"""Spatially clipped farmland statistics used by the satellite-map dashboard."""

from __future__ import annotations

import json
import math
from collections import Counter, OrderedDict
from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import datetime
from threading import Lock
from time import monotonic
from typing import Any

import sqlalchemy as sa

from framework.domain.assessment.versioned_results import business_result
from framework.domain.statistics import (
    CLASSIFICATION_VERSION,
    INDICATOR_DEFINITIONS,
    INDICATOR_GROUPS,
    audit_indicator_rows,
    get_indicator_definition,
    metric_provenance,
)
from framework.models import ParcelInfo, SpatialRegionCatalog, db


MU_PER_SQUARE_METRE = 1.0 / 666.6666666666666
SCOPE_VERSION = 1
REGION_TYPES = {"province", "city", "county", "township", "village", "zone"}
BOUNDARY_MIN_ZOOM = {
    "province": 3,
    "city": 5,
    "county": 7,
    "township": 9,
    "village": 12,
    "zone": 12,
}
MAX_BOUNDARY_FEATURES = 5000
MAX_PARCEL_QUERY_LIMIT = 500
MAX_SELECTED_REGIONS = 100
MAX_CUSTOM_GEOMETRY_VERTICES = 5000
MAX_CUSTOM_GEOMETRY_AREA_SQ_KM = 200_000.0
MAX_PICK_TOLERANCE_METERS = 50.0
MAX_VIEWPORT_PARCELS = 5000
DEFAULT_VIEWPORT_PARCELS = 2000
PICK_CACHE_TTL_SECONDS = 5.0
QUALITY_AUDIT_CACHE_TTL_SECONDS = 300.0


class _TtlCache:
    def __init__(self, max_size: int):
        self.max_size = max_size
        self._values: OrderedDict[Any, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: Any) -> Any | None:
        now = monotonic()
        with self._lock:
            item = self._values.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._values.pop(key, None)
                return None
            self._values.move_to_end(key)
            return deepcopy(value)

    def set(self, key: Any, value: Any, ttl_seconds: float) -> None:
        with self._lock:
            self._values[key] = (monotonic() + ttl_seconds, deepcopy(value))
            self._values.move_to_end(key)
            while len(self._values) > self.max_size:
                self._values.popitem(last=False)


_PICK_CACHE = _TtlCache(max_size=512)
_QUALITY_AUDIT_CACHE = _TtlCache(max_size=1)


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
    if "assessment_result" in row:
        assessment = business_result(_json_object(row.get("assessment_result")))
        # Current computed values have one publication source.  A missing
        # versioned assessment (e.g. the historical snapshot branch) must not
        # wipe the snapshot's own quality_grade/composite_index; only override
        # when an assessment with actual content is present.
        if assessment:
            indicators["quality_grade"] = assessment.get("quality_grade")
            indicators["composite_index"] = assessment.get("composite_index")
    return indicators


