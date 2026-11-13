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

from framework.domain.other_models import cd_flux

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
