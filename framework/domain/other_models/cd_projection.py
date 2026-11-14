"""未来 Cd 浓度情景预测（阶段 7）。

公式（design 决策 1，逐字照抄原系统）::

    Future_Cd = (Initial_Cd + Net_Cd × years) / (2000 × bulk_density_g_cm3)
    # 容重缺失 → 1.0；Initial_Cd 缺失 → 0；土重 <= 0 → 0

v2 基线适配（2026-11-14，`docs/cd-removal-projection-v2-alignment.md`）：

- 取数由 v1 ``cd_flux_input/cd_flux_output`` 改为 v2 ``cd_flux_input_v2`` /
  ``cd_flux_output_v2``，按 ``(input_id, input_revision)`` 取**当前修订**的输出行，
  并跳过 ``contract_version='legacy_v1'`` 的输入行（v2 计算同样跳过）；
- **土重口径严格照抄原系统**：分母固定 ``2000 × bulk_density_g_cm3``，
  **不读 ``soil_depth_m``**。这与 v2 ``calculate`` 的 ``end_cd``（按
  ``soil_depth_m × bulk_density × 1e7`` 推导）在耕层 0.2m 时数值等价、
  其他深度会有差异；该差异已登记到 ``docs/cd-legacy-known-issues.md``；
- v2 的 ``initial_cd`` 为 g/ha 储量、``net_cd`` 为 g/ha/a，量纲链与 v1 一致，
  因此除取数与容重列名外公式本体不变。

区域参数沿用原系统行为（``area_filter: not_applied``，仅记录不参与查询）；
统计口径逐项照抄原系统 ``predict_future_cd``：样本标准差（ddof=1）+ 线性插值分位数，
与阶段 2 的总体标准差不同（有意偏差，见 ``docs/cd-legacy-known-issues.md``）。
"""
from __future__ import annotations

import math
from typing import Any, Sequence

MAX_YEARS = 100
# 原系统固定土重常数（等价 0.2m 耕层 × 1.0 容重口径），不随 soil_depth_m 变化。
SOIL_MASS_KG_HA = 2000.0
DEFAULT_BULK_DENSITY = 1.0
DEFAULT_INITIAL_CD = 0.0
END_CD_THRESHOLDS: tuple[float, float] = (0.3, 0.6)
MAX_EXPORT_ROWS = 100000
FORMULA = "Future_Cd = (Initial_Cd + Net_Cd × years) / (2000 × bulk_density_g_cm3)"
SOIL_MASS_NOTE = "土重常数 2000 沿用原系统，不读 soil_depth_m（0.2m 耕层口径）"


