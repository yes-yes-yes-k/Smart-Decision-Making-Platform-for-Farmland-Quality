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

from framework.domain.statistics import (
    CLASSIFICATION_VERSION,
    INDICATOR_DEFINITIONS,
    audit_indicator_rows,
    get_indicator_definition,
    metric_provenance,
)
from framework.models import ParcelInfo, SpatialRegionCatalog, db


MU_PER_SQUARE_METRE = 1.0 / 666.6666666666666
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


def metric_metadata() -> list[dict[str, Any]]:
    return [{
        **definition.as_dict(),
        "metricKey": definition.key,
        "classificationVersion": CLASSIFICATION_VERSION,
    } for definition in INDICATOR_DEFINITIONS.values()]


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
        provenance_counts = {
            "dataSource": Counter(),
            "measurementYear": Counter(),
            "isImputed": Counter(),
            "imputationMethod": Counter(),
            "qualityFlag": Counter(),
        }

        for row in materialized:
            indicators = _json_object(row.get("soil_indicators"))
            provenance = metric_provenance(indicators, metric_key)
            for field, counter in provenance_counts.items():
                value = provenance[field]
                counter["unknown" if value is None else value] += 1
            parsed = definition.parse(definition.value_from(indicators))
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

        def uniform_value(field: str) -> Any:
            values_with_counts = provenance_counts[field]
            if len(values_with_counts) != 1:
                return None
            value = next(iter(values_with_counts))
            return None if value == "unknown" else value

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
            "metricKey": definition.key,
            "label": definition.label,
            "unit": definition.unit,
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
        "classificationVersion": CLASSIFICATION_VERSION,
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
            {"type": scope_type, "bbox": [min_lon, min_lat, max_lon, max_lat], "srid": 4326},
        )

    raise StatisticsError(
        "invalid_scope",
        "scope.type 仅支持 administrative_region、administrative_regions、polygon 或 viewport",
    )


