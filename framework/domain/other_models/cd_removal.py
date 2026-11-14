"""Cd 移除项计算（阶段 6：籽粒/秸秆移除、写回 v2 输入表并触发通量重算）。

公式来源：原系统 ``app/services/cd_flux_removal_service.py``（design 决策 1，逐项照抄）::

    grain = exp(ln_crop_cd) × f11 × 0.5 × 15 / 1000                          # g/ha/a
    straw = exp(ln_crop_cd) / (exp(ln_crop_cd)×0.76 − 0.0034) × f11 × 0.5 × 15 / 1000

系数语义（量纲推演，勿擅改）：``0.5`` = 斤→kg，``15`` = 亩→ha，``1000`` = mg→g；
``f11`` = 作物亩产量（斤/亩，原系统模型默认 800）。

v2 基线适配（2026-11-14，`docs/cd-removal-projection-v2-alignment.md`）：

- 写回目标由 v1 ``cd_flux_input`` 改为 v2 ``cd_flux_input_v2``；
- v2 唯一键为 ``(source, parcel_id, sample_id, accounting_year)``，而作物结果表
  ``cd_crop_prediction_result`` 没有年度字段，无法自动推导，因此**写回必须显式给出
  ``year``**（技术必然，不是可选项）；
- 写回按 ``select_inputs`` 返回的 ``id`` 精确定位，只更新 ``grain_removal`` /
  ``straw_removal`` 两列并把 ``input_revision`` 递增，不触碰其他列；
- ``contract_version='legacy_v1'`` 的行不参与计算也不写回，跳过数在响应中披露；
- 同一 ``(parcel_id, sample_id)`` 在所选范围内命中多个来源时视为歧义，不写回并披露，
  避免批量写错行；
- 重算调用 ``cd_flux_v2.calculate(**scope)``（v2 内部会跳过 legacy 行）。

与阶段 5 的关系：只更新籽粒/秸秆两个分量，随后触发 v2 通量重算；写回与重算分别报告
状态（design 决策 4）。地下渗漏 / 地表径流在原系统没有计算逻辑（两个 update 函数是
空壳），数值来自输入表 ``groundwater_leaching / surface_runoff``，本模块只读不计算。

统计 / 点位 / 导出 / 地图复用阶段 2 的 8 项基础统计、阶段 3 的归属依据、阶段 4 的
渲染引擎与阶段 5 的相对三档分布。
"""
from __future__ import annotations

import csv
import io
import json
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

LOG = logging.getLogger(__name__)

DEFAULT_F11 = 800.0
F11_DEFAULT = DEFAULT_F11  # 路由与调用方沿用原名
F11_MIN = 0.0
F11_MAX = 100000.0
# 0.5（斤→kg）× 15（亩→ha）/ 1000（mg→g）
CONVERSION_FACTOR = 0.5 * 15 / 1000
STRAW_DENOM_FACTOR = 0.76
STRAW_DENOM_OFFSET = 0.0034

MAX_EXPORT_ROWS = 100000
MAX_POINT_LIMIT = 20000
DEFAULT_POINT_LIMIT = 5000
SKIPPED_SAMPLE_LIMIT = 20
LOOKUP_CHUNK = 5000

FIELDS: dict[str, dict[str, Any]] = {
    "grain": {"title": "籽粒移除", "unit": "g/ha/a", "kind": "computed"},
    "straw": {"title": "秸秆移除", "unit": "g/ha/a", "kind": "computed"},
    "leaching": {
        "title": "地下渗漏",
        "unit": "g/ha/a",
        "kind": "input",
        "column": "groundwater_leaching",
    },
    "runoff": {
        "title": "地表径流",
        "unit": "g/ha/a",
        "kind": "input",
        "column": "surface_runoff",
    },
}
FIELD_NAMES: tuple[str, ...] = tuple(FIELDS)