class CdProjectionError(ValueError):
    """预测的输入或数据错误；``code`` 是机器可读问题码。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _require_app_context() -> None:
    from flask import has_app_context

    if not has_app_context():
        raise CdProjectionError("no_app_context")


def _statistics():
    from framework.domain.other_models import heavy_metal_cd_statistics as statistics

    return statistics


def _spatial():
    from framework.domain.other_models import heavy_metal_cd_spatial as spatial

    return spatial


def _check_years_single(value: Any) -> int:
    try:
        years = int(value)
    except (TypeError, ValueError) as exc:
        raise CdProjectionError("invalid_years") from exc
    if years < 1 or years > MAX_YEARS:
        raise CdProjectionError("invalid_years")
    return years


def _check_years(value: Any) -> list[int]:
    if isinstance(value, (list, tuple)):
        if not value:
            raise CdProjectionError("invalid_years")
        return sorted({_check_years_single(v) for v in value})
    return [_check_years_single(value)]


def _check_accounting_year(value: Any) -> int | None:
    """v2 核算年度筛选；空值表示不限年度（保持原系统全量行为）。"""
    if value is None or value == "":
        return None
    text = str(value).strip()
    if isinstance(value, bool) or not text.isdigit():
        raise CdProjectionError("invalid_accounting_year")
    year = int(text)
    if not 1 <= year <= 9999:
        raise CdProjectionError("invalid_accounting_year")
    return year


def _check_region(region_type: str | None, region_id: str | None) -> tuple[str | None, str | None]:
    region_type = (region_type or "").strip() or None
    region_id = (region_id or "").strip() or None
    if bool(region_type) != bool(region_id):
        raise CdProjectionError("invalid_region")
    if region_type is not None:
        spatial = _spatial()
        if region_type not in spatial.REGION_TYPES:
            raise CdProjectionError("invalid_region_type")
    return region_type, region_id


def _require_region(region_type: str | None, region_id: str | None) -> None:
    if region_type is None:
        return
    spatial = _spatial()
    if spatial.region_catalog_entry(region_type, region_id) is None:  # type: ignore[arg-type]
        raise CdProjectionError("region_not_found")


def _normalize_source(source: Any) -> str:
    statistics = _statistics()
    try:
        return statistics.normalize_source(source)
    except Exception as exc:
        code = str(getattr(exc, "code", "invalid_source"))
        raise CdProjectionError(code) from exc


def _base_rows(
    *,
    region_type: str | None,
    region_id: str | None,
    source: str,
    accounting_year: int | None = None,
) -> list[tuple[str, str, float | None, float | None, float | None, float | None, float | None]]:
    """(parcel_id, sample_id, initial_cd, bulk_density_g_cm3, net_cd, lon, lat)

    与原系统一致：``area`` 参数只用于记录，**不参与查询**（原系统源码中该筛选为 TODO，
    实际查全量）。该行为已记录到 ``docs/cd-legacy-known-issues.md``，待后续讨论。

    v2 侧的 ``accounting_year`` 是**数据维度筛选**（同地块样点可能有多年份/多来源行），
    默认不限年度，保持与原系统「全量一套结果」的可比性；显式给出时按年度取数。
    """
    _require_app_context()
    from sqlalchemy import text

    from framework.models.user import db

    source = _normalize_source(source)
    clauses = ["i.contract_version <> 'legacy_v1'"]
    params: dict[str, Any] = {}
    if source != "all":
        clauses.append("i.source = :source")
        params["source"] = source
    if accounting_year is not None:
        clauses.append("i.accounting_year = :accounting_year")
        params["accounting_year"] = accounting_year
    sql = (
        "SELECT i.parcel_id, i.sample_id, i.initial_cd, i.bulk_density_g_cm3, o.net_cd, "
        "p.centroid_lon, p.centroid_lat "
        "FROM cd_flux_input_v2 i "
        "JOIN cd_flux_output_v2 o ON o.input_id = i.id AND o.input_revision = i.input_revision "
        "AND o.calculation_version = 'cd_flux_mass_balance_v2' "
        "JOIN parcel_info p ON p.parcel_id = i.parcel_id "
        "WHERE " + " AND ".join(clauses) + " ORDER BY i.id"
    )
    rows = db.session.execute(text(sql), params).all()
    return [(str(r[0]), str(r[1]), r[2], r[3], r[4], r[5], r[6]) for r in rows]


def project_values(
    rows: Sequence[tuple], years: int
) -> tuple[list[tuple[str, str, float | None, float | None, float]], dict[str, int]]:
    """返回 (预测行, 回退计数)；预测行 = (parcel, sample, lon, lat, future_cd)。"""
    fallback = {"bulk_density_g_cm3": 0, "initial_cd": 0, "non_positive_soil_mass": 0, "skipped": 0}
    predictions: list[tuple[str, str, float | None, float | None, float]] = []
    for pid, sid, initial_cd, bulk_density, net_cd, lon, lat in rows:
        if net_cd is None:
            fallback["skipped"] += 1
            continue
        if initial_cd is None:
            initial_cd = DEFAULT_INITIAL_CD
            fallback["initial_cd"] += 1
        if bulk_density is None:
            bulk_density = DEFAULT_BULK_DENSITY
            fallback["bulk_density_g_cm3"] += 1
        soil_mass = SOIL_MASS_KG_HA * float(bulk_density)
        if soil_mass <= 0:
            future = 0.0
            fallback["non_positive_soil_mass"] += 1
        else:
            future = (float(initial_cd) + float(net_cd) * years) / soil_mass
        predictions.append((pid, sid, lon, lat, future))
    return predictions, fallback


def _end_cd_distribution(values: Sequence[float]) -> dict[str, Any]:
    total = len(values)
    if total == 0:
        return {}
    safe = sum(1 for v in values if v < END_CD_THRESHOLDS[0])
    warning = sum(1 for v in values if END_CD_THRESHOLDS[0] <= v < END_CD_THRESHOLDS[1])
    exceed = sum(1 for v in values if v >= END_CD_THRESHOLDS[1])
    counts = [safe, warning, exceed]
    ratios = [round(c / total * 100, 2) for c in counts]
    ratios[-1] = round(100.0 - sum(ratios[:-1]), 2)
    return {
        "安全区间 (< 0.3 mg/kg)": {"数量": safe, "占比": ratios[0]},
        "预警区间 (0.3-0.6 mg/kg)": {"数量": warning, "占比": ratios[1]},
        "超标区间 (≥ 0.6 mg/kg)": {"数量": exceed, "占比": ratios[2]},
        "threshold_source": "GB 15618-2018",
    }


def _stats(values: Sequence[float]) -> dict[str, Any]:
    """统计口径逐项照抄原系统 ``predict_future_cd``：

    ``count / mean / std / min / max / median / percentile_25 / percentile_75``，
    其中 std 为 **样本标准差**（ddof=1），分位数为线性插值（numpy 默认）。
    该口径与阶段 2 的总体标准差不同，已记录到 ``docs/cd-legacy-known-issues.md``。
    """
    import numpy as np

    if not values:
        return {"has_data": False, "count": 0}
    arr = np.asarray(values, dtype="float64")
    count = int(arr.size)
    return {
        "has_data": True,
        "count": count,
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=1)) if count > 1 else None,
        "min": float(arr.min()),
        "max": float(arr.max()),
        "median": float(np.median(arr)),
        "percentile_25": float(np.quantile(arr, 0.25)),
        "percentile_75": float(np.quantile(arr, 0.75)),
        "note": "恒定净通量线性外推的情景推算，非实测预测",
    }


def predict(
    years: Any = 10,
    *,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    accounting_year: Any = None,
) -> dict[str, Any]:
    """多年份情景：按年份分组返回统计与回退计数。"""
    years_list = _check_years(years)
    region_type, region_id = _check_region(region_type, region_id)
    _require_region(region_type, region_id)
    accounting_year_value = _check_accounting_year(accounting_year)
    rows = _base_rows(
        region_type=region_type,
        region_id=region_id,
        source=source,
        accounting_year=accounting_year_value,
    )
    if not rows:
        return {
            "has_data": False,
            "years": years_list,
            "unit": "mg/kg",
            "accounting_year": accounting_year_value,
            "scenarios": {},
        }

    scenarios: dict[str, Any] = {}
    for y in years_list:
        preds, fallback = project_values(rows, y)
        values = [p[4] for p in preds]
        scenarios[str(y)] = {**_stats(values), "fallback": fallback}
    return {
        "has_data": True,
        "years": years_list,
        "unit": "mg/kg",
        "accounting_year": accounting_year_value,
        "formula": FORMULA,
        "soil_mass_note": SOIL_MASS_NOTE,
        "request": {
            "region_type": region_type,
            "region_id": region_id,
            "source": source,
            "accounting_year": accounting_year_value,
        },
        "area_filter": "not_applied",
        "area_filter_note": "与原系统一致：区域参数仅记录，不参与查询",
        "scenarios": scenarios,
    }


def statistics(
    years: Any = 10,
    *,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    accounting_year: Any = None,
) -> dict[str, Any]:
    """单年份完整统计。"""
    years_value = _check_years_single(years)
    region_type, region_id = _check_region(region_type, region_id)
    _require_region(region_type, region_id)
    accounting_year_value = _check_accounting_year(accounting_year)
    rows = _base_rows(
        region_type=region_type,
        region_id=region_id,
        source=source,
        accounting_year=accounting_year_value,
    )
    if not rows:
        return {
            "has_data": False,
            "years": years_value,
            "unit": "mg/kg",
            "accounting_year": accounting_year_value,
        }
    preds, fallback = project_values(rows, years_value)
    values = [p[4] for p in preds]
    return {
        "years": years_value,
        "unit": "mg/kg",
        "accounting_year": accounting_year_value,
        **_stats(values),
        "fallback": fallback,
        "area": region_id,
        "area_filter": "not_applied",
        "area_filter_note": "与原系统一致：区域参数仅记录，不参与查询",
    }


def points_geojson(
    years: Any = 10,
    *,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    accounting_year: Any = None,
    limit: int = 5000,
) -> dict[str, Any]:
    years_value = _check_years_single(years)
    region_type, region_id = _check_region(region_type, region_id)
    _require_region(region_type, region_id)
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise CdProjectionError("invalid_limit") from exc
    if limit < 1 or limit > 20000:
        raise CdProjectionError("invalid_limit")

    accounting_year_value = _check_accounting_year(accounting_year)
    rows = _base_rows(
        region_type=region_type,
        region_id=region_id,
        source=source,
        accounting_year=accounting_year_value,
    )
    preds, fallback = project_values(rows, years_value)
    features = []
    truncated = len(preds) > limit
    for pid, sid, lon, lat, future in preds[:limit]:
        if lon is None or lat is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": {
                    "parcel_id": pid,
                    "sample_id": sid,
                    "future_cd": future,
                    "years": years_value,
                    "accounting_year": accounting_year_value,
                    "unit": "mg/kg",
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "years": years_value,
        "unit": "mg/kg",
        "accounting_year": accounting_year_value,
        "coordinate_source": "parcel_centroid",
        "count": len(features),
        "truncated": truncated,
        "fallback": fallback,
        "features": features,
    }


def export_csv(
    years: Any = 10,
    *,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    accounting_year: Any = None,
    max_rows: int = MAX_EXPORT_ROWS,
) -> tuple[str, int]:
    years_value = _check_years_single(years)
    region_type, region_id = _check_region(region_type, region_id)
    _require_region(region_type, region_id)
    accounting_year_value = _check_accounting_year(accounting_year)
    rows = _base_rows(
        region_type=region_type,
        region_id=region_id,
        source=source,
        accounting_year=accounting_year_value,
    )
    preds, _fallback = project_values(rows, years_value)
    if len(preds) > max_rows:
        raise CdProjectionError("too_many_rows")
    import csv
    import io

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["parcel_id", "sample_id", "future_cd", "years", "unit"])
    for pid, sid, _lon, _lat, future in preds:
        writer.writerow([pid, sid, future, years_value, "mg/kg"])
    return out.getvalue(), len(preds)


def _legend(raster) -> dict[str, Any]:
    import numpy as np

    valid = raster[~np.isnan(raster)]
    return {
        "mode": "threshold",
        "bounds": [0.0, END_CD_THRESHOLDS[0], END_CD_THRESHOLDS[1], float("inf")],
        "colors": ["#15B392", "#FFEB55", "#D91656"],
        "labels": ["< 0.3 mg/kg", "0.3 ~ 0.6 mg/kg", "≥ 0.6 mg/kg"],
        "note": "GB 15618-2018 三档展示分级（未来情景推算）",
        "valid_pixels": int(valid.size),
    }


def visualize(
    years: Any = 10,
    *,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    accounting_year: Any = None,
    resolution_factor: float = 4.0,
) -> dict[str, Any]:
    """未来 Cd 空间分布地图/直方图，复用阶段 4 渲染引擎。"""
    years_value = _check_years_single(years)
    region_type, region_id = _check_region(region_type, region_id)
    _require_region(region_type, region_id)
    from framework.domain.other_models import heavy_metal_cd_visualization as viz

    accounting_year_value = _check_accounting_year(accounting_year)
    rows = _base_rows(
        region_type=region_type,
        region_id=region_id,
        source=source,
        accounting_year=accounting_year_value,
    )
    preds, fallback = project_values(rows, years_value)
    points = [(pid, lon, lat, future) for pid, _sid, lon, lat, future in preds if lon is not None and lat is not None]
    if not points:
        raise CdProjectionError("no_data")

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
    legend = _legend(raster)
    import uuid

    artifact_id = uuid.uuid4().hex
    out_dir = viz.VISUALIZATION_ROOT / f"projection_{years_value}" / artifact_id
    out_dir.mkdir(parents=True, exist_ok=True)
    map_path = out_dir / viz.KINDS["map"]
    hist_path = out_dir / viz.KINDS["histogram"]
    title = f"Cd Concentration after {years_value} years"
    viz._render_map(raster, transform, boundary, legend, title=title, out_path=map_path)  # noqa: SLF001
    viz._render_histogram(raster, title=f"{title} Frequency", xlabel="Cd Content (mg/kg)", out_path=hist_path)  # noqa: SLF001
    meta = {
        "artifact_id": artifact_id,
        "years": years_value,
        "unit": "mg/kg",
        "accounting_year": accounting_year_value,
        "request": {
            "region_type": region_type,
            "region_id": region_id,
            "source": source,
            "accounting_year": accounting_year_value,
            "resolution_factor": resolution_factor,
        },
        "legend": legend,
        "boundary_source": boundary_source,
        "points": len(points),
        "points_dropped_out_of_template": dropped,
        "fallback": fallback,
        "files": {"map": f"projection_{years_value}/{artifact_id}/{viz.KINDS['map']}", "histogram": f"projection_{years_value}/{artifact_id}/{viz.KINDS['histogram']}"},
        "generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "note": "恒定净通量线性外推的情景推算，非实测预测",
    }
    (out_dir / "meta.json").write_text(__import__("json").dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta
