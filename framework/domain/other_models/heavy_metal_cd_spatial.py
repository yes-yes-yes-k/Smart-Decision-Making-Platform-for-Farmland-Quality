"""Cd 结果的空间分析：乡镇级统计、单区域统计与点位 GeoJSON（阶段 3）。

复用既有基础设施，不重造空间能力：

- 区域目录：``spatial_region_catalog``（township 103 个，边界齐全）
- 地块归属：``farmland_region_parcel_area``（预计算「区域 × 地块 × 面积亩」，30751 行）
- 坐标：``parcel_info.centroid_lon/lat``（结果表没有坐标，阶段 1 决策 3）
- 区域边界：由 ``/api/v1/farmland-statistics/boundaries`` 提供，本模块不重复实现

归属规则（design 决策 1）：每个地块只归**面积最大**的区域，避免跨乡镇地块被重复统计。
实测 township 级有 530 个地块跨乡镇（9.6%），响应中通过 ``borderline_parcel_count`` 披露。
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Sequence

from framework.domain.other_models import heavy_metal_cd_statistics as statistics

REGION_TYPES: tuple[str, ...] = ("province", "city", "county", "township", "zone", "village")
DEFAULT_POINT_LIMIT = 5000
MAX_POINT_LIMIT = 20000
CSV_SCOPE_NOTE = "空间统计复用阶段 2 的统计口径（总体标准差、下标直取分位数）"


class CdSpatialError(ValueError):
    """空间查询的输入或数据错误。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _require_app_context() -> None:
    from flask import has_app_context

    if not has_app_context():
        raise CdSpatialError("no_app_context")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _check_region_type(region_type: str) -> str:
    region_type = str(region_type or "").strip()
    if region_type not in REGION_TYPES:
        raise CdSpatialError("invalid_region_type")
    return region_type


def _result_table(model_id: str):
    if model_id not in statistics.MODEL_IDS:
        raise CdSpatialError("unknown_model")
    from framework.models.cd_prediction import (  # noqa: WPS433
        CdCropPredictionResult,
        CdEffectivePredictionResult,
    )

    return CdCropPredictionResult if model_id == "crop_cd" else CdEffectivePredictionResult


# ----------------------------- 归属 -----------------------------


def parcel_region_map(region_type: str = "township") -> dict[str, str]:
    """每个地块 → 面积最大的那个区域（唯一归属）。跨数据库可用的窗口函数写法。"""
    _require_app_context()
    from sqlalchemy import func, select

    from framework.models import FarmlandRegionParcelArea
    from framework.models.user import db

    region_type = _check_region_type(region_type)
    area = FarmlandRegionParcelArea
    ranked = (
        select(
            area.parcel_id.label("parcel_id"),
            area.region_id.label("region_id"),
            func.row_number()
            .over(
                partition_by=area.parcel_id,
                order_by=(area.area_mu.desc(), area.region_id.asc()),
            )
            .label("rn"),
        )
        .where(area.region_type == region_type)
        .subquery()
    )
    rows = db.session.execute(
        select(ranked.c.parcel_id, ranked.c.region_id).where(ranked.c.rn == 1)
    ).all()
    return {str(parcel_id): str(region_id) for parcel_id, region_id in rows}


def borderline_parcel_count(region_type: str = "township") -> int:
    """与多个区域相交的地块数（用于披露归属规则的取舍）。"""
    _require_app_context()
    from sqlalchemy import func, select

    from framework.models import FarmlandRegionParcelArea
    from framework.models.user import db

    region_type = _check_region_type(region_type)
    area = FarmlandRegionParcelArea
    sub = (
        select(area.parcel_id, func.count().label("n"))
        .where(area.region_type == region_type)
        .group_by(area.parcel_id)
        .subquery()
    )
    total = db.session.execute(
        select(func.count()).select_from(sub).where(sub.c.n > 1)
    ).scalar()
    return int(total or 0)


