"""Cd 结果统计、明细查询与 CSV 导出（阶段 2）。

口径来源：AcidMap ``app/services/cd_prediction_statistics_service.py``（逐行复核）。

- 8 项基础统计：总体标准差（除以 n）、分位数按下标直取 ``sorted[int(count*q)]``、全部 ``round(..., 6)``
- 作物 Cd 三档分布：``0.0~0.2`` 安全 / ``0.2~0.3`` 预警 / ``≥0.3`` 超标，负值计入超标并单独计数
- 有效态 Cd **没有**分箱，只有 8 项基础统计
- 区域过滤按 ``parcel_info.area_code`` JOIN 实现（原系统的 ``area`` 参数实际未参与查询）

设计取舍见 openspec change ``add-heavy-metal-cd-statistics-api``：
决策 1（照抄非标准分位数）、决策 4（空数据 200 + has_data=false）、决策 5（不伪造数据更新时间）。
"""
from __future__ import annotations

import csv
import io
import math
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

MODEL_IDS: tuple[str, ...] = ("crop_cd", "effective_cd")

UNIT = "mg/kg"
UNIT_STATUS = "unverified"
UNIT_NOTE = "单位标注依据原系统模型注释；exp(LnEffCd) 实测量级待核，unit_status 保持 unverified"

#: 8 项基础统计的固定键顺序（与原系统一致）。
BASIC_STAT_KEYS: tuple[str, ...] = (
    "数据点总数", "均值", "中位数", "标准差", "最小值", "最大值", "25%分位数", "75%分位数",
)

#: 作物 Cd 分布三档（仅作物 Cd 使用）。
DISTRIBUTION_BANDS: tuple[dict[str, Any], ...] = (
    {"序号": 1, "分布区间": "0.0 ~ 0.2", "区间说明": "安全区间"},
    {"序号": 2, "分布区间": "0.2 ~ 0.3", "区间说明": "预警区间"},
    {"序号": 3, "分布区间": "≥ 0.3", "区间说明": "超标区间"},
)

THRESHOLD_NOTE = "分布区间仅用于描述预测值分布，不构成安全或超标判定"
DEFAULT_CSV_MAX_ROWS = 100000

_COLUMNS: dict[str, str] = {"crop_cd": "ln_crop_cd", "effective_cd": "ln_eff_cd"}
_SOURCE_TABLES: dict[str, str] = {
    "crop_cd": "cd_crop_prediction_result表",
    "effective_cd": "cd_effective_prediction_result表",
}


class CdStatisticsError(ValueError):
    """统计/查询参数或数据访问错误。"""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _result_table(model_id: str):
    from framework.models.cd_prediction import (  # noqa: WPS433
        CdCropPredictionResult,
        CdEffectivePredictionResult,
    )

    if model_id not in _COLUMNS:
        raise CdStatisticsError("unknown_model")
    return CdCropPredictionResult if model_id == "crop_cd" else CdEffectivePredictionResult


def _require_app_context() -> None:
    from flask import has_app_context

    if not has_app_context():
        raise CdStatisticsError("no_app_context")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ----------------------------- 基础统计 -----------------------------


