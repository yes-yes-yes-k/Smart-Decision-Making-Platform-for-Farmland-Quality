import os
import json
from flask import Blueprint, request, jsonify, Response, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.models.conversation import Conversation
from framework.models.message import Message
from framework.models.user import db
from framework.agents.orchestrator import multi_agent_orchestrator
from framework.agents.output_contract import (
    LEGACY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    chat_compact,
    legacy_projection,
)

chat_bp = Blueprint('chat', __name__)


def _serialize_chat_response(
    result: dict,
    message_id: int | None,
    *,
    include_model_results: bool = False,
    response_schema: str = SCHEMA_VERSION,
) -> dict:
    """统一生成非流式和流式完成事件的公共聊天响应。"""
    if response_schema not in {SCHEMA_VERSION, LEGACY_SCHEMA_VERSION}:
        response_schema = SCHEMA_VERSION
    models = result.get("models", {}) if isinstance(result, dict) else {}
    question_type = result.get("question_type", 0) if isinstance(result, dict) else 0
    routing_status = result.get("routing_status", "normal") if isinstance(result, dict) else "normal"
    data = {
        "message_id": message_id,
        "answer": result.get("answer", "") if isinstance(result, dict) else "",
        "sources": result.get("sources", []) if isinstance(result, dict) else [],
        "recommendations": result.get("recommendations", []) if isinstance(result, dict) else [],
        "routing": {
            "question_type": question_type,
            "status": routing_status,
        },
    }
    if include_model_results and question_type != 0:
        if response_schema == LEGACY_SCHEMA_VERSION:
            data["models"] = {
                aid: legacy_projection(item) for aid, item in models.items()
            }
        else:
            data["models"] = {
                aid: chat_compact(item) for aid, item in models.items()
            }
    return {
        "schema_version": response_schema,
        "trace_id": result.get("trace_id") if isinstance(result, dict) else None,
        "status": "ok",
        "data": data,
    }

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
    user_id = get_jwt_identity()
    data = request.get_json()
    conversation_id = data.get('conversation_id')
    message = data.get('message', '')
    context = data.get('context', {})
    include_model_results = bool(data.get("include_model_results", False))
    response_schema = str(data.get("response_schema", SCHEMA_VERSION))
    if response_schema not in {SCHEMA_VERSION, LEGACY_SCHEMA_VERSION}:
        return jsonify({
            "schema_version": SCHEMA_VERSION,
            "status": "error",
            "error": {"code": "INVALID_RESPONSE_SCHEMA", "message": "response_schema 仅支持 1.0 或 2.0"},
        }), 400

    if not message:
        return jsonify({"status": "error", "message": "问题不能为空"}), 400

    if conversation_id:
        conversation = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
        if not conversation:
            return jsonify({"status": "error", "message": "对话不存在"}), 404
    else:
        conversation = Conversation(user_id=user_id, title=message[:50] if message else '新对话')
        db.session.add(conversation)
        db.session.commit()

    user_message = Message(conversation_id=conversation.id, role='user', content=message)
    db.session.add(user_message)
    db.session.commit()

    history = [{"role": m.role, "content": m.content} for m in conversation.messages if m.id != user_message.id]

    orchestrator_request = {"question": message, **context}
    # 顶层字段优先，确保 model-5 的区域、土地类型和土壤指标不在 API 边界丢失。
    for k in (
        "area_code", "parcel_id", "parcel_code", "land_type", "fertilizer_type", "db_path",
        "pH", "SOCbe", "SOMbe", "TN", "TP", "TK", "AP", "AK", "Gap",
        "Dose", "Fertilizer type", "SJD", "YJZ", "TD", "TL", "TJ", "YXL", "SXJ",
        "YJZTSZ", "YJFLX",
    ):
        if data.get(k) is not None:
            orchestrator_request[k] = data[k]
    result = multi_agent_orchestrator.run(orchestrator_request, conversation_history=history)
    from framework.observability.schema_metrics import record_schema_call
    record_schema_call(response_schema, result.get("status", "error"))

    answer = result.get("answer", result.get("llm_response", ""))
    sources = result.get("sources", [])
    model_results = result.get("model_results") if isinstance(result.get("model_results"), dict) else result
    question_type = result.get("question_type", model_results.get("question_type", 0))
    routing_status = result.get("routing_status", model_results.get("routing_status", "normal"))
    degradation = result.get("degradation")

    models = model_results.get("models", {}) if isinstance(model_results, dict) else {}
    recommendations = result.get("recommendations", model_results.get("recommendations", [])) or []
    multi_agent_summary = result.get("answer", model_results.get("answer", ""))
    agents_invoked = list(models.keys())

    assistant_message = Message(
        conversation_id=conversation.id,
        role='assistant',
        content=answer or multi_agent_summary,
        sources=sources if sources else None,
        agents_invoked=agents_invoked if agents_invoked else None,
        recommendations=recommendations if recommendations else None,
    )
    db.session.add(assistant_message)
    db.session.commit()

    response = _serialize_chat_response(
        {**result, "models": models},
        assistant_message.id,
        include_model_results=include_model_results,
        response_schema=response_schema,
    )
    if degradation:
        response["data"]["routing"]["degradation"] = degradation
    if response_schema == LEGACY_SCHEMA_VERSION:
        response["deprecation"] = {
            "code": "SCHEMA_1_DEPRECATED",
            "message": "Schema 1.0 已弃用，请迁移到 Schema 2.0。",
        }
    return jsonify(response)

