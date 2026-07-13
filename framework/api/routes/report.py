from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from framework.core_engine import core_engine

report_bp = Blueprint('report', __name__)

@report_bp.route('/summary', methods=['POST'])
@jwt_required()
def get_report_summary():
    data = request.get_json()
    if not data or data.get('status') != 'ok':
        return jsonify({"status": "error", "error": {"code": "MISSING_DIAGNOSIS", "message": "需要传入成功的诊断结果"}}), 400

    result = core_engine.build_report_summary(data)
    if result.get('status') == 'ok':
        return jsonify({"status": "ok", "data": result})
    return jsonify(result)