def _catalog_rows() -> list[Mapping[str, Any]] | None:
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
        provenance_counts = {
            "dataSource": Counter(),
            "measurementYear": Counter(),
            "isImputed": Counter(),
            "imputationMethod": Counter(),
            "qualityFlag": Counter(),
        }

        for row in materialized:
            indicators = _row_indicators(row)
            provenance = metric_provenance(indicators, metric_key)
            for field, counter in provenance_counts.items():
                value = provenance[field]
                counter["unknown" if value is None else value] += 1
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
                bucket_values[bucket.key]["parcelCount"] += 1
                bucket_values[bucket.key]["areaMu"] += area_mu
            numeric_values.append((numeric, area_mu))

        valid_count = len(numeric_values) + sum(category_values.values())
        valid_area = sum(area for _, area in numeric_values) + sum(category_areas.values())

        def uniform_value(field: str) -> Any:
            values_with_counts = provenance_counts[field]
            if len(values_with_counts) != 1:
                return None
            value = next(iter(values_with_counts))
            return None if value == "unknown" else value

        if definition.value_type == "category":
            distribution = [
                {
                    "key": value,
                    "label": value,
                    "rangeLabel": value,
                    "color": None,
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
            "dataSource": uniform_value("dataSource") or (
                "mixed" if len(provenance_counts["dataSource"]) > 1 else None
            ),
            "measurementYear": uniform_value("measurementYear"),
            "isImputed": uniform_value("isImputed"),
            "imputationMethod": uniform_value("imputationMethod"),
            "qualityFlag": uniform_value("qualityFlag") or (
                "mixed" if len(provenance_counts["qualityFlag"]) > 1 else None
            ),
            "provenanceSummary": {
                field: {str(value): count for value, count in counter.items()}
                for field, counter in provenance_counts.items()
            },
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
        "scopeSummary": {
            "parcelCount": len(materialized),
            "totalAreaMu": _round(total_area),
        },
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


def _validate_custom_geometry(geometry: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(geometry, Mapping):
        raise StatisticsError("invalid_geometry", "scope.geometry 必须为 GeoJSON 几何对象")
    geometry_type = geometry.get("type")
    if geometry_type not in {"Polygon", "MultiPolygon"}:
        raise StatisticsError("invalid_geometry", "自定义范围仅支持 Polygon 或 MultiPolygon")
    coordinates = geometry.get("coordinates")
    polygons = [coordinates] if geometry_type == "Polygon" else coordinates
    if not isinstance(polygons, list) or not polygons:
        raise StatisticsError("invalid_geometry", "GeoJSON coordinates 不能为空")

    vertex_count = 0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise StatisticsError("invalid_geometry", "每个 Polygon 至少需要一个线性环")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise StatisticsError("invalid_geometry", "每个线性环至少需要四个坐标点")
            first: tuple[float, float] | None = None
            last: tuple[float, float] | None = None
            for position in ring:
                if not isinstance(position, (list, tuple)) or len(position) < 2:
                    raise StatisticsError("invalid_geometry", "GeoJSON 坐标点必须包含经度和纬度")
                if isinstance(position[0], bool) or isinstance(position[1], bool):
                    raise StatisticsError("invalid_geometry", "GeoJSON 坐标必须为数字")
                try:
                    lon, lat = float(position[0]), float(position[1])
                except (TypeError, ValueError) as exc:
                    raise StatisticsError("invalid_geometry", "GeoJSON 坐标必须为数字") from exc
                if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
                    raise StatisticsError("invalid_geometry", "GeoJSON 坐标超出 WGS84 有效范围")
                current = (lon, lat)
                first = current if first is None else first
                last = current
                vertex_count += 1
                if vertex_count > MAX_CUSTOM_GEOMETRY_VERTICES:
                    raise StatisticsError(
                        "geometry_too_complex",
                        f"自定义范围顶点数不能超过 {MAX_CUSTOM_GEOMETRY_VERTICES}",
                        413,
                    )
            if first != last:
                raise StatisticsError("invalid_geometry", "GeoJSON 线性环必须首尾闭合")
    return dict(geometry), vertex_count


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
    if zoom is not None and zoom != "":
        try:
            parsed_zoom = float(zoom)
        except (TypeError, ValueError) as exc:
            raise StatisticsError("invalid_zoom", "zoom 必须为 0 到 24 之间的数字") from exc
        if not math.isfinite(parsed_zoom) or not 0 <= parsed_zoom <= 24:
            raise StatisticsError("invalid_zoom", "zoom 必须为 0 到 24 之间的数字")

    min_zoom = BOUNDARY_MIN_ZOOM[region_type]
    base = {
        "type": "FeatureCollection",
        "regionType": region_type,
        "minZoom": min_zoom,
        "maxZoom": None,
        "zoom": parsed_zoom,
        "bbox": parsed_bbox,
    }
    if parsed_zoom is not None and parsed_zoom < min_zoom:
        return {**base, "suppressedByZoom": True, "truncated": False, "features": []}

    conditions = [
        "object_type = :region_type",
        "enabled = TRUE",
        "geom IS NOT NULL",
    ]
    params: dict[str, Any] = {
        "region_type": region_type,
        "limit": MAX_BOUNDARY_FEATURES + 1,
        "tolerance": 0.0 if parsed_zoom is None else 360.0 / (256.0 * 2 ** parsed_zoom) * 0.25,
    }
    if parent_type:
        conditions.extend([
            "parent_object_type = :parent_type",
            "parent_object_id = :parent_id",
        ])
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
               ST_AsGeoJSON(
                   CASE WHEN :tolerance > 0
                        THEN ST_SimplifyPreserveTopology(geom, :tolerance)
                        ELSE geom END
               ) AS geometry
        FROM spatial_region_catalog
        WHERE {' AND '.join(conditions)}
        ORDER BY object_id
        LIMIT :limit
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
            "type": "Feature",
            "id": f"{row['object_type']}:{row['object_id']}",
            "properties": {
                "regionType": row["object_type"],
                "regionId": row["object_id"],
                "displayName": row["display_name"],
                "areaCode": row["area_code"],
                "parentType": row["parent_object_type"],
                "parentId": row["parent_object_id"],
                "selectable": bool(metadata.get("selectable", True)),
                "minZoom": min_zoom,
                "maxZoom": None,
            },
            "geometry": geometry,
        })
    return {**base, "suppressedByZoom": False, "truncated": truncated, "features": features}


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
                "scopeVersion": SCOPE_VERSION,
                "type": scope_type,
                "regionType": region_type,
                "regionId": region_id,
                "displayName": exists["display_name"],
            },
        )

    if scope_type == "administrative_regions":
        region_type = str(scope.get("region_type") or "")
        region_ids_value = scope.get("region_ids")
        if region_type not in REGION_TYPES:
            raise StatisticsError("invalid_scope", "多区域统计必须包含有效的 region_type")
        if not isinstance(region_ids_value, list) or not region_ids_value:
            raise StatisticsError("invalid_scope", "region_ids 必须为非空数组")
        if any(value is None or isinstance(value, bool) or not str(value).strip() for value in region_ids_value):
            raise StatisticsError("invalid_scope", "region_ids 不能包含空值")
        region_ids = [str(value).strip() for value in region_ids_value]
        if len(set(region_ids)) != len(region_ids):
            raise StatisticsError("invalid_scope", "region_ids 不能包含空值或重复值")
        if len(region_ids) > MAX_SELECTED_REGIONS:
            raise StatisticsError("too_many_regions", f"一次最多选择 {MAX_SELECTED_REGIONS} 个同级行政区", 413)
        try:
            rows = db.session.execute(sa.text("""
                SELECT object_id, display_name, geom IS NOT NULL AS has_geom
                FROM spatial_region_catalog
                WHERE object_type = :region_type
                  AND object_id = ANY(CAST(:region_ids AS text[]))
                  AND enabled = TRUE
            """), {"region_type": region_type, "region_ids": region_ids}).mappings().all()
        except sa.exc.SQLAlchemyError as exc:
            raise StatisticsError("statistics_unavailable", "区域目录服务暂时不可用", 503) from exc
        by_id = {row["object_id"]: row for row in rows}
        missing = [region_id for region_id in region_ids if region_id not in by_id]
        if missing:
            raise StatisticsError("region_not_found", f"以下行政区域不存在或未启用: {', '.join(missing)}", 404)
        without_geometry = [region_id for region_id in region_ids if not by_id[region_id]["has_geom"]]
        if without_geometry:
            raise StatisticsError("region_geometry_missing", f"以下行政区域尚未导入边界: {', '.join(without_geometry)}", 409)
        return (
            """SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
               FROM spatial_region_catalog
               WHERE object_type = :region_type
                 AND object_id = ANY(CAST(:region_ids AS text[]))
                 AND enabled = TRUE AND geom IS NOT NULL""",
            {"region_type": region_type, "region_ids": region_ids},
            {
                "scopeVersion": SCOPE_VERSION,
                "type": scope_type,
                "regionType": region_type,
                "regionIds": region_ids,
                "regions": [{
                    "regionType": region_type,
                    "regionId": region_id,
                    "displayName": by_id[region_id]["display_name"],
                } for region_id in region_ids],
            },
        )

    if scope_type == "polygon":
        geometry, vertex_count = _validate_custom_geometry(scope.get("geometry"))
        geojson = json.dumps(geometry, ensure_ascii=False, separators=(",", ":"))
        try:
            validation = db.session.execute(sa.text("""
                WITH input AS (
                    SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326) AS geom
                )
                SELECT ST_IsValid(geom) AS is_valid,
                       ST_IsValidReason(geom) AS reason,
                       ST_Area(geom::geography) / 1000000.0 AS area_sq_km
                FROM input
            """), {"geojson": geojson}).mappings().first()
        except (sa.exc.SQLAlchemyError, ValueError) as exc:
            raise StatisticsError("invalid_geometry", "GeoJSON 几何无法解析或计算") from exc
        if validation is None or not validation["is_valid"]:
            reason = validation["reason"] if validation else "unknown"
            raise StatisticsError("invalid_geometry", f"GeoJSON 几何无效: {reason}")
        area_sq_km = float(validation["area_sq_km"] or 0)
        if area_sq_km <= 0:
            raise StatisticsError("invalid_geometry", "自定义范围面积必须大于 0")
        if area_sq_km > MAX_CUSTOM_GEOMETRY_AREA_SQ_KM:
            raise StatisticsError(
                "geometry_too_large",
                f"自定义范围面积不能超过 {MAX_CUSTOM_GEOMETRY_AREA_SQ_KM:g} 平方公里",
                413,
            )
        return (
            """SELECT ST_ForcePolygonCCW(
                         ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326))
                     ) AS geom""",
            {"geojson": geojson},
            {
                "scopeVersion": SCOPE_VERSION,
                "type": scope_type,
                "geometryType": geometry["type"],
                "vertexCount": vertex_count,
                "areaSqKm": _round(area_sq_km, 4),
                "srid": 4326,
            },
        )

    if scope_type == "viewport":
        try:
            parsed_bbox = _parse_bbox(scope.get("bbox"), "viewport.bbox")
        except StatisticsError as exc:
            raise StatisticsError("invalid_scope", exc.message) from exc
        if parsed_bbox is None:
            raise StatisticsError("invalid_scope", "viewport.bbox 必须为 [minLon,minLat,maxLon,maxLat]")
        min_lon, min_lat, max_lon, max_lat = parsed_bbox
        return (
            "SELECT ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326) AS geom",
            {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat},
            {
                "scopeVersion": SCOPE_VERSION,
                "type": scope_type,
                "bbox": [min_lon, min_lat, max_lon, max_lat],
                "srid": 4326,
            },
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
                "scopeVersion": SCOPE_VERSION,
                "type": scope_type,
                "parcelId": parcel_id,
                "areaCode": exists["area_code"],
            },
        )

    raise StatisticsError(
        "invalid_scope",
        "scope.type 仅支持 administrative_region、administrative_regions、polygon、viewport 或 parcel",
    )


