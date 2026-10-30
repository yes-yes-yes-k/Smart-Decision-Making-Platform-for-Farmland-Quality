"""Spatially clipped farmland statistics used by the satellite-map dashboard."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from framework.domain.statistics import INDICATOR_DEFINITIONS, get_indicator_definition
from framework.domain.assessment.versioned_results import business_result
from framework.models import ParcelInfo, SpatialRegionCatalog, db


MU_PER_SQUARE_METRE = 1.0 / 666.6666666666666
REGION_TYPES = {"province", "city", "county", "township", "village", "zone"}


class StatisticsError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def metric_metadata() -> list[dict[str, Any]]:
    return [definition.as_dict() for definition in INDICATOR_DEFINITIONS.values()]


def _round(value: float | None, decimals: int = 4) -> float | None:
    return None if value is None else round(value, decimals)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def summarize_rows(
    rows: Iterable[Mapping[str, Any]],
    metric_keys: Iterable[str],
) -> dict[str, Any]:
    """Build table, bar-chart and pie-chart data from clipped parcel rows.

    ``area_mu`` is the area of each parcel after clipping it to the requested
    administrative boundary or viewport. Averages are area weighted.
    """
    materialized = [dict(row) for row in rows]
    total_area = sum(max(float(row.get("area_mu") or 0), 0) for row in materialized)
    data_as_of_values = [row.get("updated_at") for row in materialized if row.get("updated_at")]
    data_as_of = max(data_as_of_values) if data_as_of_values else None
    summaries: list[dict[str, Any]] = []

    for metric_key in metric_keys:
        definition = get_indicator_definition(metric_key)
        bucket_values = {
            bucket.key: {"parcelCount": 0, "areaMu": 0.0}
            for bucket in definition.buckets
        }
        values: list[tuple[float, float]] = []
        unclassified_count = 0
        unclassified_area = 0.0

        for row in materialized:
            indicators = _json_object(row.get("soil_indicators"))
            assessment = business_result(_json_object(row.get("assessment_result")))
            # Computed fields have one publication source.  Missing assessment
            # stays unclassified; never silently fall back to imported grades.
            if definition.source_field in {"quality_grade", "composite_index"}:
                indicators[definition.source_field] = assessment.get(definition.source_field)
            parsed = definition.parse(indicators.get(definition.source_field))
            area_mu = max(float(row.get("area_mu") or 0), 0)
            bucket = definition.classify(parsed)
            if parsed is None or bucket is None:
                unclassified_count += 1
                unclassified_area += area_mu
                continue
            values.append((parsed, area_mu))
            bucket_values[bucket.key]["parcelCount"] += 1
            bucket_values[bucket.key]["areaMu"] += area_mu

        valid_count = len(values)
        valid_area = sum(area for _, area in values)
        weighted_sum = sum(value * area for value, area in values)
        weighted_average = weighted_sum / valid_area if valid_area > 0 else None
        raw_values = [value for value, _ in values]

        buckets = []
        for bucket in definition.buckets:
            aggregate = bucket_values[bucket.key]
            count = aggregate["parcelCount"]
            area = aggregate["areaMu"]
            buckets.append({
                **bucket.as_dict(),
                "parcelCount": count,
                "areaMu": _round(area),
                "countPercent": _round(count * 100 / valid_count) if valid_count else 0.0,
                "areaPercent": _round(area * 100 / valid_area) if valid_area else 0.0,
            })

        summaries.append({
            "key": definition.key,
            "label": definition.label,
            "unit": definition.unit,
            "table": {
                "average": _round(weighted_average, definition.decimals),
                "totalAreaMu": _round(total_area),
                "parcelCount": len(materialized),
                "validAreaMu": _round(valid_area),
                "validParcelCount": valid_count,
                "range": {
                    "min": _round(min(raw_values), definition.decimals) if raw_values else None,
                    "max": _round(max(raw_values), definition.decimals) if raw_values else None,
                },
            },
            # One ordered series serves the horizontal bars and pie slices.
            "distribution": buckets,
            "unclassified": {
                "parcelCount": unclassified_count,
                "areaMu": _round(unclassified_area),
            },
        })

    return {
        "dataAsOf": _isoformat(data_as_of),
        "scopeSummary": {
            "parcelCount": len(materialized),
            "totalAreaMu": _round(total_area),
        },
        "metrics": summaries,
    }


def _metric_keys(payload: Mapping[str, Any]) -> list[str]:
    requested = payload.get("metrics", "all")
    if requested == "all" or requested is None:
        return list(INDICATOR_DEFINITIONS)
    if not isinstance(requested, list) or not requested:
        raise StatisticsError("invalid_metrics", "metrics 必须为 all 或非空指标数组")
    unknown = [key for key in requested if key not in INDICATOR_DEFINITIONS]
    if unknown:
        raise StatisticsError("invalid_metrics", f"不支持的统计指标: {', '.join(map(str, unknown))}")
    return list(dict.fromkeys(requested))


def _scope_sql(scope: Mapping[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    scope_type = scope.get("type")
    if scope_type == "administrative_region":
        region_type = str(scope.get("region_type") or "")
        region_id = str(scope.get("region_id") or "")
        if region_type not in REGION_TYPES or not region_id:
            raise StatisticsError("invalid_scope", "行政区域必须包含有效的 region_type 和 region_id")
        try:
            exists = db.session.execute(sa.text("""
                SELECT display_name, geom IS NOT NULL AS has_geom
                FROM spatial_region_catalog
                WHERE object_type = :region_type AND object_id = :region_id AND enabled = TRUE
                LIMIT 1
            """), {"region_type": region_type, "region_id": region_id}).mappings().first()
        except sa.exc.SQLAlchemyError as exc:
            raise StatisticsError("statistics_unavailable", "区域目录服务暂时不可用", 503) from exc
        if exists is None:
            raise StatisticsError("region_not_found", "指定行政区域不存在或未启用", 404)
        if not exists["has_geom"]:
            raise StatisticsError("region_geometry_missing", "指定行政区域尚未导入边界", 409)
        return (
            """SELECT geom FROM spatial_region_catalog
               WHERE object_type = :region_type AND object_id = :region_id
                 AND enabled = TRUE AND geom IS NOT NULL LIMIT 1""",
            {"region_type": region_type, "region_id": region_id},
            {
                "type": scope_type,
                "regionType": region_type,
                "regionId": region_id,
                "displayName": exists["display_name"],
            },
        )

    if scope_type == "viewport":
        bbox = scope.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise StatisticsError("invalid_scope", "viewport.bbox 必须为 [minLon,minLat,maxLon,maxLat]")
        try:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox)
        except (TypeError, ValueError) as exc:
            raise StatisticsError("invalid_scope", "viewport.bbox 坐标必须为数字") from exc
        if not all(map(math.isfinite, (min_lon, min_lat, max_lon, max_lat))):
            raise StatisticsError("invalid_scope", "viewport.bbox 坐标必须为有限数字")
        if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
            raise StatisticsError("invalid_scope", "viewport.bbox 范围或顺序无效")
        return (
            "SELECT ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326) AS geom",
            {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat},
            {"type": scope_type, "bbox": [min_lon, min_lat, max_lon, max_lat], "srid": 4326},
        )

    raise StatisticsError("invalid_scope", "scope.type 仅支持 administrative_region 或 viewport")


def _live_statistics_sql(scope_query: str) -> sa.TextClause:
    """Build the spatial fallback query while evaluating each clip only once."""
    return sa.text(f"""
        WITH scope AS MATERIALIZED ({scope_query}),
        clipped AS MATERIALIZED (
            SELECT p.parcel_id, p.area_code, p.soil_indicators, p.updated_at,
                   assessment.result_payload AS assessment_result,
                   assessment.calculated_at AS assessment_calculated_at,
                   CASE
                     WHEN ST_CoveredBy(p.geom, scope.geom) THEN p.geom
                     ELSE ST_Intersection(p.geom, scope.geom)
                   END AS clipped_geom
            FROM parcel_info AS p
            CROSS JOIN scope
            LEFT JOIN versioned_model_result AS assessment
              ON assessment.agent_id = 'model-2'
             AND assessment.subject_type = 'parcel'
             AND assessment.subject_id = p.parcel_id
             AND assessment.is_current = TRUE
            WHERE p.geom IS NOT NULL
              AND p.geom && scope.geom
              AND ST_Intersects(p.geom, scope.geom)
        ),
        measured AS MATERIALIZED (
            SELECT parcel_id, area_code, soil_indicators, updated_at,
                   assessment_result, assessment_calculated_at,
                   ST_Area(clipped_geom::geography) * :mu_per_sqm AS area_mu
            FROM clipped
            WHERE NOT ST_IsEmpty(clipped_geom)
        )
        SELECT parcel_id, area_code, soil_indicators, updated_at,
               assessment_result, assessment_calculated_at, area_mu
        FROM measured
        WHERE area_mu > 0
        ORDER BY parcel_id
    """)


def _precomputed_statistics_rows(
    scope_response: Mapping[str, Any],
) -> list[Mapping[str, Any]] | None:
    """Return fresh precomputed rows, or ``None`` when live fallback is needed."""
    if scope_response.get("type") != "administrative_region":
        return None
    if db.engine.dialect.name != "postgresql":
        return None

    tables = db.session.execute(sa.text("""
        SELECT to_regclass('farmland_region_parcel_area') AS area_table,
               to_regclass('farmland_region_precompute_state') AS state_table
    """)).mappings().one()
    if tables["area_table"] is None or tables["state_table"] is None:
        return None

    params = {
        "region_type": scope_response["regionType"],
        "region_id": scope_response["regionId"],
    }
    state = db.session.execute(sa.text("""
        WITH parcel_source AS (
            SELECT COUNT(*)::integer AS parcel_count,
                   MAX(updated_at) AS parcel_max_updated_at
            FROM parcel_info
            WHERE geom IS NOT NULL
        )
        SELECT state.relation_count
        FROM farmland_region_precompute_state AS state
        JOIN spatial_region_catalog AS region
          ON region.object_type = state.region_type
         AND region.object_id = state.region_id
         AND region.enabled = TRUE
        CROSS JOIN parcel_source
        WHERE state.region_type = :region_type
          AND state.region_id = :region_id
          AND state.region_updated_at IS NOT DISTINCT FROM region.updated_at
          AND state.source_parcel_count = parcel_source.parcel_count
          AND state.source_parcel_max_updated_at IS NOT DISTINCT FROM parcel_source.parcel_max_updated_at
    """), params).mappings().first()
    if state is None:
        return None

    rows = db.session.execute(sa.text("""
        SELECT parcel.parcel_id, parcel.area_code, parcel.soil_indicators,
               parcel.updated_at, cached.area_mu,
               assessment.result_payload AS assessment_result,
               assessment.calculated_at AS assessment_calculated_at
        FROM farmland_region_parcel_area AS cached
        JOIN parcel_info AS parcel ON parcel.parcel_id = cached.parcel_id
        LEFT JOIN versioned_model_result AS assessment
          ON assessment.agent_id = 'model-2'
         AND assessment.subject_type = 'parcel'
         AND assessment.subject_id = parcel.parcel_id
         AND assessment.is_current = TRUE
        WHERE cached.region_type = :region_type
          AND cached.region_id = :region_id
          AND cached.area_mu > 0
        ORDER BY parcel.parcel_id
    """), params).mappings().all()
    if len(rows) != state["relation_count"]:
        return None
    return rows


def aggregate_statistics(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise StatisticsError("invalid_request", "请求体必须为 JSON 对象")
    scope = payload.get("scope")
    if not isinstance(scope, Mapping):
        raise StatisticsError("invalid_scope", "请求必须包含 scope 对象")
    metric_keys = _metric_keys(payload)
    scope_query, params, scope_response = _scope_sql(scope)
    try:
        rows = _precomputed_statistics_rows(scope_response)
        if rows is None:
            params["mu_per_sqm"] = MU_PER_SQUARE_METRE
            rows = db.session.execute(
                _live_statistics_sql(scope_query), params
            ).mappings().all()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "空间统计服务暂时不可用", 503) from exc
    result = summarize_rows(rows, metric_keys)
    result["scope"] = scope_response
    return result


def list_regions(
    parent_type: str | None = None,
    parent_id: str | None = None,
    include_disputes: bool = False,
) -> list[dict[str, Any]]:
    query = db.session.query(
        SpatialRegionCatalog.object_type,
        SpatialRegionCatalog.object_id,
        SpatialRegionCatalog.display_name,
        SpatialRegionCatalog.area_code,
        SpatialRegionCatalog.parent_object_type,
        SpatialRegionCatalog.parent_object_id,
        SpatialRegionCatalog.metadata_json,
        SpatialRegionCatalog.geom.isnot(None).label("has_geometry"),
    ).filter(SpatialRegionCatalog.enabled.is_(True))
    if bool(parent_type) != bool(parent_id):
        raise StatisticsError("invalid_parent", "parent_type 与 parent_id 必须同时提供")
    if parent_type:
        if parent_type not in REGION_TYPES:
            raise StatisticsError("invalid_parent", "parent_type 无效")
        query = query.filter(
            SpatialRegionCatalog.parent_object_type == parent_type,
            SpatialRegionCatalog.parent_object_id == parent_id,
        )
    if not include_disputes:
        query = query.filter(SpatialRegionCatalog.object_type != "zone")
    rows = query.order_by(SpatialRegionCatalog.object_type, SpatialRegionCatalog.object_id).all()
    return [{
        "regionType": row.object_type,
        "regionId": row.object_id,
        "displayName": row.display_name,
        "areaCode": row.area_code,
        "parentType": row.parent_object_type,
        "parentId": row.parent_object_id,
        "selectable": bool((row.metadata_json or {}).get("selectable", True)),
        "hasGeometry": bool(row.has_geometry),
    } for row in rows]


def _parcel_area_mu(parcel_id: str) -> float | None:
    try:
        area_mu = db.session.execute(sa.text("""
            SELECT CASE
                     WHEN geom IS NULL THEN NULL
                     ELSE ST_Area(geom::geography) * :mu_per_sqm
                   END AS area_mu
            FROM parcel_info
            WHERE parcel_id = :parcel_id
            LIMIT 1
        """), {
            "parcel_id": parcel_id,
            "mu_per_sqm": MU_PER_SQUARE_METRE,
        }).scalar()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "地块面积服务暂时不可用", 503) from exc
    return None if area_mu is None else float(area_mu)


def _calculated_grade(parcel: ParcelInfo) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ensure and return the one Model-2 row shared with the agent."""
    from framework.agents.specialized.grade_agent import FarmlandGradeAgent

    execution = FarmlandGradeAgent().execute({
        "parcel_id": parcel.parcel_id,
        "area_code": parcel.area_code,
    })
    return business_result(execution), dict(execution.get("versioned_result") or {})