def basic_statistics(values: Sequence[float]) -> dict[str, Any]:
    """8 项基础统计，算法与原系统逐项对齐。

    - 标准差是**总体标准差**（除以 n），不是样本标准差
    - 25%/75% 分位数是**按下标直取** ``sorted[int(count*q)]``，不是线性插值
    """
    count = len(values)
    if count == 0:
        payload: dict[str, Any] = {key: None for key in BASIC_STAT_KEYS}
        payload["数据点总数"] = 0
        return payload

    mean_value = sum(values) / count
    ordered = sorted(values)
    if count % 2 == 0:
        median_value = (ordered[count // 2 - 1] + ordered[count // 2]) / 2
    else:
        median_value = ordered[count // 2]

    variance = sum((value - mean_value) ** 2 for value in values) / count
    std_value = math.sqrt(variance)

    q25_index = int(count * 0.25)
    q75_index = int(count * 0.75)
    q25 = ordered[q25_index] if q25_index < count else ordered[-1]
    q75 = ordered[q75_index] if q75_index < count else ordered[-1]

    return {
        "数据点总数": count,
        "均值": round(mean_value, 6),
        "中位数": round(median_value, 6),
        "标准差": round(std_value, 6),
        "最小值": round(min(values), 6),
        "最大值": round(max(values), 6),
        "25%分位数": round(q25, 6),
        "75%分位数": round(q75, 6),
    }


def crop_cd_distribution(values: Sequence[float]) -> dict[str, Any]:
    """作物 Cd 三档分布。负值计入超标区间，并单独记入 ``invalid_count``。"""
    total = len(values)
    safe_count = warning_count = exceed_count = invalid_count = 0
    for value in values:
        if value < 0:
            exceed_count += 1
            invalid_count += 1
        elif value < 0.2:
            safe_count += 1
        elif value < 0.3:
            warning_count += 1
        else:
            exceed_count += 1

    def _pct(part: int) -> float:
        return round(part / total * 100, 2) if total else 0.0

    counts = (safe_count, warning_count, exceed_count)
    rows = [
        {**band, "数据点数量": counts[index], "占比": _pct(counts[index])}
        for index, band in enumerate(DISTRIBUTION_BANDS)
    ]
    return {
        "标题": "水稻镉含量预测统计",
        "总数据点数": total,
        "表格数据": rows,
        "汇总": {
            "安全区间占比": f"{_pct(safe_count)}%",
            "预警区间占比": f"{_pct(warning_count)}%",
            "超标区间占比": f"{_pct(exceed_count)}%",
        },
        "invalid_count": invalid_count,
        "threshold_note": THRESHOLD_NOTE,
    }


# ----------------------------- 取数 -----------------------------


def _area_filtered_query(query, model_id: str, area_code: str | None):
    from framework.models import ParcelInfo  # noqa: WPS433

    table = _result_table(model_id)
    if area_code is None:
        return query
    return query.join(ParcelInfo, ParcelInfo.parcel_id == table.parcel_id).filter(
        ParcelInfo.area_code == str(area_code)
    )


def collect_values(model_id: str, area_code: str | None = None) -> list[float]:
    """取指定模型（可选区域）的全部预测值，``exp(ln)`` 还原为 mg/kg。"""
    _require_app_context()
    from framework.models.user import db  # noqa: WPS433

    table = _result_table(model_id)
    column = getattr(table, _COLUMNS[model_id])
    query = _area_filtered_query(db.session.query(column), model_id, area_code)
    values: list[float] = []
    for (log_value,) in query.all():
        if log_value is None:
            continue
        try:
            value = math.exp(float(log_value))
        except (OverflowError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def crop_cd_statistics(area_code: str | None = None) -> dict[str, Any]:
    """作物 Cd 统计：8 项基础统计 + 三档分布。"""
    values = collect_values("crop_cd", area_code)
    return {
        "模型类型": "作物Cd预测模型",
        "数据单位": UNIT,
        "unit_status": UNIT_STATUS,
        "unit_note": UNIT_NOTE,
        "has_data": bool(values),
        "statistics_scope": "crop_cd_distribution",
        "queried_at": _now_iso(),
        "queried_at_is": "query_time",
        "area_code": area_code,
        "基础统计": basic_statistics(values),
        "数据来源": _SOURCE_TABLES["crop_cd"],
        "分布统计表格": crop_cd_distribution(values),
    }


def effective_cd_statistics(area_code: str | None = None) -> dict[str, Any]:
    """有效态 Cd 统计：只有 8 项基础统计，**不含任何分箱**。"""
    values = collect_values("effective_cd", area_code)
    return {
        "模型类型": "有效态Cd预测模型",
        "数据单位": UNIT,
        "unit_status": UNIT_STATUS,
        "unit_note": UNIT_NOTE,
        "has_data": bool(values),
        "statistics_scope": "effective_cd_basic",
        "queried_at": _now_iso(),
        "queried_at_is": "query_time",
        "area_code": area_code,
        "基础统计": basic_statistics(values),
        "数据来源": _SOURCE_TABLES["effective_cd"],
    }


def combined_statistics(area_code: str | None = None) -> dict[str, Any]:
    """双模型综合统计：两侧各自统计 + 完整性标记 + 对比项。"""
    crop = crop_cd_statistics(area_code)
    effective = effective_cd_statistics(area_code)
    payload: dict[str, Any] = {
        "生成时间": _now_iso(),
        "queried_at_is": "query_time",
        "area_code": area_code,
        "has_data": crop["has_data"] or effective["has_data"],
        "数据完整性": {
            "有作物Cd数据": crop["has_data"],
            "有有效态Cd数据": effective["has_data"],
            "数据完整": crop["has_data"] and effective["has_data"],
        },
        "作物Cd统计": crop,
        "有效态Cd统计": effective,
    }
    if crop["has_data"] and effective["has_data"]:
        payload["对比分析"] = {
            "数据点数量对比": {
                "作物Cd": crop["基础统计"]["数据点总数"],
                "有效态Cd": effective["基础统计"]["数据点总数"],
            },
            "平均浓度对比": {
                "作物Cd均值": crop["基础统计"]["均值"],
                "有效态Cd均值": effective["基础统计"]["均值"],
            },
        }
    return payload


# ----------------------------- 明细与导出 -----------------------------


def list_results(
    model_id: str,
    area_code: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """分页明细：按地块与样点排序，返回 ln 值与还原值。"""
    if model_id not in _COLUMNS:
        raise CdStatisticsError("unknown_model")
    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        raise CdStatisticsError("invalid_limit")
    if not isinstance(offset, int) or offset < 0:
        raise CdStatisticsError("invalid_offset")
    _require_app_context()
    from framework.models.user import db  # noqa: WPS433

    table = _result_table(model_id)
    column = getattr(table, _COLUMNS[model_id])
    base = db.session.query(table.parcel_id, table.sample_id, column)
    query = _area_filtered_query(base, model_id, area_code).order_by(
        table.parcel_id, table.sample_id
    )
    rows = query.offset(offset).limit(limit).all()
    items = [
        {
            "parcel_id": parcel_id,
            "sample_id": sample_id,
            "ln_value": float(log_value),
            "value": math.exp(float(log_value)),
            "unit": UNIT,
            "unit_status": UNIT_STATUS,
        }
        for parcel_id, sample_id, log_value in rows
    ]
    return {
        "model_id": model_id,
        "area_code": area_code,
        "limit": limit,
        "offset": offset,
        "count": len(items),
        "items": items,
    }


def export_csv(
    model_id: str,
    area_code: str | None = None,
    max_rows: int = DEFAULT_CSV_MAX_ROWS,
) -> tuple[bytes, int]:
    """导出 CSV（UTF-8 BOM）。超过 ``max_rows`` 抛 ``export_exceeds_limit``。"""
    if model_id not in _COLUMNS:
        raise CdStatisticsError("unknown_model")
    _require_app_context()
    from framework.models.user import db  # noqa: WPS433
    from sqlalchemy import func

    table = _result_table(model_id)
    column = getattr(table, _COLUMNS[model_id])
    # 必须显式指定列：func.count() 无参数时不会带 FROM 子句，result=1 是假值
    count_query = _area_filtered_query(
        db.session.query(func.count(table.id)), model_id, area_code
    )
    total = int(count_query.scalar() or 0)
    if total > max_rows:
        raise CdStatisticsError(f"export_exceeds_limit:{total}>{max_rows}")

    base = db.session.query(table.parcel_id, table.sample_id, column)
    rows = _area_filtered_query(base, model_id, area_code).order_by(
        table.parcel_id, table.sample_id
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["parcel_id", "sample_id", "ln_value", "value", "unit", "unit_status"])
    for parcel_id, sample_id, log_value in rows:
        value = float(log_value)
        writer.writerow([parcel_id, sample_id, value, math.exp(value), UNIT, UNIT_STATUS])
    return buffer.getvalue().encode("utf-8-sig"), total


def csv_filename(model_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{model_id}_cd_results_{stamp}.csv"
