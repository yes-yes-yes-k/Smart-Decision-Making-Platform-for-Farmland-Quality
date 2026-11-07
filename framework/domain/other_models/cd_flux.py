"""Cd 通量核算：输入行导入、四类通量计算、区域统计与分布、点位与导出（阶段 5）。

取数链路（design 决策 2）：输入数据依赖外部 CSV 供给（新库没有 flux 表、
容重表为空、大气沉降/灌溉/农化投入无现成来源），因此本模块只负责
「完整输入行 → 计算 → 持久化 → 统计/空间/导出」，不自动推导输入分量。

计算口径（design 决策 3，统一原系统数据库模式）::

    In  = DQCJ + GGS + NCP
    Out = DX + DB + ZL + JG
    Net = In - Out
    End = (Initial + Net) / (2000 × bd020_90)
    # bd020_90 缺失 → 1.0；Initial 缺失 → 0；soil_mass <= 0 → 0

分布口径（design 决策 4）：end_cd 用 GB 15618-2018 三档；net_cd 用**互斥**三档
（原系统负值/接近平衡重叠，占比可超 100%，本实现修正）；in/out 用相对本批均值三档。
"""
from __future__ import annotations

import csv
import io
import logging
import math
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

LOG = logging.getLogger(__name__)

FIELDS: dict[str, dict[str, Any]] = {
    "in_cd": {"title": "输入通量", "unit": "g/ha/a", "column": "in_cd"},
    "out_cd": {"title": "输出通量", "unit": "g/ha/a", "column": "out_cd"},
    "net_cd": {"title": "净通量", "unit": "g/ha/a", "column": "net_cd"},
    "end_cd": {"title": "当年Cd浓度", "unit": "mg/kg", "column": "end_cd"},
}
FIELD_NAMES: tuple[str, ...] = tuple(FIELDS)

# 输入 CSV 必需列（与原系统列名对齐）
REQUIRED_COLUMNS: tuple[str, ...] = (
    "parcel_id",
    "sample_id",
    "initial_cd",
    "DQCJ_Cd",
    "GGS_Cd",
    "NCP_Cd",
    "DX_Cd",
    "DB_Cd",
    "ZL_Cd",
    "JG_Cd",
)
OPTIONAL_COLUMNS: tuple[str, ...] = ("bd020_90",)
CSV_TO_ATTR: dict[str, str] = {
    "initial_cd": "initial_cd",
    "DQCJ_Cd": "atmospheric_deposition",
    "GGS_Cd": "irrigation_input",
    "NCP_Cd": "agro_chemicals_input",
    "DX_Cd": "groundwater_leaching",
    "DB_Cd": "surface_runoff",
    "ZL_Cd": "grain_removal",
    "JG_Cd": "straw_removal",
    "bd020_90": "bd020_90",
}

SOIL_MASS_KG_HA = 2000.0
DEFAULT_BD020_90 = 1.0
DEFAULT_INITIAL_CD = 0.0
MAX_EXPORT_ROWS = 100000
MAX_PAGE_LIMIT = 1000
DEFAULT_PAGE_LIMIT = 100

END_CD_THRESHOLDS: tuple[float, float] = (0.3, 0.6)
NET_BALANCE = 5.0