def _dataset_sql(year: int | None) -> tuple[str, dict[str, Any]]:
    if year is None:
        return (
            """SELECT p.id AS parcel_pk, p.parcel_id, p.area_code, p.geom,
                      p.soil_indicators, NULL::text AS quality_grade,
                      NULL::double precision AS composite_index,
                      COALESCE(assessment.result_payload, '{}'::jsonb) AS assessment_result,
                      assessment.calculated_at AS assessment_calculated_at,
                      GREATEST(p.updated_at, assessment.calculated_at) AS updated_at
               FROM parcel_info AS p
               LEFT JOIN versioned_model_result AS assessment
                 ON assessment.agent_id = 'model-2'
                AND assessment.subject_type = 'parcel'
                AND assessment.subject_id = p.parcel_id
                AND assessment.is_current = TRUE""",
            {},
        )
    return (
        """SELECT p.id AS parcel_pk, p.parcel_id, p.area_code, p.geom,
                  h.soil_indicators, h.quality_grade, h.composite_index,
                  NULL::jsonb AS assessment_result,
                  NULL::timestamp with time zone AS assessment_calculated_at,
                  h.created_at AS updated_at
           FROM parcel_info AS p
           JOIN parcel_history_snapshot AS h ON h.parcel_id = p.parcel_id
           WHERE h.survey_year = :data_year""",
        {"data_year": year},
    )