def region_catalog_entry(region_type: str, region_id: str) -> dict[str, Any] | None:
    """从区域目录取展示名与上级信息。"""
    _require_app_context()
    from sqlalchemy import select

    from framework.models import SpatialRegionCatalog
    from framework.models.user import db

    region_type = _check_region_type(region_type)
    row = db.session.execute(
        select(
            SpatialRegionCatalog.object_id,
            SpatialRegionCatalog.display_name,
            SpatialRegionCatalog.area_code,
            SpatialRegionCatalog.parent_object_type,
            SpatialRegionCatalog.parent_object_id,
        )
        .where(
            SpatialRegionCatalog.object_type == region_type,
            SpatialRegionCatalog.object_id == str(region_id),
            SpatialRegionCatalog.enabled.is_(True),
        )
        .limit(1)
    ).first()
    if row is None:
        return None
    return {
        "region_type": region_type,
        "region_id": row[0],
        "display_name": row[1],
        "area_code": row[2],
        "parent_object_type": row[3],
        "parent_object_id": row[4],
    }


def _parcel_values(model_id: str) -> list[tuple[str, float]]:
    """取 (parcel_id, 还原后的值) 列表。"""
    _require_app_context()
    from sqlalchemy import select

    from framework.models.user import db

    table = _result_table(model_id)
    column = getattr(table, statistics._COLUMNS[model_id])  # noqa: SLF001 - 同模块口径
    rows = db.session.execute(select(table.parcel_id, column)).all()
    payload: list[tuple[str, float]] = []
    for parcel_id, log_value in rows:
        if log_value is None:
            continue
        try:
            value = math.exp(float(log_value))
        except (OverflowError, ValueError):
            continue
        if math.isfinite(value):
            payload.append((str(parcel_id), value))
    return payload


def _region_stats_payload(model_id: str, values: Sequence[float]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "数据单位": statistics.UNIT,
        "unit_status": statistics.UNIT_STATUS,
        "has_data": bool(values),
        "基础统计": statistics.basic_statistics(values),
    }
    if model_id == "crop_cd":
        payload["分布统计表格"] = statistics.crop_cd_distribution(values)
        payload["statistics_scope"] = statistics.THRESHOLD_NOTE
    else:
        payload["statistics_scope"] = "effective_cd_basic"
    return payload


# ----------------------------- 乡镇/区域统计 -----------------------------


def region_statistics(model_id: str, region_type: str, region_id: str) -> dict[str, Any]:
    """单个区域的 Cd 统计（归属走面积表，不用点面判断）。"""
    if model_id not in statistics.MODEL_IDS:
        raise CdSpatialError("unknown_model")
    region_type = _check_region_type(region_type)
    entry = region_catalog_entry(region_type, region_id)
    if entry is None:
        raise CdSpatialError("region_not_found")

    mapping = parcel_region_map(region_type)
    target = str(region_id)
    parcel_ids = [parcel_id for parcel_id, rid in mapping.items() if rid == target]
    wanted = set(parcel_ids)
    values = [value for parcel_id, value in _parcel_values(model_id) if parcel_id in wanted]

    payload = {
        "model_id": model_id,
        **entry,
        "assignment_rule": "max_area",
        "parcel_count": len(parcel_ids),
        "queried_at": _now_iso(),
        "queried_at_is": "query_time",
        **_region_stats_payload(model_id, values),
    }
    return payload


def township_statistics(
    model_id: str,
    *,
    region_type: str = "township",
    parent_type: str | None = None,
    parent_id: str | None = None,
    min_count: int = 1,
) -> dict[str, Any]:
    """按区域（默认 township）聚合的 Cd 统计列表。

    排序：样本数降序、区域标识升序，保证结果稳定。``min_count`` 过滤小样本。
    """
    if model_id not in statistics.MODEL_IDS:
        raise CdSpatialError("unknown_model")
    region_type = _check_region_type(region_type)
    if bool(parent_type) != bool(parent_id):
        raise CdSpatialError("invalid_parent")
    if not isinstance(min_count, int) or min_count < 0:
        raise CdSpatialError("invalid_min_count")

    mapping = parcel_region_map(region_type)
    buckets: dict[str, list[float]] = {}
    for parcel_id, value in _parcel_values(model_id):
        region_id = mapping.get(parcel_id)
        if region_id is None:
            continue
        buckets.setdefault(region_id, []).append(value)

    names = _catalog_names(region_type, parent_type, parent_id)
    items: list[dict[str, Any]] = []
    for region_id, values in buckets.items():
        if len(values) < max(min_count, 1):
            continue
        entry = names.get(region_id, {})
        items.append(
            {
                "region_type": region_type,
                "region_id": region_id,
                "display_name": entry.get("display_name"),
                "area_code": entry.get("area_code"),
                "parent_object_type": entry.get("parent_object_type"),
                "parent_object_id": entry.get("parent_object_id"),
                "count": len(values),
                **_region_stats_payload(model_id, values),
            }
        )
    items.sort(key=lambda item: (-item["count"], item["region_id"]))

    return {
        "model_id": model_id,
        "region_type": region_type,
        "assignment_rule": "max_area",
        "min_count": min_count,
        "borderline_parcel_count": borderline_parcel_count(region_type),
        "has_data": bool(items),
        "count": len(items),
        "unit": statistics.UNIT,
        "unit_status": statistics.UNIT_STATUS,
        "queried_at": _now_iso(),
        "queried_at_is": "query_time",
        "regions": items,
    }


