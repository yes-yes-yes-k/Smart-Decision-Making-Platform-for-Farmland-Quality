import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.models.conversation import Conversation
from framework.models.message import Message
from framework.models.user import db
from framework.rag.chain import rag_chain

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

    result = rag_chain.chat(message)

    assistant_message = Message(conversation_id=conversation.id, role='assistant', content=result.get('answer', ''), sources=result.get('sources'))
    db.session.add(assistant_message)
    db.session.commit()

    return jsonify({"status": "ok", "data": {"answer": result.get('answer', ''), "sources": result.get('sources', []), "message_id": assistant_message.id}})