from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from framework.core_engine import core_engine

models_bp = Blueprint('models', __name__)

@models_bp.route('/', methods=['GET'])
@jwt_required()
def get_models():
    area_code = request.args.get('area_code', 'lechang')
    result = core_engine.list_thematic_models(area_code)
    if result.get('status') == 'ok':
        models = [
            {"name": model.get('model_id', model.get('name')), "description": model.get('purpose', model.get('description', ''))}
            for model in result.get('models', [])
        ]
        return jsonify({"status": "ok", "data": models})
    return jsonify(result)