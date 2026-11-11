from collections.abc import Mapping

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from framework.models import AcidificationMeasurement, Conversation, db


acidification_measurements_bp = Blueprint("acidification_measurements", __name__)
_MODES = {"prediction", "governance"}


def _owned_conversation(conversation_id, user_id):
    return Conversation.query.filter_by(
        id=conversation_id, user_id=user_id,
    ).first()


@acidification_measurements_bp.route(
    "/conversations/<int:conversation_id>/acidification-measurements",
    methods=["GET", "POST"],
)
@jwt_required()
def conversation_measurements(conversation_id):
    user_id = int(get_jwt_identity())
    conversation = _owned_conversation(conversation_id, user_id)
    if conversation is None:
        return jsonify({"status": "error", "message": "会话不存在或无权访问"}), 404

    if request.method == "GET":
        rows = AcidificationMeasurement.query.filter_by(
            conversation_id=conversation.id,
            user_id=user_id,
        ).order_by(
            AcidificationMeasurement.created_at,
            AcidificationMeasurement.id,
        ).all()
        return jsonify({"status": "ok", "data": [row.to_dict() for row in rows]})

    body = request.get_json(silent=True) or {}
    parcel_id = body.get("parcel_id")
    mode = body.get("mode")
    input_data = body.get("input_data", {})
    source_info = body.get("source_info", {})
    if not isinstance(parcel_id, (str, int)) or not str(parcel_id).strip():
        return jsonify({"status": "error", "message": "parcel_id 必须有效"}), 400
    if mode not in _MODES:
        return jsonify({"status": "error", "message": "酸化测算模式无效"}), 400
    if not isinstance(input_data, Mapping) or not isinstance(source_info, Mapping):
        return jsonify({"status": "error", "message": "输入与来源必须为对象"}), 400

    row = AcidificationMeasurement(
        user_id=user_id,
        conversation_id=conversation.id,
        parcel_id=str(parcel_id),
        mode=mode,
        land_type=body.get("land_type"),
        input_data=dict(input_data),
        source_info=dict(source_info),
        status="draft",
    )
    db.session.add(row)
    db.session.commit()
    return jsonify({"status": "ok", "data": row.to_dict()}), 201


@acidification_measurements_bp.route(
    "/<int:measurement_id>", methods=["PATCH"],
)
@jwt_required()
def update_measurement(measurement_id):
    user_id = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    conversation_id = body.get("conversation_id")
    try:
        conversation_id = int(conversation_id)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "conversation_id 必须有效"}), 400
    if _owned_conversation(conversation_id, user_id) is None:
        return jsonify({"status": "error", "message": "会话不存在或无权访问"}), 404
    row = AcidificationMeasurement.query.filter_by(
        id=measurement_id,
        user_id=user_id,
        conversation_id=conversation_id,
    ).first()
    if row is None:
        return jsonify({"status": "error", "message": "测算记录不存在或无权访问"}), 404

    for key in ("input_data", "result_data", "source_info"):
        if key in body and body[key] is not None and not isinstance(body[key], Mapping):
            return jsonify({"status": "error", "message": f"{key} 必须为对象"}), 400
    if "parcel_id" in body and (
        not isinstance(body["parcel_id"], (str, int)) or not str(body["parcel_id"]).strip()
    ):
        return jsonify({"status": "error", "message": "parcel_id 必须有效"}), 400
    if "mode" in body and body["mode"] not in _MODES:
        return jsonify({"status": "error", "message": "酸化测算模式无效"}), 400
    if "status" in body and body["status"] not in {"draft", "completed"}:
        return jsonify({"status": "error", "message": "测算记录状态无效"}), 400

    for key in ("parcel_id", "input_data", "result_data", "source_info", "mode", "land_type", "status"):
        if key in body:
            value = str(body[key]) if key == "parcel_id" else body[key]
            setattr(row, key, dict(value) if key in {"input_data", "result_data", "source_info"} and value is not None else value)
    if row.status == "completed" and not row.result_data:
        return jsonify({"status": "error", "message": "已完成记录必须包含计算结果"}), 400
    db.session.commit()
    return jsonify({"status": "ok", "data": row.to_dict()})
