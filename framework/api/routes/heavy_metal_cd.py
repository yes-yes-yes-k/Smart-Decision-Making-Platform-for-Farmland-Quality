"""Cd 结果统计、明细与导出的 HTTP 入口（阶段 2）。

端点前缀由 ``framework/api/app.py`` 注册为 ``/api/v1/heavy-metal-cd``，全部要求 JWT。

口径与边界见 ``framework/domain/other_models/heavy_metal_cd_statistics.py``：
作物 Cd 有三档分布（仅分布描述，非安全判定），有效态 Cd 只有 8 项基础统计；
空数据返回 200 + ``has_data=false``，不用 404 区分"没数据"和"出错"。
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import jwt_required

from framework.domain.other_models import heavy_metal_cd
from framework.domain.other_models import heavy_metal_cd_statistics as statistics
from framework.domain.other_models import heavy_metal_cd_spatial as spatial

LOG = logging.getLogger(__name__)

heavy_metal_cd_bp = Blueprint("heavy_metal_cd", __name__)

_BAD_REQUEST_CODES = {
    "unknown_model",
    "invalid_limit",
    "invalid_offset",
    "invalid_region_type",
    "invalid_parent",
    "invalid_min_count",
    "invalid_bbox",
}


def _area_code() -> str | None:
    raw = request.args.get("area_code")
    if raw is None:
        return None
    raw = raw.strip()
    return raw or None


def _error_response(exc: statistics.CdStatisticsError):
    code = str(exc.code)
    if code.startswith("export_exceeds_limit"):
        payload = {"status": "error", "reason": "export_exceeds_limit"}
        detail = code.split(":", 1)[1] if ":" in code else ""
        if ">" in detail:
            total, limit = detail.split(">", 1)
            payload["count"] = int(total) if total.isdigit() else None
            payload["max_rows"] = int(limit) if limit.isdigit() else None
        payload["message"] = "导出行数超过单次上限，请按分页导出"
        return jsonify(payload), 413
    if code in _BAD_REQUEST_CODES:
        return jsonify({"status": "error", "reason": code}), 400
    LOG.exception("Cd 统计接口失败: %s", code)
    return jsonify({"status": "error", "reason": "statistics_failed"}), 500


@heavy_metal_cd_bp.route("/statistics/crop-cd", methods=["GET"])
@jwt_required()
def crop_cd_statistics():
    """作物 Cd 统计：8 项基础统计 + 三档分布（带非安全判定声明）。"""
    try:
        data = statistics.crop_cd_statistics(_area_code())
    except statistics.CdStatisticsError as exc:
        return _error_response(exc)
    return jsonify({"status": "ok", "message": "获取作物Cd预测统计信息成功", "data": data})


@heavy_metal_cd_bp.route("/statistics/effective-cd", methods=["GET"])
@jwt_required()
def effective_cd_statistics():
    """有效态 Cd 统计：只有 8 项基础统计，不提供分箱。"""
    try:
        data = statistics.effective_cd_statistics(_area_code())
    except statistics.CdStatisticsError as exc:
        return _error_response(exc)
    return jsonify({"status": "ok", "message": "获取有效态Cd预测统计信息成功", "data": data})


@heavy_metal_cd_bp.route("/statistics/combined", methods=["GET"])
@jwt_required()
def combined_statistics():
    """双模型综合统计与完整性标记。"""
    try:
        data = statistics.combined_statistics(_area_code())
    except statistics.CdStatisticsError as exc:
        return _error_response(exc)
    return jsonify({"status": "ok", "message": "获取综合统计信息成功", "data": data})


@heavy_metal_cd_bp.route("/results", methods=["GET"])
@jwt_required()
def list_results():
    """分页明细。参数：model（必填）、area_code、limit（1-1000）、offset。"""
    model_id = (request.args.get("model") or "").strip()
    if model_id not in statistics.MODEL_IDS:
        return jsonify({"status": "error", "reason": "unknown_model"}), 400
    try:
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "reason": "invalid_limit"}), 400
    try:
        data = statistics.list_results(model_id, _area_code(), limit=limit, offset=offset)
    except statistics.CdStatisticsError as exc:
        return _error_response(exc)
    return jsonify({"status": "ok", "data": data})


@heavy_metal_cd_bp.route("/results.csv", methods=["GET"])
@jwt_required()
def export_results_csv():
    """导出 CSV（UTF-8 BOM）。超过单次上限返回 413，不返回截断文件。"""
    model_id = (request.args.get("model") or "").strip()
    if model_id not in statistics.MODEL_IDS:
        return jsonify({"status": "error", "reason": "unknown_model"}), 400
    try:
        payload, total = statistics.export_csv(model_id, _area_code())
    except statistics.CdStatisticsError as exc:
        return _error_response(exc)
    response = Response(payload, mimetype="text/csv")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{statistics.csv_filename(model_id)}"'
    )
    response.headers["X-Row-Count"] = str(total)
    return response


@heavy_metal_cd_bp.route("/models", methods=["GET"])
@jwt_required()
def list_models():
    """模型清单与输入契约（含单位标注与核验状态）。"""
    try:
        models = heavy_metal_cd.available_models()
    except heavy_metal_cd.HeavyMetalCdError:
        return jsonify({"status": "error", "reason": "model_unavailable"}), 503
    return jsonify({"status": "ok", "models": models})


# ----------------------------- 空间分析（阶段 3） -----------------------------


def _spatial_error(exc) -> tuple[Any, int]:
    code = str(getattr(exc, "code", "spatial_failed"))
    if code == "region_not_found":
        return jsonify({"status": "error", "reason": code}), 404
    if code in _BAD_REQUEST_CODES:
        return jsonify({"status": "error", "reason": code}), 400
    LOG.exception("Cd 空间接口失败: %s", code)
    return jsonify({"status": "error", "reason": "spatial_failed"}), 500


def _parse_bbox(raw: str | None) -> list[float] | None:
    if raw is None or not str(raw).strip():
        return None
    parts = [p.strip() for p in str(raw).split(",")]
    if len(parts) != 4:
        raise spatial.CdSpatialError("invalid_bbox")
    try:
        return [float(p) for p in parts]
    except (TypeError, ValueError) as exc:
        raise spatial.CdSpatialError("invalid_bbox") from exc


@heavy_metal_cd_bp.route("/spatial/townships", methods=["GET"])
@jwt_required()
def spatial_townships():
    """按区域（默认 township）聚合的 Cd 统计列表。"""
    model_id = (request.args.get("model") or "crop_cd").strip()
    if model_id not in statistics.MODEL_IDS:
        return jsonify({"status": "error", "reason": "unknown_model"}), 400
    try:
        min_count = int(request.args.get("min_count", 1))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "reason": "invalid_min_count"}), 400
    try:
        data = spatial.township_statistics(
            model_id,
            region_type=request.args.get("region_type") or "township",
            parent_type=request.args.get("parent_type"),
            parent_id=request.args.get("parent_id"),
            min_count=min_count,
        )
    except spatial.CdSpatialError as exc:
        return _spatial_error(exc)
    return jsonify({"status": "ok", "data": data})


@heavy_metal_cd_bp.route(
    "/spatial/regions/<object_type>/<object_id>/statistics", methods=["GET"]
)
@jwt_required()
def spatial_region_statistics(object_type: str, object_id: str):
    """单个区域的 Cd 统计（归属走面积表，不用点面判断）。"""
    model_id = (request.args.get("model") or "crop_cd").strip()
    if model_id not in statistics.MODEL_IDS:
        return jsonify({"status": "error", "reason": "unknown_model"}), 400
    try:
        data = spatial.region_statistics(model_id, object_type, object_id)
    except spatial.CdSpatialError as exc:
        return _spatial_error(exc)
    return jsonify({"status": "ok", "data": data})


@heavy_metal_cd_bp.route("/spatial/points", methods=["GET"])
@jwt_required()
def spatial_points():
    """点位 GeoJSON（坐标取地块质心）。"""
    model_id = (request.args.get("model") or "crop_cd").strip()
    if model_id not in statistics.MODEL_IDS:
        return jsonify({"status": "error", "reason": "unknown_model"}), 400
    try:
        bbox = _parse_bbox(request.args.get("bbox"))
        limit = int(request.args.get("limit", spatial.DEFAULT_POINT_LIMIT))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "reason": "invalid_limit"}), 400
    try:
        payload = spatial.points_geojson(model_id, bbox=bbox, limit=limit)
    except spatial.CdSpatialError as exc:
        return _spatial_error(exc)
    return jsonify(payload)