@chat_bp.route('/stream', methods=['POST'])
@jwt_required()
def chat_stream():
    user_id = get_jwt_identity()
    data = request.get_json()
    conversation_id = data.get('conversation_id')
    message = data.get('message', '')
    context = data.get('context', {})
    include_model_results = bool(data.get("include_model_results", False))
    response_schema = str(data.get("response_schema", SCHEMA_VERSION))
    if response_schema not in {SCHEMA_VERSION, LEGACY_SCHEMA_VERSION}:
        return jsonify({
            "schema_version": SCHEMA_VERSION,
            "status": "error",
            "error": {"code": "INVALID_RESPONSE_SCHEMA", "message": "response_schema 仅支持 1.0 或 2.0"},
        }), 400

    if not message:
        return jsonify({"status": "error", "message": "问题不能为空"}), 400

    if conversation_id:
        conversation = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
        if not conversation:
            return jsonify({"status": "error", "message": "对话不存在"}), 404
    else:
        conversation = Conversation(user_id=user_id, title=message[:50] if message else '新对话')
        db.session.add(conversation)
        db.session.commit()

    user_message = Message(conversation_id=conversation.id, role='user', content=message)
    db.session.add(user_message)
    db.session.commit()

    history = [{"role": m.role, "content": m.content} for m in conversation.messages if m.id != user_message.id]

    orchestrator_request = {"question": message, **context}
    for k in (
        "area_code", "parcel_id", "parcel_code", "land_type", "fertilizer_type", "db_path",
        "pH", "SOCbe", "SOMbe", "TN", "TP", "TK", "AP", "AK", "Gap",
        "Dose", "Fertilizer type", "SJD", "YJZ", "TD", "TL", "TJ", "YXL", "SXJ",
        "YJZTSZ", "YJFLX",
    ):
        if data.get(k) is not None:
            orchestrator_request[k] = data[k]

    # 在生成器外部捕获 app 实例，因为生成器迭代时请求/应用上下文已销毁
    app = current_app._get_current_object()

    def event_stream():
        try:
            for item in multi_agent_orchestrator.run_stream(orchestrator_request, conversation_history=history):
                item_type = item.get("type")
                if item_type == "token":
                    yield f"data: {json.dumps({'event': 'token', 'content': item['content']})}\n\n"
                elif item_type == "meta":
                    yield f"data: {json.dumps({'event': 'meta', 'data': item.get('data', {})})}\n\n"
                elif item_type == "done":
                    data_payload = item.get("data", {})
                    answer = data_payload.get("answer", "")
                    sources = data_payload.get("sources", [])
                    models = data_payload.get("models", {})
                    question_type = data_payload.get("question_type", 0)

                    agents_invoked = list(models.keys()) if isinstance(models, dict) else []
                    recommendations = data_payload.get("recommendations", [])
                    multi_agent_summary = answer

                    # ✅ 修复：生成器迭代时请求上下文已销毁，需手动推入应用上下文
                    # 否则 db.session.commit() 会报 "Working outside of application context"
                    app_ctx = app.app_context()
                    app_ctx.push()
                    try:
                        assistant_message = Message(
                            conversation_id=conversation.id,
                            role='assistant',
                            content=answer or multi_agent_summary,
                            sources=sources if sources else None,
                            agents_invoked=agents_invoked if agents_invoked else None,
                            recommendations=recommendations if recommendations else None,
                        )
                        db.session.add(assistant_message)
                        db.session.commit()
                        msg_id = assistant_message.id
                    except Exception:
                        db.session.rollback()
                        msg_id = None
                    finally:
                        app_ctx.pop()

                    response_result = {
                        **data_payload,
                        "answer": answer or multi_agent_summary,
                        "sources": sources,
                        "models": models,
                        "question_type": question_type,
                        "trace_id": data_payload.get("trace_id"),
                        "recommendations": recommendations,
                    }
                    response = _serialize_chat_response(
                        response_result,
                        msg_id,
                        include_model_results=include_model_results,
                        response_schema=response_schema,
                    )
                    if response_schema == LEGACY_SCHEMA_VERSION:
                        response["deprecation"] = {
                            "code": "SCHEMA_1_DEPRECATED",
                            "message": "Schema 1.0 已弃用，请迁移到 Schema 2.0。",
                        }
                    yield f"data: {json.dumps({'event': 'done', 'data': response['data']}, ensure_ascii=False, allow_nan=False)}\n\n"
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
