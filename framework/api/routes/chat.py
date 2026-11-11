import json
from flask import Blueprint, request, jsonify, Response, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.models.conversation import Conversation
from framework.models.user import db
from framework.agents.orchestrator import multi_agent_orchestrator
from framework.agents.orchestrator import runtime_from_current_app
from framework.agents.workflows.comprehensive.runtime import WorkflowConflict, WorkflowNotFound, CheckpointerUnavailable
from framework.analysis_context.errors import AnalysisContextError
from framework.domain.public_field_labels import (
    PublicTextStreamTranslator,
    translate_public_text,
)
from framework.api.services import chat_request_service
from framework.observability.analysis_context_metrics import (
    EVENT_ERROR_409, EVENT_ERROR_422, EVENT_ERROR_503,
    record_analysis_context_event,
)
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
    routing = result.get("routing", {}) if isinstance(result, dict) else {}
    if not isinstance(routing, dict):
        routing = {}
    question_type = result.get("question_type", routing.get("question_type", 0)) if isinstance(result, dict) else 0
    routing_status = result.get("routing_status", routing.get("status", "normal")) if isinstance(result, dict) else "normal"
    data = {
        "message_id": message_id,
        "answer": translate_public_text(result.get("answer", "")) if isinstance(result, dict) else "",
        "sources": result.get("sources", []) if isinstance(result, dict) else [],
        "recommendations": [
            translate_public_text(item) if isinstance(item, str) else item
            for item in ((result.get("recommendations") or []) if isinstance(result, dict) else [])
        ],
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


def _response_options(body: dict) -> tuple[bool, str]:
    response_schema = str(body.get("response_schema", SCHEMA_VERSION))
    if response_schema not in {SCHEMA_VERSION, LEGACY_SCHEMA_VERSION}:
        raise ValueError("response_schema 仅支持 1.0 或 2.0")
    return bool(body.get("include_model_results", False)), response_schema


def _serialize_prepared_response(prepared, result, message_id, *, include_model_results, response_schema):
    rich = chat_request_service.build_response(prepared, result, message_id=message_id)
    model_results = rich.get("model_results", {})
    models = rich.get("models") or (
        model_results.get("models", {}) if isinstance(model_results, dict) else {}
    )
    response = _serialize_chat_response(
        {**rich, "models": models}, message_id,
        include_model_results=include_model_results,
        response_schema=response_schema,
    )
    for key in (
        "interaction_state", "analysis_context", "provenance", "scenario_result",
        "spatial_object", "object_title", "required_object_types", "missing_inputs", "trace_id",
        "run_id", "checkpoint_version", "plan_summary", "proposed_defaults",
        "report_draft", "degradations",
    ):
        if key in rich:
            response["data"][key] = rich[key]
    if response_schema == LEGACY_SCHEMA_VERSION:
        response["deprecation"] = {
            "code": "SCHEMA_1_DEPRECATED",
            "message": "Schema 1.0 已弃用，请迁移到 Schema 2.0。",
        }
    return response

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
    messages = []
    for message in conversation.messages:
        payload = message.to_dict()
        if message.role == "assistant":
            payload["content"] = translate_public_text(payload.get("content", ""))
        messages.append(payload)
    return jsonify({"status": "ok", "data": messages})

@chat_bp.route('/', methods=['POST'])
@jwt_required()
def chat():
    body = request.get_json(silent=True) or {}
    try:
        include_model_results, response_schema = _response_options(body)
    except ValueError as exc:
        return jsonify({
            "schema_version": SCHEMA_VERSION, "status": "error",
            "error": {"code": "INVALID_RESPONSE_SCHEMA", "message": str(exc)},
        }), 400
    try:
        prepared = chat_request_service.prepare(
            user_id=int(get_jwt_identity()), body=body,
        )
    except AnalysisContextError as exc:
        record_analysis_context_event({
            409: EVENT_ERROR_409, 422: EVENT_ERROR_422, 503: EVENT_ERROR_503,
        }.get(exc.http_status, EVENT_ERROR_422), code=exc.code)
        return jsonify({"status": "error", "error": {
            "code": exc.code, "message": exc.message, "details": exc.details,
        }}), exc.http_status
    try:
        result = (runtime_from_current_app().resume(conversation_id=prepared.conversation.id,response=prepared.interaction_response).model_dump(mode="json") if prepared.interaction_response else multi_agent_orchestrator.run(prepared.orchestrator_request, conversation_history=prepared.history))
    except (WorkflowConflict, WorkflowNotFound, CheckpointerUnavailable) as exc:
        return jsonify({"status":"error","error":{"code":str(exc)}}), exc.http_status
    from framework.observability.schema_metrics import record_schema_call
    record_schema_call(response_schema, result.get("status", "error"))
    assistant = chat_request_service.persist_assistant(prepared, result)
    response = _serialize_prepared_response(
        prepared, result, assistant.id,
        include_model_results=include_model_results,
        response_schema=response_schema,
    )
    return jsonify(response)

@chat_bp.route('/stream', methods=['POST'])
@jwt_required()
def chat_stream():
    body = request.get_json(silent=True) or {}
    try:
        include_model_results, response_schema = _response_options(body)
    except ValueError as exc:
        return jsonify({
            "schema_version": SCHEMA_VERSION, "status": "error",
            "error": {"code": "INVALID_RESPONSE_SCHEMA", "message": str(exc)},
        }), 400
    try:
        prepared = chat_request_service.prepare(
            user_id=int(get_jwt_identity()), body=body,
        )
    except AnalysisContextError as exc:
        record_analysis_context_event({
            409: EVENT_ERROR_409, 422: EVENT_ERROR_422, 503: EVENT_ERROR_503,
        }.get(exc.http_status, EVENT_ERROR_422), code=exc.code)
        return jsonify({"status": "error", "error": {
            "code": exc.code, "message": exc.message, "details": exc.details,
        }}), exc.http_status

    # 在生成器外部捕获 app 实例，因为生成器迭代时请求/应用上下文已销毁
    app = current_app._get_current_object()

    def event_stream():
        public_text = PublicTextStreamTranslator()
        try:
            for item in multi_agent_orchestrator.run_stream(
                prepared.orchestrator_request, conversation_history=prepared.history,
            ):
                item_type = item.get("type")
                if item_type == "token":
                    content = public_text.feed(item.get("content", ""))
                    if content:
                        yield f"data: {json.dumps({'event': 'token', 'content': content}, ensure_ascii=False)}\n\n"
                elif item_type == "meta":
                    yield f"data: {json.dumps({'event': 'meta', 'data': item.get('data', {})})}\n\n"
                elif item_type == "done":
                    pending_text = public_text.flush()
                    if pending_text:
                        yield f"data: {json.dumps({'event': 'token', 'content': pending_text}, ensure_ascii=False)}\n\n"
                    data_payload = item.get("data", {})
                    app_ctx = app.app_context()
                    app_ctx.push()
                    try:
                        assistant = chat_request_service.persist_assistant(prepared, data_payload)
                        response = _serialize_prepared_response(
                            prepared, data_payload, assistant.id,
                            include_model_results=include_model_results,
                            response_schema=response_schema,
                        )
                        from framework.observability.schema_metrics import record_schema_call
                        record_schema_call(response_schema, data_payload.get("status", "ok"))
                    except Exception:
                        from framework.models import db
                        db.session.rollback()
                        raise
                    finally:
                        app_ctx.pop()
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
