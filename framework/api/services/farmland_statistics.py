"""Versioned spatial statistics, region, boundary and parcel query services."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from framework.domain.statistics import (
    CLASSIFICATION_VERSION,
    INDICATOR_DEFINITIONS,
    INDICATOR_GROUPS,
    get_indicator_definition,
)
from framework.models import ParcelInfo, SpatialRegionCatalog, db


MU_PER_SQUARE_METRE = 1.0 / 666.6666666666666
SCOPE_VERSION = 1
REGION_TYPES = {"province", "city", "county", "township", "village", "zone"}
BOUNDARY_MIN_ZOOM = {
    "province": 3, "city": 5, "county": 7,
    "township": 9, "village": 12, "zone": 12,
}
MAX_BOUNDARY_FEATURES = 5000
MAX_PARCEL_QUERY_LIMIT = 500


class StatisticsError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


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


def _row_indicators(row: Mapping[str, Any]) -> dict[str, Any]:
    indicators = _json_object(row.get("soil_indicators"))
    if row.get("quality_grade") is not None:
        indicators["quality_grade"] = row["quality_grade"]
    if row.get("composite_index") is not None:
        indicators["composite_index"] = row["composite_index"]
    return indicators


def _catalog_rows() -> list[Mapping[str, Any]] | None:
    """Return annual snapshots, or ``None`` when the metadata DB is unavailable."""
    try:
        return db.session.execute(sa.text("""
            SELECT survey_year AS data_year, soil_indicators, quality_grade, composite_index
            FROM parcel_history_snapshot
            ORDER BY survey_year, parcel_id
        """)).mappings().all()
    except (sa.exc.SQLAlchemyError, RuntimeError):
        return None


def _year_summaries(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[int] = Counter()
    for row in rows:
        year = row.get("data_year")
        if isinstance(year, int):
            counts[year] += 1
    return [
        {"year": year, "parcelCount": counts[year], "selectable": True}
        for year in sorted(counts, reverse=True)
    ]


def metric_metadata() -> dict[str, Any]:
    """Return grouped metric metadata with observed availability by data year."""
    rows = _catalog_rows()
    years = _year_summaries(rows or [])
    counts: dict[str, Counter[int]] = {key: Counter() for key in INDICATOR_DEFINITIONS}
    totals: Counter[int] = Counter()
    if rows is not None:
        for row in rows:
            year = row.get("data_year")
            if not isinstance(year, int):
                continue
            totals[year] += 1
            indicators = _row_indicators(row)
            for key, definition in INDICATOR_DEFINITIONS.items():
                if definition.parse(definition.value_from(indicators)) is not None:
                    counts[key][year] += 1

    group_order = {group.key: group.order for group in INDICATOR_GROUPS}
    metrics = []
    for definition in sorted(
        INDICATOR_DEFINITIONS.values(),
        key=lambda item: (group_order[item.group_key], item.order),
    ):
        observed = counts[definition.key]
        data_years = sorted(observed, reverse=True)
        observed_count = sum(observed.values())
        possible_count = sum(totals.values())
        if rows is None:
            availability = "unknown"
        elif observed_count == 0:
            availability = "unavailable"
        elif possible_count and observed_count < possible_count:
            availability = "partial"
        else:
            availability = "available"
        metrics.append({
            **definition.as_dict(),
            "metricKey": definition.key,
            "classificationVersion": CLASSIFICATION_VERSION,
            "availability": availability,
            "dataYears": data_years,
            "coverageByYear": {
                str(year): {
                    "valueCount": observed[year],
                    "parcelCount": totals[year],
                    "percent": _round(observed[year] * 100 / totals[year], 2) if totals[year] else 0.0,
                }
                for year in data_years
            },
        })

    group_metrics: dict[str, list[str]] = {group.key: [] for group in INDICATOR_GROUPS}
    for metric in metrics:
        group_metrics[metric["groupKey"]].append(metric["metricKey"])
    groups = [
        {**group.as_dict(), "metrics": group_metrics[group.key]}
        for group in sorted(INDICATOR_GROUPS, key=lambda item: item.order)
    ]
    return {
        "classificationVersion": CLASSIFICATION_VERSION,
        "groups": groups,
        "metrics": metrics,
        "availableYears": years,
        "defaultYear": years[0]["year"] if years else None,
    }


def list_available_years() -> dict[str, Any]:
    try:
        rows = db.session.execute(sa.text("""
            SELECT survey_year AS year, COUNT(*) AS parcel_count
            FROM parcel_history_snapshot
            GROUP BY survey_year
            ORDER BY survey_year DESC
        """)).mappings().all()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "数据年份服务暂时不可用", 503) from exc
    years = [
        {"year": int(row["year"]), "parcelCount": int(row["parcel_count"]), "selectable": True}
        for row in rows
    ]
    return {"years": years, "defaultYear": years[0]["year"] if years else None}


def _resolve_year(value: Any) -> int | None:
    available = list_available_years()
    selectable = {item["year"] for item in available["years"]}
    if value in (None, ""):
        return available["defaultYear"]
    if isinstance(value, bool):
        raise StatisticsError("invalid_year", "year 必须为四位年份")
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise StatisticsError("invalid_year", "year 必须为四位年份") from exc
    if year < 1900 or year > 2100:
        raise StatisticsError("invalid_year", "year 必须为 1900 到 2100 之间的四位年份")
    if year not in selectable:
        raise StatisticsError("year_not_available", f"年份 {year} 没有可用地块数据", 404)
    return year


def summarize_rows(
    rows: Iterable[Mapping[str, Any]],
    metric_keys: Iterable[str],
    *,
    data_year: int | None = None,
) -> dict[str, Any]:
    """Build area-weighted numeric and area/count categorical summaries."""
    materialized = [dict(row) for row in rows]
    total_area = sum(max(float(row.get("area_mu") or 0), 0) for row in materialized)
    data_as_of_values = [row.get("updated_at") for row in materialized if row.get("updated_at")]
    data_as_of = max(data_as_of_values) if data_as_of_values else None
    summaries: list[dict[str, Any]] = []

    for metric_key in metric_keys:
        definition = get_indicator_definition(metric_key)
        numeric_values: list[tuple[float, float]] = []
        category_values: Counter[str] = Counter()
        category_areas: Counter[str] = Counter()
        bucket_values = {
            bucket.key: {"parcelCount": 0, "areaMu": 0.0}
            for bucket in definition.buckets
        }
        unclassified_count = 0
        unclassified_area = 0.0

        for row in materialized:
            indicators = _row_indicators(row)
            parsed = definition.parse(definition.value_from(indicators))
            area_mu = max(float(row.get("area_mu") or 0), 0)
            if parsed is None:
                unclassified_count += 1
                unclassified_area += area_mu
                continue
            if definition.value_type == "category":
                category = str(parsed)
                category_values[category] += 1
                category_areas[category] += area_mu
                continue
            numeric = float(parsed)
            if definition.buckets:
                bucket = definition.classify(numeric)
                if bucket is None:
                    unclassified_count += 1
                    unclassified_area += area_mu
                    continue
                else:
                    bucket_values[bucket.key]["parcelCount"] += 1
                    bucket_values[bucket.key]["areaMu"] += area_mu
            numeric_values.append((numeric, area_mu))

        valid_count = len(numeric_values) + sum(category_values.values())
        valid_area = sum(area for _, area in numeric_values) + sum(category_areas.values())
        if definition.value_type == "category":
            distribution = [
                {
                    "key": value, "label": value, "rangeLabel": value, "color": None,
                    "parcelCount": category_values[value],
                    "areaMu": _round(category_areas[value]),
                    "countPercent": _round(category_values[value] * 100 / valid_count) if valid_count else 0.0,
                    "areaPercent": _round(category_areas[value] * 100 / valid_area) if valid_area else 0.0,
                }
                for value in sorted(category_values)
            ]
            average = None
            value_range = {"min": None, "max": None}
        else:
            weighted_sum = sum(value * area for value, area in numeric_values)
            average = weighted_sum / valid_area if valid_area > 0 else None
            raw_values = [value for value, _ in numeric_values]
            value_range = {
                "min": _round(min(raw_values), definition.decimals) if raw_values else None,
                "max": _round(max(raw_values), definition.decimals) if raw_values else None,
            }
            distribution = []
            for bucket in definition.buckets:
                aggregate = bucket_values[bucket.key]
                count = aggregate["parcelCount"]
                area = aggregate["areaMu"]
                distribution.append({
                    **bucket.as_dict(),
                    "parcelCount": count,
                    "areaMu": _round(area),
                    "countPercent": _round(count * 100 / valid_count) if valid_count else 0.0,
                    "areaPercent": _round(area * 100 / valid_area) if valid_area else 0.0,
                })

        summaries.append({
            "key": definition.key,
            "metricKey": definition.key,
            "label": definition.label,
            "unit": definition.unit,
            "groupKey": definition.group_key,
            "order": definition.order,
            "valueType": definition.value_type,
            "dataYear": data_year,
            "table": {
                "average": _round(average, definition.decimals),
                "totalAreaMu": _round(total_area),
                "parcelCount": len(materialized),
                "validAreaMu": _round(valid_area),
                "validParcelCount": valid_count,
                "range": value_range,
            },
            "distribution": distribution,
            "unclassified": {
                "parcelCount": unclassified_count,
                "areaMu": _round(unclassified_area),
            },
        })

    return {
        "classificationVersion": CLASSIFICATION_VERSION,
        "dataYear": data_year,
        "dataAsOf": _isoformat(data_as_of),
        "scopeSummary": {"parcelCount": len(materialized), "totalAreaMu": _round(total_area)},
        "metrics": summaries,
    }


def _metric_keys(payload: Mapping[str, Any]) -> list[str]:
    requested = payload.get("metrics", "all")
    if requested == "all" or requested is None:
        group_order = {group.key: group.order for group in INDICATOR_GROUPS}
        return [
            item.key for item in sorted(
                INDICATOR_DEFINITIONS.values(),
                key=lambda item: (group_order[item.group_key], item.order),
            )
        ]
    if not isinstance(requested, list) or not requested:
        raise StatisticsError("invalid_metrics", "metrics 必须为 all 或非空指标数组")
    unknown = [key for key in requested if key not in INDICATOR_DEFINITIONS]
    if unknown:
        raise StatisticsError("invalid_metrics", f"不支持的统计指标: {', '.join(map(str, unknown))}")
    return list(dict.fromkeys(requested))


def _parse_bbox(value: Any, field_name: str = "bbox") -> list[float] | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise StatisticsError("invalid_bbox", f"{field_name} 必须为 [minLon,minLat,maxLon,maxLat]")
    try:
        min_lon, min_lat, max_lon, max_lat = map(float, value)
    except (TypeError, ValueError) as exc:
        raise StatisticsError("invalid_bbox", f"{field_name} 坐标必须为数字") from exc
    if not all(map(math.isfinite, (min_lon, min_lat, max_lon, max_lat))):
        raise StatisticsError("invalid_bbox", f"{field_name} 坐标必须为有限数字")
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise StatisticsError("invalid_bbox", f"{field_name} 范围或顺序无效")
    return [min_lon, min_lat, max_lon, max_lat]


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
                "scopeVersion": SCOPE_VERSION, "type": scope_type,
                "regionType": region_type, "regionId": region_id,
                "displayName": exists["display_name"],
            },
        )

    if scope_type == "viewport":
        try:
            bbox = _parse_bbox(scope.get("bbox"), "viewport.bbox")
        except StatisticsError as exc:
            raise StatisticsError("invalid_scope", exc.message) from exc
        if bbox is None:
            raise StatisticsError("invalid_scope", "viewport.bbox 必须为 [minLon,minLat,maxLon,maxLat]")
        min_lon, min_lat, max_lon, max_lat = bbox
        return (
            "SELECT ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326) AS geom",
            {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat},
            {"scopeVersion": SCOPE_VERSION, "type": scope_type, "bbox": bbox, "srid": 4326},
        )

    if scope_type == "parcel":
        parcel_id = str(scope.get("parcel_id") or scope.get("parcelId") or "")
        if not parcel_id:
            raise StatisticsError("invalid_scope", "地块范围必须包含 parcel_id")
        try:
            exists = db.session.execute(sa.text("""
                SELECT area_code, geom IS NOT NULL AS has_geom
                FROM parcel_info WHERE parcel_id = :parcel_id LIMIT 1
            """), {"parcel_id": parcel_id}).mappings().first()
        except sa.exc.SQLAlchemyError as exc:
            raise StatisticsError("statistics_unavailable", "地块服务暂时不可用", 503) from exc
        if exists is None:
            raise StatisticsError("parcel_not_found", "地块不存在", 404)
        if not exists["has_geom"]:
            raise StatisticsError("parcel_geometry_missing", "地块尚未导入几何", 409)
        return (
            "SELECT geom FROM parcel_info WHERE parcel_id = :scope_parcel_id AND geom IS NOT NULL LIMIT 1",
            {"scope_parcel_id": parcel_id},
            {
                "scopeVersion": SCOPE_VERSION, "type": scope_type,
                "parcelId": parcel_id, "areaCode": exists["area_code"],
            },
        )

    raise StatisticsError("invalid_scope", "scope.type 仅支持 administrative_region、viewport 或 parcel")


def _dataset_sql(year: int | None) -> tuple[str, dict[str, Any]]:
    if year is None:
        return (
            """SELECT p.id AS parcel_pk, p.parcel_id, p.area_code, p.geom,
                      p.soil_indicators, NULL::text AS quality_grade,
                      NULL::double precision AS composite_index, p.updated_at
               FROM parcel_info AS p""",
            {},
        )
    return (
        """SELECT p.id AS parcel_pk, p.parcel_id, p.area_code, p.geom,
                  h.soil_indicators, h.quality_grade, h.composite_index,
                  h.created_at AS updated_at
           FROM parcel_info AS p
           JOIN parcel_history_snapshot AS h ON h.parcel_id = p.parcel_id
           WHERE h.survey_year = :data_year""",
        {"data_year": year},
    )


def aggregate_statistics(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise StatisticsError("invalid_request", "请求体必须为 JSON 对象")
    scope = payload.get("scope")
    if not isinstance(scope, Mapping):
        raise StatisticsError("invalid_scope", "请求必须包含 scope 对象")
    year = _resolve_year(payload.get("year"))
    metric_keys = _metric_keys(payload)
    scope_query, scope_params, scope_response = _scope_sql(scope)
    dataset_query, dataset_params = _dataset_sql(year)
    sql = sa.text(f"""
        WITH scope AS MATERIALIZED ({scope_query}),
        data AS MATERIALIZED ({dataset_query}),
        scoped AS (
            SELECT data.parcel_id, data.area_code, data.soil_indicators,
                   data.quality_grade, data.composite_index, data.updated_at,
                   ST_Intersection(data.geom, scope.geom) AS clipped_geom
            FROM data CROSS JOIN scope
            WHERE data.geom IS NOT NULL
              AND data.geom && scope.geom
              AND ST_Intersects(data.geom, scope.geom)
        )
        SELECT parcel_id, area_code, soil_indicators, quality_grade,
               composite_index, updated_at,
               ST_Area(clipped_geom::geography) * :mu_per_sqm AS area_mu
        FROM scoped
        WHERE NOT ST_IsEmpty(clipped_geom)
          AND ST_Area(clipped_geom::geography) > 0
        ORDER BY parcel_id
    """)
    params = {**scope_params, **dataset_params, "mu_per_sqm": MU_PER_SQUARE_METRE}
    try:
        rows = db.session.execute(sql, params).mappings().all()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "空间统计服务暂时不可用", 503) from exc
    result = summarize_rows(rows, metric_keys, data_year=year)
    result["scope"] = scope_response
    return result


def list_regions(
    parent_type: str | None = None,
    parent_id: str | None = None,
    include_disputes: bool = False,
) -> list[dict[str, Any]]:
    query = db.session.query(
        SpatialRegionCatalog.object_type, SpatialRegionCatalog.object_id,
        SpatialRegionCatalog.display_name, SpatialRegionCatalog.area_code,
        SpatialRegionCatalog.parent_object_type, SpatialRegionCatalog.parent_object_id,
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
        "regionType": row.object_type, "regionId": row.object_id,
        "displayName": row.display_name, "areaCode": row.area_code,
        "parentType": row.parent_object_type, "parentId": row.parent_object_id,
        "selectable": bool((row.metadata_json or {}).get("selectable", True)),
        "hasGeometry": bool(row.has_geometry),
    } for row in rows]


def list_boundaries(
    region_type: str | None,
    parent_type: str | None = None,
    parent_id: str | None = None,
    bbox: Any = None,
    zoom: Any = None,
) -> dict[str, Any]:
    region_type = str(region_type or "")
    if region_type not in REGION_TYPES:
        raise StatisticsError("invalid_region_type", "region_type 无效")
    if bool(parent_type) != bool(parent_id):
        raise StatisticsError("invalid_parent", "parent_type 与 parent_id 必须同时提供")
    if parent_type and parent_type not in REGION_TYPES:
        raise StatisticsError("invalid_parent", "parent_type 无效")
    parsed_bbox = _parse_bbox(bbox)
    parsed_zoom: float | None = None
    if zoom not in (None, ""):
        try:
            parsed_zoom = float(zoom)
        except (TypeError, ValueError) as exc:
            raise StatisticsError("invalid_zoom", "zoom 必须为 0 到 24 之间的数字") from exc
        if not math.isfinite(parsed_zoom) or not 0 <= parsed_zoom <= 24:
            raise StatisticsError("invalid_zoom", "zoom 必须为 0 到 24 之间的数字")

    min_zoom = BOUNDARY_MIN_ZOOM[region_type]
    base = {
        "type": "FeatureCollection", "regionType": region_type,
        "minZoom": min_zoom, "maxZoom": None, "zoom": parsed_zoom, "bbox": parsed_bbox,
    }
    if parsed_zoom is not None and parsed_zoom < min_zoom:
        return {**base, "suppressedByZoom": True, "truncated": False, "features": []}

    conditions = ["object_type = :region_type", "enabled = TRUE", "geom IS NOT NULL"]
    params: dict[str, Any] = {
        "region_type": region_type,
        "limit": MAX_BOUNDARY_FEATURES + 1,
        "tolerance": 0.0 if parsed_zoom is None else 360.0 / (256.0 * 2 ** parsed_zoom) * 0.25,
    }
    if parent_type:
        conditions.extend(["parent_object_type = :parent_type", "parent_object_id = :parent_id"])
        params.update(parent_type=parent_type, parent_id=str(parent_id))
    if parsed_bbox:
        conditions.extend([
            "geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)",
            "ST_Intersects(geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))",
        ])
        params.update(zip(("min_lon", "min_lat", "max_lon", "max_lat"), parsed_bbox))
    sql = sa.text(f"""
        SELECT object_type, object_id, display_name, area_code,
               parent_object_type, parent_object_id, metadata,
               ST_AsGeoJSON(CASE WHEN :tolerance > 0
                   THEN ST_SimplifyPreserveTopology(geom, :tolerance) ELSE geom END) AS geometry
        FROM spatial_region_catalog
        WHERE {' AND '.join(conditions)}
        ORDER BY object_id LIMIT :limit
    """)
    try:
        rows = db.session.execute(sql, params).mappings().all()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "行政边界服务暂时不可用", 503) from exc
    truncated = len(rows) > MAX_BOUNDARY_FEATURES
    features = []
    for row in rows[:MAX_BOUNDARY_FEATURES]:
        metadata = _json_object(row["metadata"])
        geometry = row["geometry"]
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        features.append({
            "type": "Feature", "id": f"{row['object_type']}:{row['object_id']}",
            "properties": {
                "regionType": row["object_type"], "regionId": row["object_id"],
                "displayName": row["display_name"], "areaCode": row["area_code"],
                "parentType": row["parent_object_type"], "parentId": row["parent_object_id"],
                "selectable": bool(metadata.get("selectable", True)),
                "minZoom": min_zoom, "maxZoom": None,
            },
            "geometry": geometry,
        })
    return {**base, "suppressedByZoom": False, "truncated": truncated, "features": features}


def _metric_response(metric_key: str, indicators: Mapping[str, Any]) -> dict[str, Any]:
    definition = get_indicator_definition(metric_key)
    value = definition.parse(definition.value_from(dict(indicators)))
    bucket = definition.classify(value)
    if isinstance(value, float):
        value = _round(value, definition.decimals)
    return {
        "metricKey": definition.key, "label": definition.label,
        "groupKey": definition.group_key, "valueType": definition.value_type,
        "value": value, "unit": definition.unit,
        "bucketKey": bucket.key if bucket else None,
        "bucketLabel": bucket.label if bucket else None,
        "rangeLabel": bucket.range_label if bucket else None,
        "color": bucket.color if bucket else None,
    }


def _parcel_payload(
    parcel_id: str,
    area_code: str | None,
    indicators: Mapping[str, Any],
    area_mu: float | None,
    data_year: int | None,
    metric_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    keys = list(metric_keys) if metric_keys is not None else _metric_keys({"metrics": "all"})
    metrics = {key: _metric_response(key, indicators) for key in keys}
    response = {
        "classificationVersion": CLASSIFICATION_VERSION,
        "parcelId": parcel_id, "areaCode": area_code,
        "areaMu": _round(area_mu), "dataYear": data_year, "metrics": metrics,
    }
    for legacy_key, metric_key in (
        ("qualityGrade", "quality_grade"), ("organicMatter", "organic_matter"),
        ("soilPh", "soil_ph"), ("availablePhosphorus", "available_phosphorus"),
    ):
        if metric_key in metrics:
            response[legacy_key] = metrics[metric_key]["value"]
    return response


def _parcel_response(
    parcel: ParcelInfo,
    area_mu: float | None,
    data_year: int | None = None,
    metric_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    indicators = _json_object(parcel.soil_indicators)
    if getattr(parcel, "quality_grade", None) is not None:
        indicators["quality_grade"] = parcel.quality_grade
    if getattr(parcel, "composite_index", None) is not None:
        indicators["composite_index"] = parcel.composite_index
    return _parcel_payload(parcel.parcel_id, parcel.area_code, indicators, area_mu, data_year, metric_keys)


def get_parcel_summary(parcel_id: str, year: Any = None) -> dict[str, Any]:
    data_year = _resolve_year(year)
    if data_year is None:
        parcel = ParcelInfo.query.filter_by(parcel_id=parcel_id).first()
        if parcel is None:
            raise StatisticsError("parcel_not_found", "地块不存在", 404)
        area_mu = db.session.execute(sa.text("""
            SELECT CASE WHEN geom IS NULL THEN NULL
                        ELSE ST_Area(geom::geography) * :mu_per_sqm END
            FROM parcel_info WHERE parcel_id = :parcel_id LIMIT 1
        """), {"parcel_id": parcel_id, "mu_per_sqm": MU_PER_SQUARE_METRE}).scalar()
        return _parcel_response(parcel, None if area_mu is None else float(area_mu), None)
    try:
        row = db.session.execute(sa.text("""
            SELECT p.parcel_id, p.area_code, h.soil_indicators, h.quality_grade,
                   h.composite_index,
                   CASE WHEN p.geom IS NULL THEN NULL
                        ELSE ST_Area(p.geom::geography) * :mu_per_sqm END AS area_mu
            FROM parcel_info AS p
            JOIN parcel_history_snapshot AS h ON h.parcel_id = p.parcel_id
            WHERE p.parcel_id = :parcel_id AND h.survey_year = :data_year
            LIMIT 1
        """), {
            "parcel_id": parcel_id, "data_year": data_year,
            "mu_per_sqm": MU_PER_SQUARE_METRE,
        }).mappings().first()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "地块详情服务暂时不可用", 503) from exc
    if row is None:
        raise StatisticsError("parcel_year_not_found", f"地块在 {data_year} 年没有可用数据", 404)
    return _parcel_payload(
        row["parcel_id"], row["area_code"], _row_indicators(row),
        None if row["area_mu"] is None else float(row["area_mu"]), data_year,
    )


def pick_parcel(longitude: Any, latitude: Any, year: Any = None) -> dict[str, Any]:
    try:
        lon, lat = float(longitude), float(latitude)
    except (TypeError, ValueError) as exc:
        raise StatisticsError("invalid_coordinate", "经纬度必须为数字") from exc
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise StatisticsError("invalid_coordinate", "经纬度范围无效")
    data_year = _resolve_year(year)
    dataset_query, dataset_params = _dataset_sql(data_year)
    try:
        selected = db.session.execute(sa.text(f"""
            WITH data AS ({dataset_query})
            SELECT parcel_id FROM data
            WHERE geom IS NOT NULL
              AND ST_Covers(geom, ST_SetSRID(ST_Point(:lon, :lat), 4326))
            ORDER BY ST_Area(geom::geography), parcel_id LIMIT 1
        """), {**dataset_params, "lon": lon, "lat": lat}).mappings().first()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "地块点选服务暂时不可用", 503) from exc
    if selected is None:
        raise StatisticsError("parcel_not_found", "该位置在所选年份未命中地块", 404)
    return get_parcel_summary(selected["parcel_id"], data_year)


def query_parcels(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise StatisticsError("invalid_request", "请求体必须为 JSON 对象")
    scope = payload.get("scope")
    if not isinstance(scope, Mapping):
        raise StatisticsError("invalid_scope", "请求必须包含 scope 对象")
    metric_keys = _metric_keys(payload)
    data_year = _resolve_year(payload.get("year"))
    try:
        limit = int(payload.get("limit", 100))
        offset = int(payload.get("offset", 0))
    except (TypeError, ValueError) as exc:
        raise StatisticsError("invalid_pagination", "limit 和 offset 必须为整数") from exc
    if not 1 <= limit <= MAX_PARCEL_QUERY_LIMIT or offset < 0:
        raise StatisticsError("invalid_pagination", f"limit 必须为 1-{MAX_PARCEL_QUERY_LIMIT}，offset 不能小于 0")
    geometry_mode = str(payload.get("geometry", "centroid"))
    if geometry_mode not in {"none", "centroid"}:
        raise StatisticsError("invalid_geometry_mode", "geometry 仅支持 none 或 centroid")
    geometry_sql = "NULL" if geometry_mode == "none" else "ST_AsGeoJSON(ST_PointOnSurface(data.geom))"
    scope_query, scope_params, scope_response = _scope_sql(scope)
    dataset_query, dataset_params = _dataset_sql(data_year)
    sql = sa.text(f"""
        WITH scope AS MATERIALIZED ({scope_query}),
        data AS MATERIALIZED ({dataset_query}),
        matched AS (
            SELECT data.*,
                   ST_Area(ST_Intersection(data.geom, scope.geom)::geography) * :mu_per_sqm AS area_mu,
                   {geometry_sql} AS geometry
            FROM data CROSS JOIN scope
            WHERE data.geom IS NOT NULL
              AND data.geom && scope.geom
              AND ST_Intersects(data.geom, scope.geom)
        )
        SELECT parcel_id, area_code, soil_indicators, quality_grade, composite_index,
               updated_at, area_mu, geometry
        FROM matched WHERE area_mu > 0
        ORDER BY parcel_id LIMIT :query_limit OFFSET :query_offset
    """)
    params = {
        **scope_params, **dataset_params, "mu_per_sqm": MU_PER_SQUARE_METRE,
        "query_limit": limit + 1, "query_offset": offset,
    }
    try:
        rows = db.session.execute(sql, params).mappings().all()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "地块查询服务暂时不可用", 503) from exc
    has_more = len(rows) > limit
    items = []
    for row in rows[:limit]:
        item = _parcel_payload(
            row["parcel_id"], row["area_code"], _row_indicators(row),
            float(row["area_mu"]), data_year, metric_keys,
        )
        geometry = row["geometry"]
        item["geometry"] = json.loads(geometry) if isinstance(geometry, str) else geometry
        items.append(item)
    return {
        "scope": scope_response,
        "dataYear": data_year,
        "classificationVersion": CLASSIFICATION_VERSION,
        "items": items,
        "pagination": {"limit": limit, "offset": offset, "hasMore": has_more},
    }
