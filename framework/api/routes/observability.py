"""观测 API：追溯链与看板指标查询端点（均需 JWT 鉴权）。

- GET /api/v1/observability/trace/<trace_id> → 追溯信息（命中 200，未命中 404）
- GET /api/v1/observability/dashboard → 看板结构化 JSON 指标
"""
import json
import os

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from framework.observability import routing_log
from framework.observability.dashboard import compute_log_metrics
from framework.observability.traceability import trace_result
from framework.observability.schema_metrics import snapshot_schema_metrics

observability_bp = Blueprint('observability', __name__)


@observability_bp.route('/trace/<trace_id>', methods=['GET'])
@jwt_required()
def get_trace(trace_id):
    """按 trace_id 返回追溯信息；未命中返回 404。"""
    info = trace_result(trace_id)
    if info is None:
        return jsonify({"status": "error", "message": "trace 不存在"}), 404
    return jsonify({"status": "ok", "data": info})


@observability_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    """读取本地路由日志与混淆矩阵，返回结构化指标 JSON。

    复用 dashboard.compute_log_metrics 避免指标逻辑漂移；混淆矩阵文件
    （confusion_matrix*.json，含 .llm.json 变体）缺失时兜底空矩阵。
    """
    log_dir = routing_log._LOG_DIR
    entries = routing_log.read_routing_logs(log_dir)
    log_metrics = compute_log_metrics(entries)

    matrices = {}
    if os.path.isdir(log_dir):
        for name in sorted(os.listdir(log_dir)):
            if name.startswith("confusion_matrix") and name.endswith(".json"):
                try:
                    with open(os.path.join(log_dir, name), "r", encoding="utf-8") as f:
                        matrices[name] = json.load(f)
                except (OSError, json.JSONDecodeError):
                    matrices[name] = {}

    return jsonify({
        "status": "ok",
        "data": {
            "log_metrics": log_metrics,
            "confusion_matrices": matrices,
            "schema_metrics": snapshot_schema_metrics(),
        },
    })