def _live_statistics_sql(scope_query: str, dataset_query: str) -> sa.TextClause:
    """Build the spatial fallback query while evaluating each clip only once."""
    return sa.text(f"""
        WITH scope AS MATERIALIZED ({scope_query}),
        data AS MATERIALIZED ({dataset_query}),
        clipped AS MATERIALIZED (
            SELECT data.parcel_pk,
                   CASE
                     WHEN ST_CoveredBy(data.geom, scope.geom) THEN data.geom
                     ELSE ST_Intersection(data.geom, scope.geom)
                   END AS clipped_geom
            FROM data
            CROSS JOIN scope
            WHERE data.geom IS NOT NULL
              AND data.geom && scope.geom
              AND ST_Intersects(data.geom, scope.geom)
        ),
        parcel_areas AS MATERIALIZED (
            SELECT parcel_pk,
                   ST_Area(clipped_geom::geography) * :mu_per_sqm AS area_mu
            FROM clipped
            WHERE NOT ST_IsEmpty(clipped_geom)
        )
        SELECT data.parcel_id, data.area_code, data.soil_indicators,
               data.quality_grade, data.composite_index,
               data.assessment_result, data.assessment_calculated_at,
               data.updated_at,
               parcel_areas.area_mu
        FROM parcel_areas
        JOIN data ON data.parcel_pk = parcel_areas.parcel_pk
        WHERE parcel_areas.area_mu > 0
        ORDER BY data.parcel_id
    """)


