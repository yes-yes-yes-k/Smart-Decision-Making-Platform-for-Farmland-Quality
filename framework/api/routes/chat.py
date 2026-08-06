import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.models.conversation import Conversation
from framework.models.message import Message
from framework.models.user import db
from framework.agents.orchestrator import multi_agent_orchestrator

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
    user_id = get_jwt_identity()
    data = request.get_json()
    conversation_id = data.get('conversation_id')
    message = data.get('message', '')
    context = data.get('context', {})

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
    # top-level parcel_id/parcel_code 优先（覆盖 context 内同名字段）
    # parcel_id（数字字符串）给 model-1/2/4 查 DB，parcel_code（字母数字）给 model-5 调评价程序
    for k in ("parcel_id", "parcel_code", "land_type", "fertilizer_type"):
        if data.get(k) is not None:
            orchestrator_request[k] = data[k]
    result = multi_agent_orchestrator.run(orchestrator_request, conversation_history=history)

    answer = result.get("answer", result.get("llm_response", ""))
    sources = result.get("sources", [])
    model_results = result.get("model_results", {})
    question_type = result.get("question_type", 0)
    routing_status = result.get("routing_status", "normal")
    degradation = result.get("degradation")

    # 解析 AgentManager 结构化结果（若存在）
    agent_data = model_results.get("data", {}) if isinstance(model_results, dict) else {}
    agents_invoked = agent_data.get("agents_invoked", [])
    recommendations = agent_data.get("recommendations", [])
    multi_agent_summary = agent_data.get("summary", "")

    assistant_message = Message(
        conversation_id=conversation.id,
        role='assistant',
        content=answer or multi_agent_summary,
        sources=sources if sources else None,
    )
    db.session.add(assistant_message)
    db.session.commit()

    response_data = {
        "answer": answer or multi_agent_summary,
        "sources": sources,
        "question_type": question_type,
        "model_results": model_results,
        "message_id": assistant_message.id,
        "routing_status": routing_status,
    }
    if agents_invoked:
        response_data["agents_invoked"] = agents_invoked
    if recommendations:
        response_data["recommendations"] = recommendations
    if degradation:
        response_data["degradation"] = degradation

    return jsonify({
        "status": "ok",
        "data": response_data,
    })