"""Cd 通量核算的 HTTP 入口（阶段 5）。

端点前缀由 ``framework/api/app.py`` 注册为 ``/api/v1/cd-flux``，全部要求 JWT。

口径与边界见 ``framework/domain/other_models/cd_flux.py``：
输入行外部供给（CSV 导入）→ 计算 In/Out/Net/End → 区域统计/分布 → 点位/地图 → 导出。
空数据返回 200 + ``has_data=false``（与阶段 2 一致）。
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.api.services.cd_chat_artifacts import legacy_access

from framework.domain.other_models import cd_flux, cd_projection, cd_removal

LOG = logging.getLogger(__name__)

cd_flux_bp = Blueprint("cd_flux", __name__)


@cd_flux_bp.before_request
def v2_availability():
    if '/v2/' in request.path and not current_app.config.get('CD_FLUX_V2_ENABLED', True):
        return jsonify(status='unavailable', reason='cd_flux_v2_disabled'), 503


def _v2_scope():
    return {name: request.args.get(name) for name in
            ('source', 'year', 'parcel_id', 'region_type', 'region_id') if request.args.get(name) is not None}


@cd_flux_bp.route('/v2/inputs/import', methods=['POST'])
@jwt_required()
def import_v2():
    from framework.domain.other_models import cd_flux_v2
    upload = request.files.get('file')
    if upload is None:
        return jsonify(reason='missing_file'), 400
    try:
        result = cd_flux_v2.import_csv(upload.read(), legacy=request.args.get('mode') == 'legacy')
        return jsonify(status='ok', data=result)
    except (ValueError, UnicodeError) as exc:
        return jsonify(status='error', reason=str(exc)), 400


@cd_flux_bp.route('/v2/calculate', methods=['POST'])
@jwt_required()
def calculate_v2():
    from framework.domain.other_models import cd_flux_v2
    body = request.get_json(silent=True) or {}
    allowed = {'source','year','parcel_id','region_type','region_id'}
    if not isinstance(body, dict) or set(body) - allowed:
        return jsonify(reason='invalid_scope'), 400
    try:
        return jsonify(status='ok', data=cd_flux_v2.calculate(**body))
    except ValueError as exc:
        return jsonify(status='error', reason=str(exc)), 400


@cd_flux_bp.route('/v2/statistics', methods=['GET'])
@jwt_required()
def statistics_v2():
    from framework.domain.other_models import cd_flux_v2
    try:
        return jsonify(status='ok', data=cd_flux_v2.statistics(field=request.args.get('field', 'net_cd'), **_v2_scope()))
    except ValueError as exc:
        return jsonify(status='error', reason=str(exc)), 400


@cd_flux_bp.route('/v2/compare', methods=['GET'])
@jwt_required()
def compare_v2():
    from framework.domain.other_models import cd_flux_v2
    try:
        scope = _v2_scope()
        if 'year' in scope:
            raise ValueError('use_years_for_comparison')
        return jsonify(status='ok', data=cd_flux_v2.compare(request.args.getlist('years'), field=request.args.get('field', 'net_cd'), **scope))
    except ValueError as exc:
        return jsonify(status='error', reason=str(exc)), 400


@cd_flux_bp.route('/v2/results', methods=['GET'])
@jwt_required()
def results_v2():
    from framework.domain.other_models import cd_flux_v2
    try:
        limit, offset = int(request.args.get('limit', 100)), int(request.args.get('offset', 0))
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError('invalid_limit')
        result = cd_flux_v2.results(calculation_version=request.args.get('calculation_version', cd_flux_v2.VERSION), **_v2_scope())
        result['total'] = len(result['rows'])
        result['rows'] = result['rows'][offset:offset + limit]
        return jsonify(status='ok', data=result)
    except ValueError as exc:
        return jsonify(status='error', reason=str(exc)), 400

_BAD_REQUEST_CODES = {
    "unknown_field",
    "invalid_region",
    "invalid_region_type",
    "invalid_source",
    "invalid_limit",
    "invalid_csv",
    "invalid_encoding",
    "invalid_row",
    "invalid_artifact_id",
    "invalid_kind",
}


def _error(exc) -> tuple[Any, int]:
    code = str(getattr(exc, "code", "cd_flux_failed"))
    if code.startswith("missing_columns"):
        return jsonify({"status": "error", "reason": code}), 400
    if code in _BAD_REQUEST_CODES:
        return jsonify({"status": "error", "reason": code}), 400
    if code in {"region_not_found", "no_data", "artifact_not_found"}:
        return jsonify({"status": "error", "reason": code}), 404
    if code == "too_many_rows":
        return jsonify({"status": "error", "reason": code}), 413
    LOG.exception("Cd 通量接口失败: %s", code)
    return jsonify({"status": "error", "reason": "cd_flux_failed"}), 500


def _source() -> str:
    return (request.args.get("source") or "all").strip().lower()


def _field() -> str:
    return (request.args.get("field") or "in_cd").strip()


@cd_flux_bp.route("/inputs/import", methods=["POST"])
@jwt_required()
def import_inputs():
    """上传 CSV，把完整通量输入行灌入输入表（同键覆盖）。"""
    upload = request.files.get("file")
    if upload is None:
        return jsonify({"status": "error", "reason": "missing_file"}), 400
    try:
        data = cd_flux.import_csv(upload.read())
        data.update(contract_version='legacy_v1', accounting_year=None, enterprise_input_status='unknown')
    except cd_flux.CdFluxError as exc:
        return _error(exc)
    return jsonify({"status": "ok", "message": "通量输入行导入完成", "data": data})


@cd_flux_bp.route("/calculate", methods=["POST"])
@jwt_required()
def calculate():
    """输入表 → 输出表（覆盖写）。"""
    body = request.get_json(silent=True) or {}
    try:
        data = cd_flux.calculate(
            region_type=body.get("region_type"),
            region_id=body.get("region_id"),
            source=body.get("source", "all"),
        )
        data.update(contract_version='legacy_v1', accounting_year=None, enterprise_input_status='unknown')
    except cd_flux.CdFluxError as exc:
        return _error(exc)
    return jsonify({"status": "ok", "message": "Cd 通量计算完成", "data": data})


@cd_flux_bp.route("/statistics", methods=["GET"])
@jwt_required()
def statistics():
    """四类字段的区域统计与分布。"""
    try:
        data = cd_flux.statistics(
            _field(),
            region_type=request.args.get("region_type"),
            region_id=request.args.get("region_id"),
            source=_source(),
        )
    except cd_flux.CdFluxError as exc:
        return _error(exc)
    return jsonify({"status": "ok", "data": data})


@cd_flux_bp.route("/results", methods=["GET"])
@jwt_required()
def results():
    """通量明细分页。"""
    try:
        data = cd_flux.list_results(
            _field(),
            region_type=request.args.get("region_type"),
            region_id=request.args.get("region_id"),
            source=_source(),
            limit=request.args.get("limit", cd_flux.DEFAULT_PAGE_LIMIT),
            offset=request.args.get("offset", 0),
        )
    except cd_flux.CdFluxError as exc:
        return _error(exc)
    return jsonify({"status": "ok", "data": data})


@cd_flux_bp.route("/points", methods=["GET"])
@jwt_required()
def points():
    """通量点位 GeoJSON。"""
    try:
        data = cd_flux.points_geojson(
            _field(),
            region_type=request.args.get("region_type"),
            region_id=request.args.get("region_id"),
            source=_source(),
            limit=request.args.get("limit", 5000),
        )
    except cd_flux.CdFluxError as exc:
        return _error(exc)
    return jsonify(data)


@cd_flux_bp.route("/export.csv", methods=["GET"])
@jwt_required()
def export_csv():
    """CSV 导出（上限 10 万行）。"""
    field = _field()
    try:
        text, count = cd_flux.export_csv(
            field,
            region_type=request.args.get("region_type"),
            region_id=request.args.get("region_id"),
            source=_source(),
        )
    except cd_flux.CdFluxError as exc:
        return _error(exc)
    filename = f"cd_flux_{field}.csv"
    return Response(
        text,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Row-Count": str(count),
        },
    )


@cd_flux_bp.route("/visualization", methods=["POST"])
@jwt_required()
def visualization():
    """生成通量地图/直方图（复用阶段 4 引擎）。"""
    body = request.get_json(silent=True) or {}
    try:
        data = cd_flux.visualize(
            str(body.get("field") or "in_cd"),
            region_type=body.get("region_type"),
            region_id=body.get("region_id"),
            source=body.get("source", "all"),
            resolution_factor=body.get("resolution_factor", 4.0),
            owner_id=str(get_jwt_identity()),
        )
    except cd_flux.CdFluxError as exc:
        return _error(exc)
    return jsonify({"status": "ok", "message": "Cd 通量地图生成成功", "data": data})


@cd_flux_bp.route("/artifacts/<artifact_id>/<kind>", methods=["GET"])
@jwt_required()
def artifact(artifact_id: str, kind: str):
    """下载通量地图/直方图产物。"""
    try:
        path, mime = cd_flux.artifact_path(artifact_id, kind, **legacy_access(get_jwt_identity()))
    except cd_flux.CdFluxError as exc:
        return _error(exc)
    return send_file(path, mimetype=mime, as_attachment=False, download_name=path.name)


# ----------------------------- 移除项计算（阶段 6，v2 基线） -----------------------------

_REMOVAL_BAD_CODES = {*_BAD_REQUEST_CODES, "invalid_f11", "invalid_year", "year_required"}
_PROJECTION_BAD_CODES = {*_BAD_REQUEST_CODES, "invalid_accounting_year"}


def _removal_error(exc) -> tuple[Any, int]:
    code = str(getattr(exc, "code", "cd_removal_failed"))
    if code in _REMOVAL_BAD_CODES:
        return jsonify({"status": "error", "reason": code}), 400
    if code in {"region_not_found", "no_data"}:
        return jsonify({"status": "error", "reason": code}), 404
    if code == "too_many_rows":
        return jsonify({"status": "error", "reason": code}), 413
    LOG.exception("Cd 移除项接口失败: %s", code)
    return jsonify({"status": "error", "reason": "cd_removal_failed"}), 500


def _projection_error(exc) -> tuple[Any, int]:
    code = str(getattr(exc, "code", "cd_projection_failed"))
    if code in _PROJECTION_BAD_CODES:
        return jsonify({"status": "error", "reason": code}), 400
    if code in {"region_not_found", "no_data"}:
        return jsonify({"status": "error", "reason": code}), 404
    if code == "too_many_rows":
        return jsonify({"status": "error", "reason": code}), 413
    LOG.exception("Cd 未来预测接口失败: %s", code)
    return jsonify({"status": "error", "reason": "cd_projection_failed"}), 500


@cd_flux_bp.route("/v2/removal/calculate", methods=["POST"])
@jwt_required()
def removal_calculate():
    """计算籽粒/秸秆移除，写回 v2 输入表并触发 v2 重算（写回时必须给 ``year``）。"""
    body = request.get_json(silent=True) or {}
    try:
        data = cd_removal.calculate(
            f11=body.get("f11", cd_removal.F11_DEFAULT),
            region_type=body.get("region_type"),
            region_id=body.get("region_id"),
            source=body.get("source", "all"),
            year=body.get("year"),
            write_back=bool(body.get("write_back", True)),
            recalculate=bool(body.get("recalculate", True)),
        )
    except cd_removal.CdRemovalError as exc:
        return _removal_error(exc)
    return jsonify({"status": "ok", "message": "Cd 移除项计算完成", "data": data})


@cd_flux_bp.route("/v2/removal/statistics", methods=["GET"])
@jwt_required()
def removal_statistics():
    """四类移除项的区域统计。"""
    try:
        data = cd_removal.statistics(
            (request.args.get("field") or "grain").strip(),
            f11=request.args.get("f11"),
            region_type=request.args.get("region_type"),
            region_id=request.args.get("region_id"),
            source=_source(),
            year=request.args.get("year"),
        )
    except cd_removal.CdRemovalError as exc:
        return _removal_error(exc)
    return jsonify({"status": "ok", "data": data})


@cd_flux_bp.route("/v2/removal/points", methods=["GET"])
@jwt_required()
def removal_points():
    """四类移除项点位 GeoJSON。"""
    try:
        data = cd_removal.points_geojson(
            (request.args.get("field") or "grain").strip(),
            f11=request.args.get("f11"),
            region_type=request.args.get("region_type"),
            region_id=request.args.get("region_id"),
            source=_source(),
            year=request.args.get("year"),
            limit=request.args.get("limit", 5000),
        )
    except cd_removal.CdRemovalError as exc:
        return _removal_error(exc)
    return jsonify(data)


@cd_flux_bp.route("/v2/removal/export.csv", methods=["GET"])
@jwt_required()
def removal_export_csv():
    """四类移除项 CSV 导出。"""
    field = (request.args.get("field") or "grain").strip()
    try:
        text, count = cd_removal.export_csv(
            field,
            f11=request.args.get("f11"),
            region_type=request.args.get("region_type"),
            region_id=request.args.get("region_id"),
            source=_source(),
            year=request.args.get("year"),
        )
    except cd_removal.CdRemovalError as exc:
        return _removal_error(exc)
    return Response(
        text,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=cd_removal_{field}.csv",
            "X-Row-Count": str(count),
        },
    )


@cd_flux_bp.route("/v2/removal/visualization", methods=["POST"])
@jwt_required()
def removal_visualization():
    """生成移除项地图/直方图（复用阶段 4 引擎）。"""
    body = request.get_json(silent=True) or {}
    try:
        data = cd_removal.visualize(
            str(body.get("field") or "grain"),
            f11=body.get("f11"),
            region_type=body.get("region_type"),
            region_id=body.get("region_id"),
            source=body.get("source", "all"),
            year=body.get("year"),
            resolution_factor=body.get("resolution_factor", 4.0),
        )
    except cd_removal.CdRemovalError as exc:
        return _removal_error(exc)
    return jsonify({"status": "ok", "message": "Cd 移除项地图生成成功", "data": data})


# ----------------------------- 未来情景预测（阶段 7，v2 基线） -----------------------------


@cd_flux_bp.route("/v2/projection", methods=["POST"])
@jwt_required()
def projection():
    """多年份情景预测（``years`` 可单个或列表；``accounting_year`` 为 v2 数据维度筛选）。"""
    body = request.get_json(silent=True) or {}
    try:
        data = cd_projection.predict(
            body.get("years", 10),
            region_type=body.get("region_type"),
            region_id=body.get("region_id"),
            source=body.get("source", "all"),
            accounting_year=body.get("accounting_year"),
        )
    except cd_projection.CdProjectionError as exc:
        return _projection_error(exc)
    return jsonify({"status": "ok", "message": "Cd 未来情景预测完成", "data": data})


@cd_flux_bp.route("/v2/projection/statistics", methods=["GET"])
@jwt_required()
def projection_statistics():
    """单年份未来 Cd 统计。"""
    try:
        data = cd_projection.statistics(
            request.args.get("years", 10),
            region_type=request.args.get("region_type"),
            region_id=request.args.get("region_id"),
            source=_source(),
            accounting_year=request.args.get("accounting_year"),
        )
    except cd_projection.CdProjectionError as exc:
        return _projection_error(exc)
    return jsonify({"status": "ok", "data": data})


@cd_flux_bp.route("/v2/projection/points", methods=["GET"])
@jwt_required()
def projection_points():
    """未来 Cd 点位 GeoJSON。"""
    try:
        data = cd_projection.points_geojson(
            request.args.get("years", 10),
            region_type=request.args.get("region_type"),
            region_id=request.args.get("region_id"),
            source=_source(),
            accounting_year=request.args.get("accounting_year"),
            limit=request.args.get("limit", 5000),
        )
    except cd_projection.CdProjectionError as exc:
        return _projection_error(exc)
    return jsonify(data)


@cd_flux_bp.route("/v2/projection/export.csv", methods=["GET"])
@jwt_required()
def projection_export_csv():
    """未来 Cd CSV 导出。"""
    years = request.args.get("years", 10)
    try:
        text, count = cd_projection.export_csv(
            years,
            region_type=request.args.get("region_type"),
            region_id=request.args.get("region_id"),
            source=_source(),
            accounting_year=request.args.get("accounting_year"),
        )
    except cd_projection.CdProjectionError as exc:
        return _projection_error(exc)
    return Response(
        text,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=cd_projection_{years}y.csv",
            "X-Row-Count": str(count),
        },
    )


@cd_flux_bp.route("/v2/projection/visualization", methods=["POST"])
@jwt_required()
def projection_visualization():
    """未来 Cd 空间分布地图/直方图（复用阶段 4 引擎）。"""
    body = request.get_json(silent=True) or {}
    try:
        data = cd_projection.visualize(
            body.get("years", 10),
            region_type=body.get("region_type"),
            region_id=body.get("region_id"),
            source=body.get("source", "all"),
            accounting_year=body.get("accounting_year"),
            resolution_factor=body.get("resolution_factor", 4.0),
        )
    except cd_projection.CdProjectionError as exc:
        return _projection_error(exc)
    return jsonify({"status": "ok", "message": "Cd 未来情景地图生成成功", "data": data})