class CdFluxError(ValueError):
    """通量核算的输入或数据错误；``code`` 是机器可读问题码。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _require_app_context() -> None:
    from flask import has_app_context

    if not has_app_context():
        raise CdFluxError("no_app_context")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _statistics():
    from framework.domain.other_models import heavy_metal_cd_statistics as statistics

    return statistics


def _spatial():
    from framework.domain.other_models import heavy_metal_cd_spatial as spatial

    return spatial


def _check_field(field: str) -> str:
    field = str(field or "in_cd").strip()
    if field not in FIELDS:
        raise CdFluxError("unknown_field")
    return field


def _check_region(region_type: str | None, region_id: str | None) -> tuple[str | None, str | None]:
    region_type = (region_type or "").strip() or None
    region_id = (region_id or "").strip() or None
    if bool(region_type) != bool(region_id):
        raise CdFluxError("invalid_region")
    if region_type is not None:
        spatial = _spatial()
        if region_type not in spatial.REGION_TYPES:
            raise CdFluxError("invalid_region_type")
    return region_type, region_id


def _region_parcels(region_type: str | None, region_id: str | None, source: str) -> set[str] | None:
    """按来源取归属映射并返回目标区域的地块集合；无区域限制时返回 None。"""
    if region_type is None:
        return None
    spatial = _spatial()
    statistics = _statistics()
    source = statistics.normalize_source(source)
    mapping: dict[str, str] = {}
    if source in ("native", "all"):
        mapping.update(spatial.parcel_region_map(region_type))
    if source in ("ported", "all") and region_type == "township":
        mapping.update(spatial.ported_region_map())
    return {parcel_id for parcel_id, rid in mapping.items() if rid == str(region_id)}


def _ensure_region_exists(region_type: str | None, region_id: str | None) -> None:
    if region_type is None:
        return
    spatial = _spatial()
    if spatial.region_catalog_entry(region_type, region_id) is None:  # type: ignore[arg-type]
        raise CdFluxError("region_not_found")


# ----------------------------- 导入 -----------------------------


def _to_float(raw: Any, *, required: bool) -> float | None:
    text = ("" if raw is None else str(raw)).strip()
    if not text:
        if required:
            raise CdFluxError("invalid_row")
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise CdFluxError("invalid_row") from exc
    if not math.isfinite(value):
        raise CdFluxError("invalid_row")
    return value


def import_csv(content: bytes) -> dict[str, Any]:
    """解析并写入输入表；同键覆盖。返回 inserted/updated/skipped 计数。"""
    _require_app_context()
    from sqlalchemy import select

    from framework.models import CdFluxInput
    from framework.models.user import db

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CdFluxError("invalid_encoding") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CdFluxError("invalid_csv")
    headers = {h.strip() for h in reader.fieldnames if h}
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise CdFluxError(f"missing_columns:{','.join(missing)}")

    rows: list[dict[str, Any]] = []
    skipped = 0
    for raw in reader:
        pid = str(raw.get("parcel_id") or "").strip()
        sid = str(raw.get("sample_id") or "").strip()
        if not pid or not sid:
            skipped += 1
            continue
        record: dict[str, Any] = {"parcel_id": pid, "sample_id": sid}
        try:
            for csv_col, attr in CSV_TO_ATTR.items():
                if csv_col == "initial_cd" or csv_col == "bd020_90":
                    record[attr] = _to_float(raw.get(csv_col), required=False)
                else:
                    record[attr] = _to_float(raw.get(csv_col), required=True)
        except CdFluxError:
            skipped += 1
            continue
        rows.append(record)

    if not rows:
        return {"inserted": 0, "updated": 0, "skipped": skipped, "total": 0}

    existing = {
        (r[0], r[1]): r[2]
        for r in db.session.execute(select(CdFluxInput.parcel_id, CdFluxInput.sample_id, CdFluxInput.id)).all()
    }
    to_insert: list[dict[str, Any]] = []
    to_update: list[dict[str, Any]] = []
    updated_ids: list[int] = []
    for rec in rows:
        key = (rec["parcel_id"], rec["sample_id"])
        if key in existing:
            to_update.append({**rec, "id": existing[key]})
            updated_ids.append(existing[key])
        else:
            to_insert.append(rec)
    if to_insert:
        db.session.bulk_insert_mappings(CdFluxInput, to_insert)
    if to_update:
        db.session.bulk_update_mappings(CdFluxInput, to_update)
    db.session.commit()
    return {
        "inserted": len(to_insert),
        "updated": len(to_update),
        "skipped": skipped,
        "total": len(rows),
        "imported_at": _now_iso(),
    }


# ----------------------------- 计算 -----------------------------


def calculate(
    *, region_type: str | None = None, region_id: str | None = None, source: str = "all"
) -> dict[str, Any]:
    """输入表 → 输出表（覆盖写），返回计数与回退统计。"""
    _require_app_context()
    from sqlalchemy import select

    from framework.models import CdFluxInput, CdFluxOutput
    from framework.models.user import db

    region_type, region_id = _check_region(region_type, region_id)
    _ensure_region_exists(region_type, region_id)
    wanted = _region_parcels(region_type, region_id, source)
    if wanted is not None and not wanted:
        return {"has_data": False, "input_rows": 0, "inserted": 0, "updated": 0, "fallback": {}}

    query = select(
        CdFluxInput.parcel_id,
        CdFluxInput.sample_id,
        CdFluxInput.initial_cd,
        CdFluxInput.atmospheric_deposition,
        CdFluxInput.irrigation_input,
        CdFluxInput.agro_chemicals_input,
        CdFluxInput.groundwater_leaching,
        CdFluxInput.surface_runoff,
        CdFluxInput.grain_removal,
        CdFluxInput.straw_removal,
        CdFluxInput.bd020_90,
    )
    if wanted is not None:
        query = query.where(CdFluxInput.parcel_id.in_(wanted))
    inputs = db.session.execute(query).all()
    if not inputs:
        return {"has_data": False, "input_rows": 0, "inserted": 0, "updated": 0, "fallback": {}}

    existing = {
        (r[0], r[1]): r[2]
        for r in db.session.execute(select(CdFluxOutput.parcel_id, CdFluxOutput.sample_id, CdFluxOutput.id)).all()
    }
    to_insert: list[dict[str, Any]] = []
    to_update: list[dict[str, Any]] = []
    fallback = {"bd020_90": 0, "initial_cd": 0, "non_positive_soil_mass": 0}

    for row in inputs:
        pid, sid = str(row[0]), str(row[1])
        initial = row[2]
        if initial is None:
            initial = DEFAULT_INITIAL_CD
            fallback["initial_cd"] += 1
        bd = row[10]
        if bd is None:
            bd = DEFAULT_BD020_90
            fallback["bd020_90"] += 1
        in_cd = float(row[3]) + float(row[4]) + float(row[5])
        out_cd = float(row[6]) + float(row[7]) + float(row[8]) + float(row[9])
        net_cd = in_cd - out_cd
        soil_mass = SOIL_MASS_KG_HA * float(bd)
        if soil_mass <= 0:
            end_cd = 0.0
            fallback["non_positive_soil_mass"] += 1
        else:
            end_cd = (float(initial) + net_cd) / soil_mass

        payload = {
            "parcel_id": pid,
            "sample_id": sid,
            "in_cd": in_cd,
            "out_cd": out_cd,
            "net_cd": net_cd,
            "end_cd": end_cd,
        }
        key = (pid, sid)
        if key in existing:
            to_update.append({**payload, "id": existing[key]})
        else:
            to_insert.append(payload)

    if to_insert:
        db.session.bulk_insert_mappings(CdFluxOutput, to_insert)
    if to_update:
        db.session.bulk_update_mappings(CdFluxOutput, to_update)
    db.session.commit()
    return {
        "has_data": True,
        "input_rows": len(inputs),
        "inserted": len(to_insert),
        "updated": len(to_update),
        "fallback": fallback,
        "computed_at": _now_iso(),
    }


# ----------------------------- 统计 -----------------------------


def _values(field: str, *, region_type: str | None = None, region_id: str | None = None, source: str = "all") -> list[float]:
    _require_app_context()
    from sqlalchemy import select

    from framework.models import CdFluxOutput
    from framework.models.user import db

    column = getattr(CdFluxOutput, FIELDS[field]["column"])
    query = select(CdFluxOutput.parcel_id, column)
    wanted = _region_parcels(region_type, region_id, source)
    if wanted is not None:
        if not wanted:
            return []
        query = query.where(CdFluxOutput.parcel_id.in_(wanted))
    rows = db.session.execute(query).all()
    values: list[float] = []
    for _pid, value in rows:
        if value is None:
            continue
        v = float(value)
        if math.isfinite(v):
            values.append(v)
    return values


def _distribution(field: str, values: Sequence[float]) -> dict[str, Any]:
    total = len(values)
    if total == 0:
        return {}

    def bucketed(entries: list[tuple[str, int]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """按「数量 / 占比」输出；占比四舍五入后把差额补给末档，保证三档之和恰为 100。"""
        counts = [count for _label, count in entries]
        ratios = [round(count / total * 100, 2) for count in counts]
        if ratios:
            ratios[-1] = round(100.0 - sum(ratios[:-1]), 2)
        payload: dict[str, Any] = {
            label: {"数量": count, "占比": ratios[i]}
            for i, (label, count) in enumerate(entries)
        }
        if extra:
            payload.update(extra)
        return payload

    if field == "end_cd":
        safe = sum(1 for v in values if v < END_CD_THRESHOLDS[0])
        warning = sum(1 for v in values if END_CD_THRESHOLDS[0] <= v < END_CD_THRESHOLDS[1])
        exceed = sum(1 for v in values if v >= END_CD_THRESHOLDS[1])
        return bucketed(
            [
                ("安全区间 (< 0.3 mg/kg)", safe),
                ("预警区间 (0.3-0.6 mg/kg)", warning),
                ("超标区间 (≥ 0.6 mg/kg)", exceed),
            ],
            {"threshold_source": "GB 15618-2018"},
        )
    if field == "net_cd":
        negative = sum(1 for v in values if v < -NET_BALANCE)
        near_zero = sum(1 for v in values if -NET_BALANCE <= v <= NET_BALANCE)
        positive = sum(1 for v in values if v > NET_BALANCE)
        return bucketed(
            [
                ("负通量 (< -5 g/ha/a)", negative),
                ("接近平衡 (-5~5 g/ha/a)", near_zero),
                ("正通量 (> 5 g/ha/a)", positive),
            ],
            {"mutually_exclusive": True},
        )
    mean = sum(values) / total
    low = sum(1 for v in values if v < mean * 0.5)
    medium = sum(1 for v in values if mean * 0.5 <= v < mean * 1.5)
    high = sum(1 for v in values if v >= mean * 1.5)
    return bucketed(
        [
            ("低水平 (< 平均值×0.5)", low),
            ("中等水平 (平均值×0.5~1.5)", medium),
            ("高水平 (≥ 平均值×1.5)", high),
        ],
        {"relative": True, "relative_note": "按本批均值分级，跨批次不可比"},
    )


def statistics(
    field: str = "in_cd",
    *,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
) -> dict[str, Any]:
    field = _check_field(field)
    region_type, region_id = _check_region(region_type, region_id)
    _ensure_region_exists(region_type, region_id)
    statistics_mod = _statistics()
    values = _values(field, region_type=region_type, region_id=region_id, source=source)
    return {
        "field": field,
        "title": FIELDS[field]["title"],
        "unit": FIELDS[field]["unit"],
        "has_data": bool(values),
        "count": len(values),
        "基础统计": statistics_mod.basic_statistics(values) if values else {},
        "分布统计": _distribution(field, values),
    }


# ----------------------------- 点位与明细 -----------------------------


def points_geojson(
    field: str = "in_cd",
    *,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    limit: int = 5000,
) -> dict[str, Any]:
    """通量点位 FeatureCollection（坐标取地块质心）。"""
    field = _check_field(field)
    region_type, region_id = _check_region(region_type, region_id)
    _ensure_region_exists(region_type, region_id)
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise CdFluxError("invalid_limit") from exc
    if limit < 1 or limit > 20000:
        raise CdFluxError("invalid_limit")

    _require_app_context()
    from sqlalchemy import select

    from framework.models import CdFluxOutput, ParcelInfo
    from framework.models.user import db

    column = getattr(CdFluxOutput, FIELDS[field]["column"])
    query = select(
        CdFluxOutput.parcel_id, CdFluxOutput.sample_id, column,
        ParcelInfo.centroid_lon, ParcelInfo.centroid_lat,
    ).join(ParcelInfo, ParcelInfo.parcel_id == CdFluxOutput.parcel_id)
    wanted = _region_parcels(region_type, region_id, source)
    if wanted is not None:
        if not wanted:
            return {"type": "FeatureCollection", "field": field, "count": 0, "features": []}
        query = query.where(CdFluxOutput.parcel_id.in_(wanted))
    rows = db.session.execute(query.limit(limit + 1)).all()
    truncated = len(rows) > limit
    features = []
    for pid, sid, value, lon, lat in rows[:limit]:
        if value is None or lon is None or lat is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": {
                    "parcel_id": pid,
                    "sample_id": sid,
                    "value": float(value),
                    "field": field,
                    "unit": FIELDS[field]["unit"],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "field": field,
        "unit": FIELDS[field]["unit"],
        "coordinate_source": "parcel_centroid",
        "count": len(features),
        "truncated": truncated,
        "features": features,
    }


def list_results(
    field: str = "in_cd",
    *,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    field = _check_field(field)
    region_type, region_id = _check_region(region_type, region_id)
    _ensure_region_exists(region_type, region_id)
    try:
        limit = int(limit)
        offset = int(offset)
    except (TypeError, ValueError) as exc:
        raise CdFluxError("invalid_limit") from exc
    if limit < 1 or limit > MAX_PAGE_LIMIT or offset < 0:
        raise CdFluxError("invalid_limit")

    _require_app_context()
    from sqlalchemy import func, select

    from framework.models import CdFluxOutput
    from framework.models.user import db

    column = getattr(CdFluxOutput, FIELDS[field]["column"])
    base = select(CdFluxOutput.parcel_id, CdFluxOutput.sample_id, column)
    wanted = _region_parcels(region_type, region_id, source)
    if wanted is not None:
        if not wanted:
            return {"total": 0, "limit": limit, "offset": offset, "rows": []}
        base = base.where(CdFluxOutput.parcel_id.in_(wanted))
    total = db.session.execute(select(func.count()).select_from(base.subquery())).scalar() or 0
    rows = db.session.execute(base.order_by(CdFluxOutput.parcel_id, CdFluxOutput.sample_id).offset(offset).limit(limit)).all()
    return {
        "field": field,
        "unit": FIELDS[field]["unit"],
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "rows": [
            {"parcel_id": pid, "sample_id": sid, "value": None if value is None else float(value)}
            for pid, sid, value in rows
        ],
    }


def export_csv(
    field: str = "in_cd",
    *,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    max_rows: int = MAX_EXPORT_ROWS,
) -> tuple[str, int]:
    """返回 (CSV 文本, 行数)；超过 max_rows 抛错误而不是静默截断。"""
    field = _check_field(field)
    region_type, region_id = _check_region(region_type, region_id)
    _ensure_region_exists(region_type, region_id)
    _require_app_context()
    from sqlalchemy import func, select

    from framework.models import CdFluxOutput
    from framework.models.user import db

    column = getattr(CdFluxOutput, FIELDS[field]["column"])
    base = select(CdFluxOutput.parcel_id, CdFluxOutput.sample_id, column)
    wanted = _region_parcels(region_type, region_id, source)
    if wanted is not None:
        if not wanted:
            return "", 0
        base = base.where(CdFluxOutput.parcel_id.in_(wanted))
    rows = db.session.execute(base.order_by(CdFluxOutput.parcel_id, CdFluxOutput.sample_id)).all()
    if len(rows) > max_rows:
        raise CdFluxError("too_many_rows")
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["parcel_id", "sample_id", field, "unit"])
    for pid, sid, value in rows:
        writer.writerow([pid, sid, "" if value is None else float(value), FIELDS[field]["unit"]])
    return out.getvalue(), len(rows)


# ----------------------------- 地图（复用阶段 4 引擎） -----------------------------


def _legend(field: str, raster) -> dict[str, Any]:
    import numpy as np

    valid = raster[~np.isnan(raster)]
    if field == "end_cd":
        return {
            "mode": "threshold",
            "bounds": [0.0, END_CD_THRESHOLDS[0], END_CD_THRESHOLDS[1], float("inf")],
            "colors": ["#15B392", "#FFEB55", "#D91656"],
            "labels": ["< 0.3 mg/kg", "0.3 ~ 0.6 mg/kg", "≥ 0.6 mg/kg"],
            "note": "GB 15618-2018 三档展示分级",
        }
    if field == "net_cd":
        return {
            "mode": "threshold",
            "bounds": [float(np.nanmin(valid)) - 1.0, -NET_BALANCE, NET_BALANCE, float(np.nanmax(valid)) + 1.0],
            "colors": ["#4F959D", "#FFF085", "#BE3D2A"],
            "labels": ["负通量 (< -5)", "接近平衡 (-5~5)", "正通量 (> 5)"],
            "note": "互斥三档；单位 g/ha/a",
        }
    quantiles = np.nanpercentile(valid, [0, 20, 40, 60, 80, 90, 100]) if valid.size else []
    bounds = [float(v) for v in quantiles]
    labels = [f"{bounds[i]:.4g} ~ {bounds[i + 1]:.4g}" for i in range(len(bounds) - 1)] if bounds else []
    return {
        "mode": "quantile",
        "bounds": bounds,
        "colors": ["#15B392", "#73EC8B", "#FFEB55", "#EE66A6", "#D91656", "#640D5F"],
        "labels": labels,
        "note": "相对分级（按有效像元分位数），跨批次不可比",
    }


def visualize(
    field: str = "in_cd",
    *,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    resolution_factor: float = 4.0,
) -> dict[str, Any]:
    """生成通量地图/直方图，复用阶段 4 的栅格化与渲染引擎。"""
    field = _check_field(field)
    region_type, region_id = _check_region(region_type, region_id)
    _ensure_region_exists(region_type, region_id)
    from framework.domain.other_models import heavy_metal_cd_visualization as viz

    points_payload = points_geojson(
        field, region_type=region_type, region_id=region_id, source=source, limit=20000
    )
    if not points_payload["features"]:
        raise CdFluxError("no_data")
    points = [
        (f["properties"]["parcel_id"], f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1], f["properties"]["value"])
        for f in points_payload["features"]
    ]
    template = viz.load_template()
    boundary = viz._region_boundary(region_type, region_id)  # noqa: SLF001
    raster, transform, boundary_source, dropped, _effective = viz._rasterize(  # noqa: SLF001
        points,
        template=template,
        resolution_factor=float(resolution_factor),
        boundary=boundary,
        enable_interpolation=False,
        interpolation_method="nearest",
    )
    legend = _legend(field, raster)
    artifact_id = __import__("uuid").uuid4().hex
    out_dir = viz.VISUALIZATION_ROOT / f"flux_{field}" / artifact_id
    out_dir.mkdir(parents=True, exist_ok=True)
    map_path = out_dir / viz.KINDS["map"]
    hist_path = out_dir / viz.KINDS["histogram"]
    title = {"in_cd": "Cd Input Flux", "out_cd": "Cd Output Flux", "net_cd": "Cd Net Flux", "end_cd": "Cd End Concentration"}[field]
    viz._render_map(raster, transform, boundary, legend, title=title, out_path=map_path)  # noqa: SLF001
    viz._render_histogram(raster, title=f"{title} Frequency", xlabel=f"{title} ({FIELDS[field]['unit']})", out_path=hist_path)  # noqa: SLF001
    meta = {
        "artifact_id": artifact_id,
        "field": field,
        "title": FIELDS[field]["title"],
        "unit": FIELDS[field]["unit"],
        "request": {"region_type": region_type, "region_id": region_id, "source": source, "resolution_factor": resolution_factor},
        "legend": legend,
        "boundary_source": boundary_source,
        "points": len(points),
        "points_dropped_out_of_template": dropped,
        "files": {"map": f"flux_{field}/{artifact_id}/{viz.KINDS['map']}", "histogram": f"flux_{field}/{artifact_id}/{viz.KINDS['histogram']}"},
        "generated_at": _now_iso(),
    }
    (out_dir / "meta.json").write_text(__import__("json").dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def artifact_path(artifact_id: str, kind: str):
    """下载校验转交阶段 4 的实现（同一产物根目录）。"""
    from framework.domain.other_models import heavy_metal_cd_visualization as viz

    return viz.artifact_path(artifact_id, kind)
