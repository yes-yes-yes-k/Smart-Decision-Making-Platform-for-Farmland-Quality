from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from framework.agents.orchestrator import multi_agent_orchestrator

models_bp = Blueprint('models', __name__)

@models_bp.route('/', methods=['GET'])
@jwt_required()
def get_models():
    models = [
        {"name": "acidification_assessment", "description": "酸化程度评估模型"},
        {"name": "lime_calculation", "description": "石灰需求量计算模型"},
        {"name": "nitrogen_impact", "description": "氮肥影响模拟模型"},
        {"name": "model_4", "description": "模型4"},
        {"name": "model_5", "description": "模型5"},
        {"name": "model_6", "description": "模型6"},
    ]
    return jsonify({"status": "ok", "data": models})

@models_bp.route('/run', methods=['POST'])
@jwt_required()
def run_model():
    data = request.get_json()
    question = data.get('question', '')
    if not question:
        return jsonify({"status": "error", "message": "问题不能为空"}), 400

    result = multi_agent_orchestrator.run({"question": question})
    return jsonify(result)