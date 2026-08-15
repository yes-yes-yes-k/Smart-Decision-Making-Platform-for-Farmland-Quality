"""观测 API：追溯链与看板指标查询端点（均需 JWT 鉴权）。

- GET /api/v1/observability/trace/<trace_id> → 追溯信息（命中 200，未命中 404）
- GET /api/v1/observability/dashboard → 看板结构化 JSON 指标（Task 5 补充）
"""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from framework.observability.traceability import trace_result

observability_bp = Blueprint('observability', __name__)


@observability_bp.route('/trace/<trace_id>', methods=['GET'])
@jwt_required()
def get_trace(trace_id):
    """按 trace_id 返回追溯信息；未命中返回 404。"""
    info = trace_result(trace_id)
    if info is None:
        return jsonify({"status": "error", "message": "trace 不存在"}), 404
    return jsonify({"status": "ok", "data": info})