# 与原系统一致的公式说明，随响应与产物元信息输出，避免调用方自行猜测口径。
FORMULA_NOTE = (
    "grain = exp(ln_crop_cd) × f11 × 0.5 × 15 / 1000；"
    "straw = exp(ln_crop_cd) / (exp(ln_crop_cd)×0.76 − 0.0034) × f11 × 0.5 × 15 / 1000；"
    "0.5=斤→kg，15=亩→ha，1000=mg→g"
)
STRAW_COEFFICIENT_NOTE = "0.76 / 0.0034 为原系统经验系数，出处未考证，照抄不改"
INPUT_FIELD_NOTE = "直接读取 v2 输入表 groundwater_leaching/surface_runoff，不做物理计算（原系统同样为空壳）"
YEAR_NOTE = "v2 输入表年度维度：write_back 必须显式提供 accounting_year"


class CdRemovalError(ValueError):
    """移除项计算的输入或数据错误；``code`` 是机器可读问题码。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


# ----------------------------- 校验与工具 -----------------------------


def _require_app_context() -> None:
    from flask import has_app_context

    if not has_app_context():
        raise CdRemovalError("no_app_context")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _statistics():
    from framework.domain.other_models import heavy_metal_cd_statistics as statistics

    return statistics


def _cd_flux():
    from framework.domain.other_models import cd_flux

    return cd_flux


def _cd_flux_v2():
    from framework.domain.other_models import cd_flux_v2

    return cd_flux_v2


def _check_field(field: str) -> str:
    field = str(field or "grain").strip()
    if field not in FIELDS:
        raise CdRemovalError("unknown_field")
    return field


def _check_f11(value: Any) -> float:
    if value is None or value == "":
        return DEFAULT_F11
    try:
        f11 = float(value)
    except (TypeError, ValueError) as exc:
        raise CdRemovalError("invalid_f11") from exc
    if not math.isfinite(f11) or f11 <= F11_MIN or f11 > F11_MAX:
        raise CdRemovalError("invalid_f11")
    return f11


def _check_year(value: Any) -> int | None:
    """v2 年度参数：空值返回 None，非数字或越界抛 ``invalid_year``。"""
    if value is None or value == "":
        return None
    text = str(value).strip()
    if isinstance(value, bool) or not text.isdigit():
        raise CdRemovalError("invalid_year")
    year = int(text)
    if not 1 <= year <= 9999:
        raise CdRemovalError("invalid_year")
    return year


def _check_region(region_type: str | None, region_id: str | None) -> tuple[str | None, str | None]:
    cd_flux = _cd_flux()
    try:
        return cd_flux._check_region(region_type, region_id)  # noqa: SLF001
    except cd_flux.CdFluxError as exc:
        raise CdRemovalError(exc.code) from exc


def _ensure_region_exists(region_type: str | None, region_id: str | None) -> None:
    cd_flux = _cd_flux()
    try:
        cd_flux._ensure_region_exists(region_type, region_id)  # noqa: SLF001
    except cd_flux.CdFluxError as exc:
        raise CdRemovalError(exc.code) from exc


def _normalize_source(source: Any) -> str:
    statistics = _statistics()
    try:
        return statistics.normalize_source(source)
    except Exception as exc:  # CdStatisticsError 等，统一转成本模块问题码
        code = str(getattr(exc, "code", "invalid_source"))
        raise CdRemovalError(code) from exc


def _scope(
    region_type: str | None,
    region_id: str | None,
    source: Any,
    year: Any = None,
    *,
    apply_region: bool = False,
) -> tuple[str, str | None, str | None, int | None, set[str] | None]:
    """校验区域/来源/年度，返回 (source, region_type, region_id, year, 目标地块或 None)。

    与原系统一致：移除**计算**按全量执行（``apply_region=False``，area 仅记录）；
    统计/点位/导出按区域过滤（``apply_region=True``，对应原系统按乡镇空间过滤的统计入口）。
    """
    region_type, region_id = _check_region(region_type, region_id)
    _ensure_region_exists(region_type, region_id)
    source = _normalize_source(source)
    year = _check_year(year)
    wanted = None
    if apply_region:
        wanted = _cd_flux()._region_parcels(region_type, region_id, source)  # noqa: SLF001
    return source, region_type, region_id, year, wanted


# ----------------------------- 公式 -----------------------------


def _evaluate(ln_value: float, f11: float) -> tuple[float | None, float | None, float | None, str | None]:
    """返回 (crop_cd, grain, straw, reason)；``reason`` 非空表示该样点相应分量被跳过。"""
    try:
        crop = math.exp(float(ln_value))
    except (OverflowError, ValueError):
        return None, None, None, "invalid_value"
    if not math.isfinite(crop) or crop < 0:
        return None, None, None, "invalid_value"
    grain = crop * f11 * CONVERSION_FACTOR
    denominator = crop * STRAW_DENOM_FACTOR - STRAW_DENOM_OFFSET
    if denominator <= 0:
        return crop, grain, None, "invalid_denominator"
    straw = (crop / denominator) * f11 * CONVERSION_FACTOR
    return crop, grain, straw, None


def _crop_rows(source: str, wanted: set[str] | None) -> Sequence[Any]:
    from sqlalchemy import select

    from framework.models import CdCropPredictionResult
    from framework.models.user import db

    statistics = _statistics()
    query = select(
        CdCropPredictionResult.parcel_id,
        CdCropPredictionResult.sample_id,
        CdCropPredictionResult.ln_crop_cd,
    )
    query = statistics.source_filter(query, CdCropPredictionResult, source)
    if wanted is not None:
        if not wanted:
            return []
        query = query.where(CdCropPredictionResult.parcel_id.in_(sorted(wanted)))
    return db.session.execute(
        query.order_by(CdCropPredictionResult.parcel_id, CdCropPredictionResult.sample_id)
    ).all()


def _compute_all(f11: float, *, source: str, wanted: set[str] | None) -> dict[str, Any]:
    """遍历作物 Cd 结果，返回籽粒/秸秆两条序列与跳过统计。"""
    grain: list[tuple[str, str, float]] = []
    straw: list[tuple[str, str, float]] = []
    skipped_samples: list[dict[str, Any]] = []
    invalid_denominator = 0
    invalid_value = 0
    rows = _crop_rows(source, wanted)
    for pid, sid, ln_value in rows:
        crop, grain_value, straw_value, reason = _evaluate(ln_value, f11)
        if reason == "invalid_value":
            invalid_value += 1
            continue
        grain.append((str(pid), str(sid), float(grain_value)))
        if reason == "invalid_denominator":
            invalid_denominator += 1
            if len(skipped_samples) < SKIPPED_SAMPLE_LIMIT:
                skipped_samples.append(
                    {"parcel_id": str(pid), "sample_id": str(sid), "crop_cd": float(crop)}
                )
            continue
        straw.append((str(pid), str(sid), float(straw_value)))
    return {
        "crop_rows": len(rows),
        "grain": grain,
        "straw": straw,
        "skipped_invalid_denominator": invalid_denominator,
        "skipped_invalid_value": invalid_value,
        "skipped_samples": skipped_samples,
        "skipped_samples_truncated": invalid_denominator > len(skipped_samples),
    }


def _summary(values: Iterable[float], unit: str) -> dict[str, Any]:
    """单分量摘要：count / mean / min / max + 阶段 2 的 8 项基础统计。"""
    statistics = _statistics()
    series = list(values)
    if not series:
        return {"count": 0, "unit": unit, "mean": None, "min": None, "max": None, "基础统计": {}}
    stats = statistics.basic_statistics(series)
    return {
        "count": len(series),
        "unit": unit,
        "mean": stats["均值"],
        "min": stats["最小值"],
        "max": stats["最大值"],
        "基础统计": stats,
    }


def _preview(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(items),
        "preview": list(items[:SKIPPED_SAMPLE_LIMIT]),
        "truncated": len(items) > SKIPPED_SAMPLE_LIMIT,
    }


# ----------------------------- 写回与重算 -----------------------------


def _write_back(
    grain: Sequence[tuple[str, str, float]],
    straw: Sequence[tuple[str, str, float]],
    *,
    source: str,
    year: int,
) -> dict[str, Any]:
    """按 v2 唯一键写回 ``grain_removal``/``straw_removal`` 并递增 ``input_revision``。

    只更新这两列，其他列保持原值；``legacy_v1`` 行跳过；同一 (parcel, sample) 命中多个
    来源时判为歧义，不写回。返回计数与样本预览，供调用方披露。
    """
    _require_app_context()
    from sqlalchemy import text

    from framework.models.user import db

    flux_v2 = _cd_flux_v2()

    payload: dict[tuple[str, str], dict[str, Any]] = {}
    for pid, sid, value in grain:
        payload.setdefault((pid, sid), {})["grain_removal"] = value
    straw_keys: set[tuple[str, str]] = set()
    for pid, sid, value in straw:
        payload.setdefault((pid, sid), {})["straw_removal"] = value
        straw_keys.add((pid, sid))
    result: dict[str, Any] = {
        "updated": 0,
        "missing": [],
        "straw_uncovered": [],
        "legacy_skipped": 0,
        "ambiguous": [],
    }
    if not payload:
        return result

    rows, _coverage = flux_v2.select_inputs(source=source, year=year)
    index: dict[tuple[str, str], list[Any]] = {}
    for row in rows:
        if row["contract_version"] == "legacy_v1":
            continue
        index.setdefault((str(row["parcel_id"]), str(row["sample_id"])), []).append(row["id"])
    # legacy 行没有年度，会被年度筛选排除；这里按地块单独统计未参与写回的 legacy 行数，
    # 让调用方知道「这批地块还有多少历史输入行没被覆盖」。
    result["legacy_skipped"] = int(
        db.session.execute(
            text(
                "SELECT count(*) FROM cd_flux_input_v2 "
                "WHERE contract_version='legacy_v1' AND parcel_id = ANY(:pids)"
            ),
            {"pids": sorted({key[0] for key in payload})},
        ).scalar()
        or 0
    )

    updates: list[dict[str, Any]] = []
    for key, columns in payload.items():
        hits = index.get(key) or []
        if not hits:
            result["missing"].append({"parcel_id": key[0], "sample_id": key[1]})
            continue
        if len(hits) > 1:
            # 同一地块样点在所选范围内有多条来源记录：写回会批量命中，改为拒绝并披露。
            result["ambiguous"].append({"parcel_id": key[0], "sample_id": key[1]})
            continue
        updates.append({**columns, "id": hits[0]})
        if key not in straw_keys:
            result["straw_uncovered"].append({"parcel_id": key[0], "sample_id": key[1]})

    if updates:
        full_sql = text(
            "UPDATE cd_flux_input_v2 SET grain_removal=:grain_removal, "
            "straw_removal=:straw_removal, input_revision=input_revision+1 WHERE id=:id"
        )
        grain_sql = text(
            "UPDATE cd_flux_input_v2 SET grain_removal=:grain_removal, "
            "input_revision=input_revision+1 WHERE id=:id"
        )
        try:
            for item in updates:
                db.session.execute(full_sql if "straw_removal" in item else grain_sql, item)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    result["updated"] = len(updates)
    return result


def calculate(
    *,
    f11: Any = DEFAULT_F11,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    year: Any = None,
    write_back: bool = True,
    recalculate: bool = True,
) -> dict[str, Any]:
    """计算籽粒/秸秆移除，按需写回 v2 输入表并触发 v2 重算。"""
    _require_app_context()
    f11 = _check_f11(f11)
    source, region_type, region_id, year_value, wanted = _scope(region_type, region_id, source, year)
    if write_back and year_value is None:
        raise CdRemovalError("year_required")
    computed = _compute_all(f11, source=source, wanted=wanted)

    result: dict[str, Any] = {
        "f11": f11,
        "source": source,
        "year": year_value,
        "year_note": YEAR_NOTE,
        "region": {"region_type": region_type, "region_id": region_id},
        "area_filter": "not_applied",
        "area_filter_note": "与原系统一致：移除计算按全量执行，区域参数仅记录",
        "formula_note": FORMULA_NOTE,
        "straw_coefficient_note": STRAW_COEFFICIENT_NOTE,
        "crop_rows": computed["crop_rows"],
        # rows = 籽粒与秸秆都算出的完整样点数（秸秆分母非正的样点不计入）
        "rows": len(computed["straw"]),
        "grain_rows": len(computed["grain"]),
        "straw_rows": len(computed["straw"]),
        "grain": _summary((v for _p, _s, v in computed["grain"]), FIELDS["grain"]["unit"]),
        "straw": _summary((v for _p, _s, v in computed["straw"]), FIELDS["straw"]["unit"]),
        "skipped_invalid_denominator": computed["skipped_invalid_denominator"],
        "skipped_invalid_value": computed["skipped_invalid_value"],
        "skipped_samples": computed["skipped_samples"],
        "skipped_samples_truncated": computed["skipped_samples_truncated"],
        "write_back": bool(write_back),
        "computed_at": _now_iso(),
    }

    if computed["crop_rows"] == 0:
        result.update(
            {
                "has_data": False,
                "updated_inputs": 0,
                "missing_input_rows": 0,
                "missing_input_preview": _preview([]),
                "straw_not_written": _preview([]),
                "legacy_input_skipped": 0,
                "ambiguous_input_rows": 0,
                "recalculated": None,
                "recalculate_reason": "no_data",
            }
        )
        return result

    result["has_data"] = True
    if not write_back:
        result.update(
            {
                "updated_inputs": 0,
                "missing_input_rows": 0,
                "missing_input_preview": _preview([]),
                "straw_not_written": _preview([]),
                "legacy_input_skipped": 0,
                "ambiguous_input_rows": 0,
                "recalculated": None,
                "recalculate_reason": "write_back_disabled",
            }
        )
        return result

    written = _write_back(
        computed["grain"], computed["straw"], source=source, year=year_value
    )
    result.update(
        {
            "updated_inputs": written["updated"],
            "missing_input_rows": len(written["missing"]),
            "missing_input_preview": _preview(written["missing"]),
            "straw_not_written": _preview(written["straw_uncovered"]),
            "legacy_input_skipped": written["legacy_skipped"],
            "ambiguous_input_rows": len(written["ambiguous"]),
            "ambiguous_input_preview": _preview(written["ambiguous"]),
        }
    )

    if not recalculate:
        result.update({"recalculated": None, "recalculate_reason": "disabled_by_request"})
        return result

    flux_v2 = _cd_flux_v2()
    scope: dict[str, Any] = {"source": source}
    if year_value is not None:
        scope["year"] = year_value
    try:
        recalc = flux_v2.calculate(**scope)
    except Exception as exc:  # 写回已提交，重算失败必须显式上报（spec: 不得报告整体成功）
        LOG.exception("Cd 移除项写回后重算失败")
        result.update(
            {
                "recalculated": False,
                "recalculate_reason": "failed",
                "recalculate_error": str(getattr(exc, "code", "recalculate_failed")),
                "recalculate_detail": str(exc),
            }
        )
        return result

    result.update(
        {
            "recalculated": {
                "has_data": recalc.get("has_data"),
                "calculated": recalc.get("calculated"),
                "coverage": recalc.get("coverage"),
            },
            "recalculate_reason": None,
        }
    )
    return result


# ----------------------------- 取数（四类字段） -----------------------------


def _input_series(
    field: str, *, source: str, wanted: set[str] | None, year: int | None
) -> list[tuple[str, str, float]]:
    """从 v2 输入表读地下渗漏/地表径流两列（原系统同样只读不计算）。"""
    from sqlalchemy import text

    from framework.models.user import db

    column = FIELDS[field]["column"]
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if source != "all":
        clauses.append("source = :source")
        params["source"] = source
    if year is not None:
        clauses.append("accounting_year = :year")
        params["year"] = year
    sql = f"SELECT parcel_id, sample_id, {column} FROM cd_flux_input_v2"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY parcel_id, sample_id, source, accounting_year"
    rows = db.session.execute(text(sql), params).all()
    series: list[tuple[str, str, float]] = []
    for pid, sid, value in rows:
        if wanted is not None and str(pid) not in wanted:
            continue
        if value is None:
            continue
        v = float(value)
        if math.isfinite(v):
            series.append((str(pid), str(sid), v))
    return series


def _series(
    field: str, *, f11: float, source: str, wanted: set[str] | None, year: int | None
) -> list[tuple[str, str, float]]:
    if FIELDS[field]["kind"] == "computed":
        computed = _compute_all(f11, source=source, wanted=wanted)
        return list(computed[field])
    return _input_series(field, source=source, wanted=wanted, year=year)


def _coords(parcel_ids: Sequence[str]) -> dict[str, tuple[float, float]]:
    from sqlalchemy import select

    from framework.models import ParcelInfo
    from framework.models.user import db

    coords: dict[str, tuple[float, float]] = {}
    unique = list(dict.fromkeys(parcel_ids))
    for start in range(0, len(unique), LOOKUP_CHUNK):
        chunk = unique[start : start + LOOKUP_CHUNK]
        rows = db.session.execute(
            select(ParcelInfo.parcel_id, ParcelInfo.centroid_lon, ParcelInfo.centroid_lat).where(
                ParcelInfo.parcel_id.in_(chunk)
            )
        ).all()
        for pid, lon, lat in rows:
            if lon is None or lat is None:
                continue
            coords[str(pid)] = (float(lon), float(lat))
    return coords


def statistics(
    field: str = "grain",
    *,
    f11: Any = DEFAULT_F11,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    year: Any = None,
) -> dict[str, Any]:
    """四类字段的区域统计与分布（统计口径复用阶段 2）。"""
    field = _check_field(field)
    f11 = _check_f11(f11)
    source, region_type, region_id, year_value, wanted = _scope(
        region_type, region_id, source, year, apply_region=True
    )
    series = _series(field, f11=f11, source=source, wanted=wanted, year=year_value)
    values = [value for _pid, _sid, value in series]
    statistics_mod = _statistics()
    cd_flux = _cd_flux()
    payload: dict[str, Any] = {
        "field": field,
        "title": FIELDS[field]["title"],
        "unit": FIELDS[field]["unit"],
        "calculation": FIELDS[field]["kind"],
        "source": source,
        "year": year_value,
        "region": {"region_type": region_type, "region_id": region_id},
        "has_data": bool(values),
        "count": len(values),
        "基础统计": statistics_mod.basic_statistics(values) if values else {},
        "分布统计": cd_flux._distribution(field, values) if values else {},  # noqa: SLF001
    }
    if FIELDS[field]["kind"] == "computed":
        payload["f11"] = f11
        payload["formula_note"] = FORMULA_NOTE
        payload["source_note"] = "按作物 Cd 结果实时计算（不依赖输入表已写回的值）"
    else:
        payload["input_column"] = FIELDS[field]["column"]
        payload["source_note"] = INPUT_FIELD_NOTE
    return payload


def points_geojson(
    field: str = "grain",
    *,
    f11: Any = DEFAULT_F11,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    year: Any = None,
    limit: int = DEFAULT_POINT_LIMIT,
) -> dict[str, Any]:
    """四类字段的点位 FeatureCollection（坐标取地块质心，复用阶段 3/5 形状）。"""
    field = _check_field(field)
    f11 = _check_f11(f11)
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise CdRemovalError("invalid_limit") from exc
    if limit < 1 or limit > MAX_POINT_LIMIT:
        raise CdRemovalError("invalid_limit")
    source, region_type, region_id, year_value, wanted = _scope(
        region_type, region_id, source, year, apply_region=True
    )
    series = _series(field, f11=f11, source=source, wanted=wanted, year=year_value)
    truncated = len(series) > limit
    selected = series[:limit]
    coords = _coords([pid for pid, _sid, _value in selected])
    features: list[dict[str, Any]] = []
    for pid, sid, value in selected:
        point = coords.get(pid)
        if point is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [point[0], point[1]]},
                "properties": {
                    "parcel_id": pid,
                    "sample_id": sid,
                    "value": value,
                    "field": field,
                    "unit": FIELDS[field]["unit"],
                },
            }
        )
    payload: dict[str, Any] = {
        "type": "FeatureCollection",
        "field": field,
        "unit": FIELDS[field]["unit"],
        "source": source,
        "year": year_value,
        "coordinate_source": "parcel_centroid",
        "count": len(features),
        "truncated": truncated,
        "features": features,
    }
    if FIELDS[field]["kind"] == "computed":
        payload["f11"] = f11
    return payload


def export_csv(
    field: str = "grain",
    *,
    f11: Any = DEFAULT_F11,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    year: Any = None,
    max_rows: int = MAX_EXPORT_ROWS,
) -> tuple[str, int]:
    """返回 (CSV 文本, 行数)；超过 max_rows 抛错误而不是静默截断。"""
    field = _check_field(field)
    f11 = _check_f11(f11)
    source, _region_type, _region_id, year_value, wanted = _scope(
        region_type, region_id, source, year, apply_region=True
    )
    series = _series(field, f11=f11, source=source, wanted=wanted, year=year_value)
    if len(series) > max_rows:
        raise CdRemovalError("too_many_rows")
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["parcel_id", "sample_id", field, "unit"])
    unit = FIELDS[field]["unit"]
    for pid, sid, value in series:
        writer.writerow([pid, sid, value, unit])
    return out.getvalue(), len(series)


# ----------------------------- 地图（复用阶段 4 引擎） -----------------------------


def _legend(field: str, raster) -> dict[str, Any]:
    import numpy as np

    valid = raster[~np.isnan(raster)]
    quantiles = np.nanpercentile(valid, [0, 20, 40, 60, 80, 90, 100]) if valid.size else []
    bounds = [float(v) for v in quantiles]
    labels = (
        [f"{bounds[i]:.4g} ~ {bounds[i + 1]:.4g}" for i in range(len(bounds) - 1)]
        if bounds
        else []
    )
    return {
        "mode": "quantile",
        "bounds": bounds,
        "colors": ["#15B392", "#73EC8B", "#FFEB55", "#EE66A6", "#D91656", "#640D5F"],
        "labels": labels,
        "note": f"{FIELDS[field]['title']}相对分级（按有效像元分位数），跨批次不可比",
    }


_TITLES = {
    "grain": "Cd Grain Removal",
    "straw": "Cd Straw Removal",
    "leaching": "Cd Groundwater Leaching",
    "runoff": "Cd Surface Runoff",
}


def visualize(
    field: str = "grain",
    *,
    f11: Any = DEFAULT_F11,
    region_type: str | None = None,
    region_id: str | None = None,
    source: str = "all",
    year: Any = None,
    resolution_factor: float = 4.0,
) -> dict[str, Any]:
    """生成移除项地图/直方图，复用阶段 4 的栅格化与渲染引擎。"""
    field = _check_field(field)
    f11 = _check_f11(f11)
    _check_region(region_type, region_id)
    from framework.domain.other_models import heavy_metal_cd_visualization as viz

    points_payload = points_geojson(
        field,
        f11=f11,
        region_type=region_type,
        region_id=region_id,
        source=source,
        year=year,
        limit=MAX_POINT_LIMIT,
    )
    if not points_payload["features"]:
        raise CdRemovalError("no_data")
    points = [
        (
            feature["properties"]["parcel_id"],
            feature["geometry"]["coordinates"][0],
            feature["geometry"]["coordinates"][1],
            feature["properties"]["value"],
        )
        for feature in points_payload["features"]
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
    artifact_id = uuid.uuid4().hex
    out_dir = viz.VISUALIZATION_ROOT / f"removal_{field}" / artifact_id
    out_dir.mkdir(parents=True, exist_ok=True)
    map_path = out_dir / viz.KINDS["map"]
    hist_path = out_dir / viz.KINDS["histogram"]
    title = _TITLES[field]
    viz._render_map(raster, transform, boundary, legend, title=title, out_path=map_path)  # noqa: SLF001
    viz._render_histogram(
        raster,
        title=f"{title} Frequency",
        xlabel=f"{title} ({FIELDS[field]['unit']})",
        out_path=hist_path,
    )  # noqa: SLF001
    meta = {
        "artifact_id": artifact_id,
        "field": field,
        "title": FIELDS[field]["title"],
        "unit": FIELDS[field]["unit"],
        "calculation": FIELDS[field]["kind"],
        "f11": f11 if FIELDS[field]["kind"] == "computed" else None,
        "formula_note": FORMULA_NOTE if FIELDS[field]["kind"] == "computed" else None,
        "request": {
            "region_type": region_type,
            "region_id": region_id,
            "source": source,
            "year": points_payload.get("year"),
            "resolution_factor": resolution_factor,
        },
        "legend": legend,
        "boundary_source": boundary_source,
        "points": len(points),
        "points_dropped_out_of_template": dropped,
        "files": {
            "map": f"removal_{field}/{artifact_id}/{viz.KINDS['map']}",
            "histogram": f"removal_{field}/{artifact_id}/{viz.KINDS['histogram']}",
        },
        "generated_at": _now_iso(),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def artifact_path(artifact_id: str, kind: str):
    """下载校验转交阶段 4 的实现（同一产物根目录）。"""
    from framework.domain.other_models import heavy_metal_cd_visualization as viz

    return viz.artifact_path(artifact_id, kind)