def _catalog_names(
    region_type: str, parent_type: str | None, parent_id: str | None
) -> dict[str, dict[str, Any]]:
    _require_app_context()
    from sqlalchemy import select

    from framework.models import SpatialRegionCatalog
    from framework.models.user import db

    query = select(
        SpatialRegionCatalog.object_id,
        SpatialRegionCatalog.display_name,
        SpatialRegionCatalog.area_code,
        SpatialRegionCatalog.parent_object_type,
        SpatialRegionCatalog.parent_object_id,
    ).where(
        SpatialRegionCatalog.object_type == region_type,
        SpatialRegionCatalog.enabled.is_(True),
    )
    if parent_type:
        query = query.where(
            SpatialRegionCatalog.parent_object_type == str(parent_type),
            SpatialRegionCatalog.parent_object_id == str(parent_id),
        )
    return {
        str(row[0]): {
            "display_name": row[1],
            "area_code": row[2],
            "parent_object_type": row[3],
            "parent_object_id": row[4],
        }
        for row in db.session.execute(query).all()
    }


# ----------------------------- 点位 GeoJSON -----------------------------


def points_geojson(
    model_id: str,
    *,
    bbox: Sequence[float] | None = None,
    limit: int = DEFAULT_POINT_LIMIT,
) -> dict[str, Any]:
    """点位 FeatureCollection，坐标取地块质心（结果表没有坐标）。"""
    if model_id not in statistics.MODEL_IDS:
        raise CdSpatialError("unknown_model")
    if not isinstance(limit, int) or limit < 1 or limit > MAX_POINT_LIMIT:
        raise CdSpatialError("invalid_limit")
    if bbox is not None:
        if len(bbox) != 4:
            raise CdSpatialError("invalid_bbox")
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
        if not (min_lon < max_lon and min_lat < max_lat):
            raise CdSpatialError("invalid_bbox")

    _require_app_context()
    from sqlalchemy import func, select

    from framework.models import ParcelInfo
    from framework.models.user import db

    table = _result_table(model_id)
    column = getattr(table, statistics._COLUMNS[model_id])  # noqa: SLF001
    base = select(
        table.parcel_id, table.sample_id, column,
        ParcelInfo.centroid_lon, ParcelInfo.centroid_lat,
    ).join(ParcelInfo, ParcelInfo.parcel_id == table.parcel_id)

    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
        base = base.where(
            ParcelInfo.centroid_lon.between(min_lon, max_lon),
            ParcelInfo.centroid_lat.between(min_lat, max_lat),
        )

    total = db.session.execute(select(func.count()).select_from(base.subquery())).scalar() or 0
    rows = db.session.execute(
        base.order_by(table.parcel_id, table.sample_id).limit(limit)
    ).all()

    features = []
    for parcel_id, sample_id, log_value, lon, lat in rows:
        if log_value is None or lon is None or lat is None:
            continue
        value = float(log_value)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": {
                    "parcel_id": parcel_id,
                    "sample_id": sample_id,
                    "value": math.exp(value),
                    "ln_value": value,
                    "unit": statistics.UNIT,
                    "unit_status": statistics.UNIT_STATUS,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "model_id": model_id,
        "coordinate_source": "parcel_centroid",
        "boundary_endpoint": "/api/v1/farmland-statistics/boundaries",
        "bbox": list(bbox) if bbox is not None else None,
        "limit": limit,
        "count": len(features),
        "omitted": max(int(total) - len(features), 0),
        "unit": statistics.UNIT,
        "unit_status": statistics.UNIT_STATUS,
        "features": features,
    }
