"""酸化随机森林（RF）预测 HTTP 入口。

与 model-4 过程模型并列存在，互不调用；模型资产、来源与在线语义见
``data/model_artifacts/acidification_rf/manifest.json`` 与
``framework/domain/other_models/acidification_rf.py``。
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from framework.domain.other_models import acidification_rf

acidification_rf_bp = Blueprint("acidification_rf", __name__)

# 资产缺失、hash 不一致、模型不可用属于服务端状态，不回退到其他模型。
_MODEL_UNAVAILABLE_REASONS = {
    "model_unavailable",
    "model_integrity_mismatch",
    "model_metadata_invalid",
}


@acidification_rf_bp.route("/models", methods=["GET"])
@jwt_required()
def list_models():
    """返回当前登记的 RF 模型清单（供前端选择 model_id 与土地类型）。"""
    try:
        models = acidification_rf.available_models()
    except acidification_rf.AcidificationRFError:
        return jsonify({"status": "error", "reason": "model_unavailable"}), 503
    return jsonify({"status": "ok", "models": models})


@acidification_rf_bp.route("/parcels/<parcel_id>/prefill", methods=["GET"])
@jwt_required()
def parcel_prefill(parcel_id):
    """按地块编号返回 RF 输入预填值，供前端"选地块→自动填表"。

    可选查询参数 ``model_id`` 指定模型（须与地块土地类型匹配）；缺省取该
    土地类型的 reflux 模型。

    响应说明：

    - ``status`` 为 ``ready``（可预测）或 ``need_input``（仍有缺失字段）；
    - ``data`` 只包含有既定映射的字段，不做任何推测性填充；
    - ``provenance`` 标注每个已填字段的来源，``region_mean_backfill`` 表示
      区域平均回填而非地块实测；
    - ``missing_fields`` 列出地块数据中无对应字段的 RF 输入；
    - ``warnings`` 为可直接展示给使用者的中文提示。
    """
    from flask import current_app

    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    model_id = request.args.get("model_id", type=int)
    snapshot = ParcelDataAccessor(current_app._get_current_object()).get_parcel_snapshot(parcel_id)
    if snapshot is None:
        return jsonify({"status": "rejected", "reason": "parcel_not_found", "parcel_id": parcel_id}), 404

    try:
        result = acidification_rf.prefill_from_parcel(
            snapshot.indicators, snapshot.land_type, model_id=model_id
        )
    except acidification_rf.AcidificationRFError as exc:
        reason = str(exc)
        code = 400 if reason in {"unknown_land_type", "land_type_mismatch"} else 503
        return jsonify({"status": "rejected", "reason": reason, "parcel_id": parcel_id}), code

    result["parcel_id"] = parcel_id
    result["land_type_parcel"] = snapshot.land_type
    return jsonify(result)


@acidification_rf_bp.route("/predict", methods=["POST"])
@jwt_required()
def predict():
    """按 model_id 执行本地 RF 预测。

    请求体：

        {"model_id": 33, "data": {...}, "assumptions": {"NO3": "training_median"}}

    ``data`` 字段使用规范名：reduce 模型为
    ``init_pH/target_pH/H/Al/OM/NO3/NH4/CEC``；旱地 reflux 为
    ``H/Al/OM/NO3/NH4/CEC``；水田 reflux 为 ``CEC/NH4/NO3/Al/FeO/OM``。

    **采用 prefill 建议值的调用必须传 ``assumptions``**（字段名 → 依据），
    后端据此把 ``status`` 强制降为 ``degraded`` 并在 ``assumed_fields`` 回显。
    不传则后端无法区分采用值与实测值，结果会被记为 ``success``。

    响应 ``status``：

    - ``success``：完整输入；
    - ``degraded``：请求批次内存在缺失值，已按旧在线语义做批次均值填补，
      ``imputed_fields`` 记录被填补字段；
    - ``rejected``：输入不合法或模型资产不可用，``reason`` 说明原因。
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or "model_id" not in payload or "data" not in payload:
        return jsonify({"status": "rejected", "reason": "invalid_input", "predictions": []}), 400

    try:
        model_id = int(payload["model_id"])
    except (TypeError, ValueError):
        return jsonify({"status": "rejected", "reason": "invalid_input", "predictions": []}), 400

    assumptions = payload.get("assumptions")
    if assumptions is not None and not isinstance(assumptions, dict):
        return jsonify({"status": "rejected", "reason": "invalid_assumptions", "predictions": []}), 400

    result = acidification_rf.predict(model_id, payload["data"], assumptions=assumptions)
    if result.get("status") != "rejected":
        return jsonify(result)

    reason = str(result.get("reason") or "invalid_input")
    if reason in _MODEL_UNAVAILABLE_REASONS:
        return jsonify(result), 503
    return jsonify(result), 400
