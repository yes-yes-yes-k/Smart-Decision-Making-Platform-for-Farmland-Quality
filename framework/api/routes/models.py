import uuid

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from framework.core_engine import core_engine
import logging

logger = logging.getLogger(__name__)
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
    data = request.get_json(silent=True) or {}
    model_id = data.get('model_id')
    if not model_id:
        return jsonify({"status": "error", "error": {"code": "MISSING_MODEL_ID", "message": "调用专题模型时必须提供 model_id"}}), 400
    response_schema = str(data.get("response_schema", "2.0"))
    if response_schema not in {"1.0", "2.0"}:
        return jsonify({
            "schema_version": "2.0",
            "status": "error",
            "error": {"code": "INVALID_RESPONSE_SCHEMA", "message": "response_schema 仅支持 1.0 或 2.0"},
        }), 400

    parcel_id = data.get('parcel_id', '')
    parcel_code = data.get('parcel_code', '')
    print(f"\n{'='*60}")
    print(f"[模型调用] 收到请求: model_id={model_id}, parcel_id={parcel_id}, parcel_code={parcel_code}")
    print(f"{'='*60}")

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
        'parcel_id', 'parcel_code', 'target_ph', 'exe_path', 'dat_path',
        'land_type', 'fertilizer_type', 'db_path',
        'pH', 'SOCbe', 'SOMbe', 'TN', 'TP', 'TK', 'AP', 'AK', 'Gap',
        'Dose', 'Fertilizer type',
        'SJD', 'YJZ', 'TD', 'TL', 'TJ', 'YXL', 'SXJ', 'YJZTSZ', 'YJFLX',
    ):
        if key in data:
            payload[key] = data[key]

    result = core_engine.run_thematic_model(payload)
    trace_id = str(uuid.uuid4())
    from framework.agents.output_contract import (
        LEGACY_SCHEMA_VERSION,
        SCHEMA_VERSION,
        legacy_projection,
        public_full,
    )
    from framework.observability.schema_metrics import record_schema_call

    if response_schema == LEGACY_SCHEMA_VERSION:
        record_schema_call(response_schema, result.get("status", "error"))
        return jsonify({
            "schema_version": LEGACY_SCHEMA_VERSION,
            "trace_id": trace_id,
            "status": "ok",
            "data": legacy_projection(result),
            "deprecation": {
                "code": "SCHEMA_1_DEPRECATED",
                "message": "Schema 1.0 已弃用，请迁移到 Schema 2.0。",
            },
        })
    if response_schema != SCHEMA_VERSION:
        return jsonify({
            "schema_version": SCHEMA_VERSION,
            "trace_id": trace_id,
            "status": "error",
            "error": {"code": "INVALID_RESPONSE_SCHEMA", "message": "response_schema 仅支持 1.0 或 2.0"},
        }), 400

    record_schema_call(response_schema, result.get("status", "error"))
    logger.info("模型调用完成 model_id=%s status=%s trace_id=%s", model_id, result.get("status"), trace_id)
    return jsonify({
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "status": "ok",
        "data": public_full(result),
    })
