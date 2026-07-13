from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from framework.core_engine import core_engine

county_bp = Blueprint('county', __name__)

@county_bp.route('/overview', methods=['GET'])
@jwt_required()
def get_overview():
    area_code = request.args.get('area_code', 'lechang')
    result = core_engine.get_county_overview(area_code)
    if result.get('status') == 'ok':
        return jsonify({"status": "ok", "data": result})
    return jsonify(result)

@county_bp.route('/diagnose', methods=['POST'])
@jwt_required()
def diagnose():
    data = request.get_json()
    topic = data.get('topic', 'quality')
    area_code = data.get('area_code', 'lechang')
    payload = {"topic": topic, "area_code": area_code}
    if 'longitude' in data:
        payload['longitude'] = data['longitude']
    if 'latitude' in data:
        payload['latitude'] = data['latitude']
    if 'target_ph' in data:
        payload['target_ph'] = data['target_ph']

    result = core_engine.diagnose_county(payload)
    if result.get('status') == 'ok':
        return jsonify({"status": "ok", "data": result})
    return jsonify(result)