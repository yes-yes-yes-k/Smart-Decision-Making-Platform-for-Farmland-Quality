from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

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