def _precomputed_statistics_rows(
    scope_response: Mapping[str, Any],
    dataset_query: str,
    query_params: Mapping[str, Any],
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
        **query_params,
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
          AND state.relation_count = (
              SELECT COUNT(*)
              FROM farmland_region_parcel_area AS cached
              WHERE cached.region_type = state.region_type
                AND cached.region_id = state.region_id
          )
    """), params).mappings().first()
    if state is None:
        return None

    rows = db.session.execute(sa.text(f"""
        WITH data AS MATERIALIZED ({dataset_query})
        SELECT data.parcel_id, data.area_code, data.soil_indicators,
               data.quality_grade, data.composite_index,
               data.assessment_result, data.assessment_calculated_at,
               data.updated_at,
               cached.area_mu
        FROM farmland_region_parcel_area AS cached
        JOIN data ON data.parcel_id = cached.parcel_id
        WHERE cached.region_type = :region_type
          AND cached.region_id = :region_id
          AND cached.area_mu > 0
        ORDER BY data.parcel_id
    """), params).mappings().all()
    return rows






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
    params = {**scope_params, **dataset_params}
    try:
        rows = _precomputed_statistics_rows(scope_response, dataset_query, params)
        if rows is None:
            params["mu_per_sqm"] = MU_PER_SQUARE_METRE
            rows = db.session.execute(
                _live_statistics_sql(scope_query, dataset_query), params
            ).mappings().all()
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


_REGION_ORDER = ("province", "city", "county", "township", "village")
_REGION_DEPTH = {name: seq for seq, name in enumerate(_REGION_ORDER)}


def _parcel_region(parcel_id: str) -> dict[str, Any] | None:
    """通过地块几何中心，解析其行政区划层级路径（省/市/县/乡镇/村）。

    优先用点包含关系取最深层级（村），从而自然涵盖其上级；若点落在边界缝隙，
    则退化为面积码匹配到的县区及上级。返回形如
    {"path": ["广东省","韶关市",...], "village": "...", ...}，缺失层级不出现。
    """
    try:
        rows = db.session.execute(sa.text(f"""
            WITH pt AS MATERIALIZED (
                SELECT ST_PointOnSurface(geom) AS g
                FROM parcel_info
                WHERE parcel_id = :pid
                LIMIT 1
            )
            SELECT r.object_type, r.display_name
            FROM spatial_region_catalog AS r, pt
            WHERE r.enabled AND r.geom IS NOT NULL AND ST_Contains(r.geom, pt.g)
            ORDER BY CASE {" ".join(
                f"WHEN r.object_type = '{t}' THEN {d}" for t, d in _REGION_DEPTH.items()
            )} END DESC
        """), {"pid": parcel_id}).fetchall()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "地块区域信息暂时不可用", 503) from exc

    region: dict[str, str] = {}
    for object_type, display_name in rows:
        region[object_type] = str(display_name)
    if not region:
        return None
    return {
        "path": [region[t] for t in _REGION_ORDER if region.get(t)],
        **{t: region[t] for t in _REGION_ORDER if region.get(t)},
    }


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


def _validated_metric_key(metric_key: Any, *, required: bool = False) -> str | None:
    if metric_key is None or metric_key == "":
        if required:
            raise StatisticsError("invalid_metric", "必须提供有效的 metric 指标 key")
        return None
    metric_key = str(metric_key)
    if metric_key not in INDICATOR_DEFINITIONS:
        raise StatisticsError("invalid_metric", f"不支持的指标: {metric_key}")
    return metric_key


def _metric_response(metric_key: str, indicators: Mapping[str, Any]) -> dict[str, Any]:
    definition = get_indicator_definition(metric_key)
    value = definition.parse(definition.value_from(dict(indicators)))
    bucket = definition.classify(value)
    if isinstance(value, float):
        value = _round(value, definition.decimals)
    return {
        "metricKey": definition.key,
        "label": definition.label,
        "groupKey": definition.group_key,
        "order": definition.order,
        "valueType": definition.value_type,
        "value": value,
        "unit": definition.unit,
        "bucketKey": bucket.key if bucket else None,
        "bucketLabel": bucket.label if bucket else None,
        "rangeLabel": bucket.range_label if bucket else None,
        "color": bucket.color if bucket else None,
        **metric_provenance(indicators, metric_key),
    }


def _parcel_payload(
    parcel_id: str,
    area_code: str | None,
    indicators: Mapping[str, Any],
    area_mu: float | None,
    data_year: int | None,
    metric_keys: Iterable[str] | None = None,
    metric_key: str | None = None,
) -> dict[str, Any]:
    keys = list(metric_keys) if metric_keys is not None else _metric_keys({"metrics": "all"})
    metrics = {key: _metric_response(key, indicators) for key in keys}
    if metric_key is not None:
        return {
            "classificationVersion": CLASSIFICATION_VERSION,
            "parcelId": parcel_id,
            "areaCode": area_code,
            "areaMu": _round(area_mu),
            "dataYear": data_year,
            "metric": metrics[metric_key],
        }
    response = {
        "classificationVersion": CLASSIFICATION_VERSION,
        "parcelId": parcel_id,
        "areaCode": area_code,
        "areaMu": _round(area_mu),
        "dataYear": data_year,
        "metrics": metrics,
    }
    for legacy_key, key in (
        ("qualityGrade", "quality_grade"),
        ("organicMatter", "organic_matter"),
        ("soilPh", "soil_ph"),
        ("availablePhosphorus", "available_phosphorus"),
        ("availablePotassium", "available_potassium"),
        ("bulkDensity", "bulk_density"),
        ("plowLayerThickness", "plow_layer_thickness"),
        ("effectiveSoilDepth", "effective_soil_depth"),
    ):
        if key in metrics:
            response[legacy_key] = metrics[key]["value"]
    return response


def _parcel_response(
    parcel: ParcelInfo,
    area_mu: float | None,
    metric_key: str | None = None,
    *,
    data_year: int | None = None,
    metric_keys: Iterable[str] | None = None,
    assessment: Mapping[str, Any] | None = None,
    version: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    indicators = _json_object(parcel.soil_indicators)
    if getattr(parcel, "quality_grade", None) is not None:
        indicators["quality_grade"] = parcel.quality_grade
    if getattr(parcel, "composite_index", None) is not None:
        indicators["composite_index"] = parcel.composite_index
    if assessment is not None:
        calculated = dict(assessment)
        indicators["quality_grade"] = calculated.get("quality_grade")
        indicators["composite_index"] = calculated.get("composite_index")
    response = _parcel_payload(
        parcel.parcel_id,
        parcel.area_code,
        indicators,
        area_mu,
        data_year,
        metric_keys,
        metric_key,
    )
    if metric_key is None:
        response["compositeIndex"] = _round(indicators.get("composite_index"))
    if version:
        response["qualityAssessment"] = dict(version)
    return response


def _calculated_grade(parcel: ParcelInfo) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ensure and return the Model-2 publication shared by map and agent."""
    from framework.agents.specialized.grade_agent import FarmlandGradeAgent

    execution = FarmlandGradeAgent().execute({
        "parcel_id": parcel.parcel_id,
        "area_code": parcel.area_code,
    })
    return business_result(execution), dict(execution.get("versioned_result") or {})


def get_parcel_summary(
    parcel_id: str,
    year: Any = None,
    metric_key: Any = None,
) -> dict[str, Any]:
    validated_metric = _validated_metric_key(metric_key)
    data_year = _resolve_year(year)
    if data_year is None:
        parcel = ParcelInfo.query.filter_by(parcel_id=parcel_id).first()
        if parcel is None:
            raise StatisticsError("parcel_not_found", "地块不存在", 404)
        keys = [validated_metric] if validated_metric else None
        assessment, version = _calculated_grade(parcel)
        return _parcel_response(
            parcel,
            _parcel_area_mu(parcel.parcel_id),
            validated_metric,
            data_year=None,
            metric_keys=keys,
            assessment=assessment,
            version=version,
        )
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
            "parcel_id": parcel_id,
            "data_year": data_year,
            "mu_per_sqm": MU_PER_SQUARE_METRE,
        }).mappings().first()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "地块详情服务暂时不可用", 503) from exc
    if row is None:
        raise StatisticsError("parcel_year_not_found", f"地块在 {data_year} 年没有可用数据", 404)
    keys = [validated_metric] if validated_metric else None
    return _parcel_payload(
        row["parcel_id"],
        row["area_code"],
        _row_indicators(row),
        None if row["area_mu"] is None else float(row["area_mu"]),
        data_year,
        keys,
        validated_metric,
    )


