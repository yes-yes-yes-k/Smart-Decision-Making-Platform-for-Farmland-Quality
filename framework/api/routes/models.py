from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from framework.core_engine import core_engine

models_bp = Blueprint('models', __name__)

@models_bp.route('/', methods=['GET'])
@jwt_required()
def get_models():
    area_code = request.args.get('area_code', 'lechang')
    include_non_professional = request.args.get('include_non_professional', 'false').lower() == 'true'
    result = core_engine.list_thematic_models(area_code, include_non_professional=include_non_professional)
    if result.get('status') == 'ok':
        models = [
            {"name": model.get('model_id', model.get('name')), "description": model.get('purpose', model.get('description', ''))}
            for model in result.get('models', [])
        ]
        return jsonify({"status": "ok", "data": models})
    return jsonify(result)

@models_bp.route('/run', methods=['POST'])
@jwt_required()
def run_model():
    data = request.get_json()
    model_id = data.get('model_id')
    if not model_id:
        return jsonify({"status": "error", "error": {"code": "MISSING_MODEL_ID", "message": "调用专题模型时必须提供 model_id"}}), 400

    payload = {"model_id": model_id}
    if 'area_code' in data:
        payload['area_code'] = data['area_code']
    if 'longitude' in data:
        payload['longitude'] = data['longitude']
    if 'latitude' in data:
        payload['latitude'] = data['latitude']
    if 'indicators' in data:
        payload['indicators'] = data['indicators']
    if 'context' in data:
        payload['context'] = data['context']
    for key in (
        'parcel_id', 'parcel_code', 'question_type', 'xqmc_code', 'scenario',
        'csv_path', 'target_ph', 'exe_path', 'dat_path',
    ):
        if key in data:
            payload[key] = data[key]

    result = core_engine.run_thematic_model(payload)
    if result.get('status') == 'ok':
        return jsonify({"status": "ok", "data": result})
    return jsonify(result)