def aggregate_statistics(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise StatisticsError("invalid_request", "请求体必须为 JSON 对象")
    scope = payload.get("scope")
    if not isinstance(scope, Mapping):
        raise StatisticsError("invalid_scope", "请求必须包含 scope 对象")
    metric_keys = _metric_keys(payload)
    scope_query, params, scope_response = _scope_sql(scope)
    sql = sa.text(f"""
        WITH scope AS MATERIALIZED ({scope_query}),
        scope_parts AS MATERIALIZED (
            SELECT ST_Subdivide(geom, 256) AS geom
            FROM scope
            WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom)
        ),
        clipped AS MATERIALIZED (
            SELECT p.id AS parcel_pk,
                   ST_Intersection(p.geom, scope_parts.geom) AS clipped_geom
            FROM parcel_info AS p
            JOIN scope_parts
              ON p.geom && scope_parts.geom
             AND ST_Intersects(p.geom, scope_parts.geom)
            WHERE p.geom IS NOT NULL
        ),
        parcel_areas AS (
            SELECT parcel_pk,
                   SUM(ST_Area(clipped_geom::geography)) * :mu_per_sqm AS area_mu
            FROM clipped
            WHERE NOT ST_IsEmpty(clipped_geom)
            GROUP BY parcel_pk
        )
        SELECT p.parcel_id, p.area_code, p.soil_indicators, p.updated_at,
               parcel_areas.area_mu
        FROM parcel_areas
        JOIN parcel_info AS p ON p.id = parcel_areas.parcel_pk
        WHERE parcel_areas.area_mu > 0
        ORDER BY p.parcel_id
    """)
    params["mu_per_sqm"] = MU_PER_SQUARE_METRE
    try:
        rows = db.session.execute(sql, params).mappings().all()
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
    return {
        "metricKey": definition.key,
        "value": _round(value, definition.decimals),
        "unit": definition.unit,
        "bucketKey": bucket.key if bucket else None,
        "bucketLabel": bucket.label if bucket else None,
        "rangeLabel": bucket.range_label if bucket else None,
        "color": bucket.color if bucket else None,
        **metric_provenance(indicators, metric_key),
    }


def _parcel_response(
    parcel: ParcelInfo,
    area_mu: float | None,
    metric_key: str | None = None,
) -> dict[str, Any]:
    indicators = _json_object(parcel.soil_indicators)
    if metric_key is not None:
        return {
            "classificationVersion": CLASSIFICATION_VERSION,
            "parcelId": parcel.parcel_id,
            "areaCode": parcel.area_code,
            "areaMu": _round(area_mu),
            "metric": _metric_response(metric_key, indicators),
        }

    metrics = {
        definition.key: _metric_response(definition.key, indicators)
        for definition in INDICATOR_DEFINITIONS.values()
    }
    return {
        "classificationVersion": CLASSIFICATION_VERSION,
        "parcelId": parcel.parcel_id,
        "areaCode": parcel.area_code,
        "areaMu": _round(area_mu),
        "qualityGrade": indicators.get("quality_grade"),
        "organicMatter": metrics["organic_matter"]["value"],
        "soilPh": metrics["soil_ph"]["value"],
        "availablePhosphorus": metrics["available_phosphorus"]["value"],
        "availablePotassium": metrics["available_potassium"]["value"],
        "bulkDensity": metrics["bulk_density"]["value"],
        "plowLayerThickness": metrics["plow_layer_thickness"]["value"],
        "effectiveSoilDepth": metrics["effective_soil_depth"]["value"],
        "metrics": metrics,
    }


def get_parcel_summary(parcel_id: str) -> dict[str, Any]:
    parcel = ParcelInfo.query.filter_by(parcel_id=parcel_id).first()
    if parcel is None:
        raise StatisticsError("parcel_not_found", "地块不存在", 404)
    return _parcel_response(parcel, _parcel_area_mu(parcel.parcel_id))


def pick_parcel(
    longitude: Any,
    latitude: Any,
    metric_key: Any = None,
    tolerance_meters: Any = 0,
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

    cache_key = (round(lon, 7), round(lat, 7), round(tolerance, 2), metric_key)
    cached = _PICK_CACHE.get(cache_key)
    if cached is not None:
        return cached

    tolerance_degrees = tolerance / 111_320.0
    try:
        selected = db.session.execute(sa.text("""
            WITH target AS (
                SELECT ST_SetSRID(ST_Point(:lon, :lat), 4326) AS geom
            )
            SELECT p.parcel_id,
                   ST_Area(p.geom::geography) * :mu_per_sqm AS area_mu,
                   ST_Covers(p.geom, target.geom) AS exact_hit,
                   CASE WHEN ST_Covers(p.geom, target.geom) THEN 0.0
                        ELSE ST_Distance(p.geom::geography, target.geom::geography)
                   END AS distance_meters
            FROM parcel_info AS p
            CROSS JOIN target
            WHERE p.geom IS NOT NULL
              AND p.geom && ST_Expand(target.geom, :tolerance_degrees)
              AND (
                    ST_Covers(p.geom, target.geom)
                    OR (:tolerance > 0 AND ST_DWithin(
                        p.geom::geography, target.geom::geography, :tolerance
                    ))
              )
            ORDER BY exact_hit DESC, distance_meters,
                     ST_Area(p.geom::geography), p.parcel_id
            LIMIT 1
        """), {
            "lon": lon,
            "lat": lat,
            "tolerance": tolerance,
            "tolerance_degrees": tolerance_degrees,
            "mu_per_sqm": MU_PER_SQUARE_METRE,
        }).mappings().first()
    except sa.exc.SQLAlchemyError as exc:
        raise StatisticsError("statistics_unavailable", "地块点选服务暂时不可用", 503) from exc
    parcel = ParcelInfo.query.filter_by(parcel_id=selected["parcel_id"]).first() if selected else None
    if parcel is None:
        raise StatisticsError("parcel_not_found", "该位置未命中地块", 404)
    result = _parcel_response(parcel, float(selected["area_mu"]), metric_key)
    result["hit"] = {
        "mode": "exact" if selected["exact_hit"] else "nearest",
        "distanceMeters": _round(float(selected["distance_meters"] or 0), 3),
        "toleranceMeters": tolerance,
    }
    _PICK_CACHE.set(cache_key, result, PICK_CACHE_TTL_SECONDS)
    return result


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