def pick_parcel(
    longitude: Any,
    latitude: Any,
    metric_key: Any = None,
    tolerance_meters: Any = 0,
    year: Any = None,
) -> dict[str, Any]:
    try:
        lon, lat = float(longitude), float(latitude)
    except (TypeError, ValueError) as exc:
        raise StatisticsError("invalid_coordinate", "经纬度必须为数字") from exc
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise StatisticsError("invalid_coordinate", "经纬度范围无效")
    metric_key = _validated_metric_key(metric_key)
    try:
        tolerance = float(tolerance_meters or 0)
    except (TypeError, ValueError) as exc:
        raise StatisticsError("invalid_tolerance", "toleranceMeters 必须为数字") from exc
    if not math.isfinite(tolerance) or not 0 <= tolerance <= MAX_PICK_TOLERANCE_METERS:
        raise StatisticsError(
            "invalid_tolerance",
            f"toleranceMeters 必须在 0 到 {MAX_PICK_TOLERANCE_METERS:g} 之间",
        )

    data_year = _resolve_year(year)
    cache_key = (round(lon, 7), round(lat, 7), round(tolerance, 2), metric_key, data_year)
    cached = _PICK_CACHE.get(cache_key)
    if cached is not None:
        return cached

    tolerance_degrees = tolerance / 111_320.0
    dataset_query, dataset_params = _dataset_sql(data_year)
    try:
        selected = db.session.execute(sa.text(f"""
            WITH target AS (
                SELECT ST_SetSRID(ST_Point(:lon, :lat), 4326) AS geom
            ),
            data AS MATERIALIZED ({dataset_query})
            SELECT data.parcel_id,
                   ST_Area(data.geom::geography) * :mu_per_sqm AS area_mu,
                   ST_Covers(data.geom, target.geom) AS exact_hit,
                   CASE WHEN ST_Covers(data.geom, target.geom) THEN 0.0
                        ELSE ST_Distance(data.geom::geography, target.geom::geography)
                   END AS distance_meters
            FROM data
            CROSS JOIN target
            WHERE data.geom IS NOT NULL
              AND data.geom && ST_Expand(target.geom, :tolerance_degrees)
              AND (
                    ST_Covers(data.geom, target.geom)
                    OR (:tolerance > 0 AND ST_DWithin(
                        data.geom::geography, target.geom::geography, :tolerance
                    ))
              )
            ORDER BY exact_hit DESC, distance_meters,
                     ST_Area(data.geom::geography), data.parcel_id
            LIMIT 1
        """), {
            **dataset_params,
            "lon": lon,
            "lat": lat,
            "tolerance": tolerance,
            "tolerance_degrees": tolerance_degrees,
            "mu_per_sqm": MU_PER_SQUARE_METRE,
        }).mappings().first()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "地块点选服务暂时不可用", 503) from exc
    if selected is None:
        raise StatisticsError("parcel_not_found", "该位置未命中地块", 404)
    result = get_parcel_summary(selected["parcel_id"], data_year, metric_key)
    land_type_row = db.session.execute(
        sa.text("SELECT land_type FROM parcel_info WHERE parcel_id = :pid LIMIT 1"),
        {"pid": selected["parcel_id"]},
    ).first()
    if land_type_row and land_type_row[0]:
        result["landType"] = str(land_type_row[0])
    result["hit"] = {
        "mode": "exact" if selected["exact_hit"] else "nearest",
        "distanceMeters": _round(float(selected["distance_meters"] or 0), 3),
        "toleranceMeters": tolerance,
    }
    region = _parcel_region(selected["parcel_id"])
    if region:
        result["region"] = region
    _PICK_CACHE.set(cache_key, result, PICK_CACHE_TTL_SECONDS)
    return result


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
        raise StatisticsError(
            "invalid_pagination",
            f"limit 必须为 1-{MAX_PARCEL_QUERY_LIMIT}，offset 不能小于 0",
        )
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
               assessment_result, assessment_calculated_at,
               updated_at, area_mu, geometry
        FROM matched WHERE area_mu > 0
        ORDER BY parcel_id LIMIT :query_limit OFFSET :query_offset
    """)
    params = {
        **scope_params,
        **dataset_params,
        "mu_per_sqm": MU_PER_SQUARE_METRE,
        "query_limit": limit + 1,
        "query_offset": offset,
    }
    try:
        rows = db.session.execute(sql, params).mappings().all()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "地块查询服务暂时不可用", 503) from exc
    has_more = len(rows) > limit
    items = []
    for row in rows[:limit]:
        item = _parcel_payload(
            row["parcel_id"],
            row["area_code"],
            _row_indicators(row),
            float(row["area_mu"]),
            data_year,
            metric_keys,
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


def list_viewport_parcels(
    bbox: Any,
    metric_key: Any,
    geometry_mode: Any = "centroid",
    zoom: Any = None,
    limit: Any = DEFAULT_VIEWPORT_PARCELS,
) -> dict[str, Any]:
    parsed_bbox = _parse_bbox(bbox)
    if parsed_bbox is None:
        raise StatisticsError("invalid_bbox", "bbox 必须为 [minLon,minLat,maxLon,maxLat]")
    metric_key = _validated_metric_key(metric_key, required=True)
    geometry_mode = str(geometry_mode or "centroid")
    if geometry_mode not in {"centroid", "simplified", "none"}:
        raise StatisticsError("invalid_geometry_mode", "geometry 必须为 centroid、simplified 或 none")
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise StatisticsError("invalid_limit", "limit 必须为整数") from exc
    if not 1 <= parsed_limit <= MAX_VIEWPORT_PARCELS:
        raise StatisticsError("invalid_limit", f"limit 必须在 1 到 {MAX_VIEWPORT_PARCELS} 之间")

    parsed_zoom = 14.0
    if zoom not in (None, ""):
        try:
            parsed_zoom = float(zoom)
        except (TypeError, ValueError) as exc:
            raise StatisticsError("invalid_zoom", "zoom 必须为 0 到 24 之间的数字") from exc
        if not math.isfinite(parsed_zoom) or not 0 <= parsed_zoom <= 24:
            raise StatisticsError("invalid_zoom", "zoom 必须为 0 到 24 之间的数字")
    tolerance = 360.0 / (256.0 * 2 ** parsed_zoom) * 0.25

    if geometry_mode == "centroid":
        geometry_sql = "ST_AsGeoJSON(ST_PointOnSurface(p.geom))"
    elif geometry_mode == "simplified":
        geometry_sql = """ST_AsGeoJSON(ST_SimplifyPreserveTopology(
            ST_Intersection(p.geom, bounds.geom), :tolerance
        ))"""
    else:
        geometry_sql = "NULL"

    min_lon, min_lat, max_lon, max_lat = parsed_bbox
    sql = sa.text(f"""
        WITH bounds AS MATERIALIZED (
            SELECT ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326) AS geom
        )
        SELECT p.parcel_id, p.area_code, p.soil_indicators, p.updated_at,
               {geometry_sql} AS geometry
        FROM parcel_info AS p
        CROSS JOIN bounds
        WHERE p.geom IS NOT NULL
          AND p.geom && bounds.geom
          AND ST_Intersects(p.geom, bounds.geom)
        ORDER BY p.parcel_id
        LIMIT :query_limit
    """)
    try:
        rows = db.session.execute(sql, {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
            "tolerance": tolerance,
            "query_limit": parsed_limit + 1,
        }).mappings().all()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "视口地块服务暂时不可用", 503) from exc

    truncated = len(rows) > parsed_limit
    features = []
    updated_values = []
    for row in rows[:parsed_limit]:
        indicators = _json_object(row["soil_indicators"])
        metric = _metric_response(metric_key, indicators)
        geometry = row["geometry"]
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        if row["updated_at"] is not None:
            updated_values.append(row["updated_at"])
        features.append({
            "type": "Feature",
            "id": row["parcel_id"],
            "properties": {
                "parcelId": row["parcel_id"],
                "areaCode": row["area_code"],
                **metric,
            },
            "geometry": geometry,
        })

    return {
        "type": "FeatureCollection",
        "classificationVersion": CLASSIFICATION_VERSION,
        "metricKey": metric_key,
        "bbox": parsed_bbox,
        "geometryMode": geometry_mode,
        "zoom": parsed_zoom if geometry_mode == "simplified" else None,
        "dataAsOf": _isoformat(max(updated_values)) if updated_values else None,
        "truncated": truncated,
        "limit": parsed_limit,
        "features": features,
    }


def indicator_quality_audit(*, refresh: bool = False) -> dict[str, Any]:
    if not refresh:
        cached = _QUALITY_AUDIT_CACHE.get("all")
        if cached is not None:
            return cached
    try:
        rows = db.session.execute(sa.text("""
            SELECT soil_indicators, updated_at
            FROM parcel_info
            ORDER BY id
        """)).mappings().all()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "指标质量审计服务暂时不可用", 503) from exc
    result = audit_indicator_rows(rows)
    _QUALITY_AUDIT_CACHE.set("all", result, QUALITY_AUDIT_CACHE_TTL_SECONDS)
    return result
