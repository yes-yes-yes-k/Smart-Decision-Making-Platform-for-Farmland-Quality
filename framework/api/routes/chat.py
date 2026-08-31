import json
from flask import Blueprint, request, jsonify, Response, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.models.conversation import Conversation
from framework.models.user import db
from framework.agents.orchestrator import multi_agent_orchestrator
from framework.analysis_context.errors import AnalysisContextError
from framework.api.services import chat_request_service

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/conversations', methods=['GET'])
@jwt_required()
def get_conversations():
    user_id = get_jwt_identity()
    conversations = Conversation.query.filter_by(user_id=user_id).order_by(Conversation.update_time.desc()).all()
    return jsonify({"status": "ok", "data": [c.to_dict() for c in conversations]})

@chat_bp.route('/conversations', methods=['POST'])
@jwt_required()
def create_conversation():
    user_id = get_jwt_identity()
    data = request.get_json()
    title = data.get('title', '新对话')
    conversation = Conversation(user_id=user_id, title=title)
    db.session.add(conversation)
    db.session.commit()
    return jsonify({"status": "ok", "data": conversation.to_dict(), "message": "对话创建成功"})

@chat_bp.route('/conversations/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_conversation(id):
    user_id = get_jwt_identity()
    conversation = Conversation.query.filter_by(id=id, user_id=user_id).first()
    if not conversation:
        return jsonify({"status": "error", "message": "对话不存在"}), 404
    db.session.delete(conversation)
    db.session.commit()
    return jsonify({"status": "ok", "message": "对话删除成功"})

@chat_bp.route('/conversations/<int:id>/messages', methods=['GET'])
@jwt_required()
def get_messages(id):
    user_id = get_jwt_identity()
    conversation = Conversation.query.filter_by(id=id, user_id=user_id).first()
    if not conversation:
        return jsonify({"status": "error", "message": "对话不存在"}), 404
    return jsonify({"status": "ok", "data": [m.to_dict() for m in conversation.messages]})

@chat_bp.route('/', methods=['POST'])
@jwt_required()
def chat():
    try:
        prepared = chat_request_service.prepare(
            user_id=int(get_jwt_identity()), body=request.get_json(silent=True) or {},
        )
    except AnalysisContextError as exc:
        return jsonify({"status": "error", "error": {
            "code": exc.code, "message": exc.message, "details": exc.details,
        }}), exc.http_status
    result = multi_agent_orchestrator.run(
        prepared.orchestrator_request, conversation_history=prepared.history,
    )
    assistant = chat_request_service.persist_assistant(prepared, result)
    return jsonify({"status": "ok", "data": chat_request_service.build_response(
        prepared, result, message_id=assistant.id,
    )})

@chat_bp.route('/stream', methods=['POST'])
@jwt_required()
def chat_stream():
    try:
        prepared = chat_request_service.prepare(
            user_id=int(get_jwt_identity()), body=request.get_json(silent=True) or {},
        )
    except AnalysisContextError as exc:
        return jsonify({"status": "error", "error": {
            "code": exc.code, "message": exc.message, "details": exc.details,
        }}), exc.http_status

    # 在生成器外部捕获 app 实例，因为生成器迭代时请求/应用上下文已销毁
    app = current_app._get_current_object()

    def event_stream():
        try:
            for item in multi_agent_orchestrator.run_stream(
                prepared.orchestrator_request, conversation_history=prepared.history,
            ):
                item_type = item.get("type")
                if item_type == "token":
                    yield f"data: {json.dumps({'event': 'token', 'content': item['content']})}\n\n"
                elif item_type == "meta":
                    yield f"data: {json.dumps({'event': 'meta', 'data': item.get('data', {})})}\n\n"
                elif item_type == "done":
                    data_payload = item.get("data", {})
                    app_ctx = app.app_context()
                    app_ctx.push()
                    try:
                        assistant = chat_request_service.persist_assistant(prepared, data_payload)
                        response_data = chat_request_service.build_response(
                            prepared, data_payload, message_id=assistant.id,
                        )
                    except Exception:
                        from framework.models import db
                        db.session.rollback()
                        raise
                    finally:
                        app_ctx.pop()
                    yield f"data: {json.dumps({'event': 'done', 'data': response_data})}\n\n"
                elif item_type == "error":
                    yield f"data: {json.dumps({'event': 'error', 'message': item.get('message', '')})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    resp = Response(event_stream(), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache, no-transform, must-revalidate, max-age=0'
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['Connection'] = 'keep-alive'
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    # 关闭 Gzip 压缩，防止压缩导致 SSE 被缓冲
    resp.headers['Content-Encoding'] = 'identity'
    return resp