def _parcel_response(
    parcel: ParcelInfo,
    area_mu: float | None,
    assessment: Mapping[str, Any] | None = None,
    version: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    indicators = parcel.soil_indicators or {}
    calculated = dict(assessment or {})
    return {
        "parcelId": parcel.parcel_id,
        "areaCode": parcel.area_code,
        "areaMu": _round(area_mu),
        "qualityGrade": calculated.get("quality_grade"),
        "compositeIndex": _round(calculated.get("composite_index")),
        "qualityAssessment": dict(version or {}),
        "organicMatter": indicators.get("organic_matter"),
        "soilPh": indicators.get("soil_ph"),
        "availablePhosphorus": indicators.get("available_phosphorus"),
    }


def get_parcel_summary(parcel_id: str) -> dict[str, Any]:
    parcel = ParcelInfo.query.filter_by(parcel_id=parcel_id).first()
    if parcel is None:
        raise StatisticsError("parcel_not_found", "地块不存在", 404)
    assessment, version = _calculated_grade(parcel)
    return _parcel_response(parcel, _parcel_area_mu(parcel.parcel_id), assessment, version)


def pick_parcel(longitude: Any, latitude: Any) -> dict[str, Any]:
    try:
        lon, lat = float(longitude), float(latitude)
    except (TypeError, ValueError) as exc:
        raise StatisticsError("invalid_coordinate", "经纬度必须为数字") from exc
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise StatisticsError("invalid_coordinate", "经纬度范围无效")
    try:
        selected = db.session.execute(sa.text("""
            SELECT parcel_id,
                   ST_Area(geom::geography) * :mu_per_sqm AS area_mu
            FROM parcel_info
            WHERE geom IS NOT NULL
              AND ST_Covers(geom, ST_SetSRID(ST_Point(:lon, :lat), 4326))
            ORDER BY ST_Area(geom::geography), parcel_id
            LIMIT 1
        """), {
            "lon": lon,
            "lat": lat,
            "mu_per_sqm": MU_PER_SQUARE_METRE,
        }).mappings().first()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "地块点选服务暂时不可用", 503) from exc
    parcel = ParcelInfo.query.filter_by(parcel_id=selected["parcel_id"]).first() if selected else None
    if parcel is None:
        raise StatisticsError("parcel_not_found", "该位置未命中地块", 404)
    assessment, version = _calculated_grade(parcel)
    return _parcel_response(parcel, float(selected["area_mu"]), assessment, version)
