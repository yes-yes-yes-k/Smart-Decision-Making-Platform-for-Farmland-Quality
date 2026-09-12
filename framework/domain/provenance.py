"""地块指标来源标注与回填识别。

`parcel_info.soil_indicators` 是 JSON 快照，历史上由两类脚本写入：

1. 地块级映射（``scripts/import_real_parcels.py``）：来自地块 shp 的指标；
2. 区域平均回填（``scripts/link_soil_indicators.py``）：把三普采样表的平均值
   批量写入所有地块，用于补齐 Model-4/5 需要的字段。

第 2 类字段“有值”但并非地块实测值，模型侧无法据此判断输入是否可信。本模块
把来源标记固定为机器可读事实：

- ``measured``：由地块级来源数据映射得到；
- ``region_mean_backfill``：由区域/全局平均值批量回填；
- ``default``：代码默认值或模板值。

未出现在来源标记中的字段视为**来源未知**，不得当作实测值使用。
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping, Optional, Sequence

PROVENANCE_KEY = "provenance"

SOURCE_MEASURED = "measured"
SOURCE_REGION_MEAN_BACKFILL = "region_mean_backfill"
SOURCE_DEFAULT = "default"

SOURCES = (SOURCE_MEASURED, SOURCE_REGION_MEAN_BACKFILL, SOURCE_DEFAULT)
IMPUTED_SOURCES = frozenset({SOURCE_REGION_MEAN_BACKFILL, SOURCE_DEFAULT})

#: 统一问题码：模型输入中包含回填或默认取值。
IMPUTED_INPUT = "IMPUTED_INPUT"

#: Model-5 必填特征 -> soil_indicators 字段
MODEL5_FEATURE_SOURCES: dict[str, str] = {
    "pH": "soil_ph",
    "SOMbe": "organic_matter",
    "AK": "available_potassium",
    "AP": "available_phosphorus",
    "TN": "total_n",
}

#: Model-4 过程模型输入 -> soil_indicators 字段
MODEL4_INPUT_SOURCES: dict[str, str] = {
    "SJD": "soil_ph",
    "Hex": "exchangeable_hydrogen",
    "Alex": "exchangeable_aluminum",
}

#: Model-4 的上下文参数（不是 soil_indicators 字段，缺失即按默认值处理）
MODEL4_CONTEXT_INPUTS = ("target_ph", "fertilizer_type")

#: 结构性枚举字段：取值天然离散，不参与“跨地块常量”判定。
STRUCTURAL_FIELDS = frozenset({
    "soil_texture",
    "irrigation_condition",
    "drainage_capacity",
    "terrain_position",
    "soil_structure",
    "land_type",
    "obstacle_factors",
    "quality_grade",
})

#: 已知由导入/兼容代码写入固定默认值的字段。
DEFAULT_FIELDS = frozenset({"target_ph", "fertilizer_type"})


def source_for_field(field: str) -> str:
    """回填字段的默认来源类型：已知默认值字段标记为 ``default``。"""
    return SOURCE_DEFAULT if field in DEFAULT_FIELDS else SOURCE_REGION_MEAN_BACKFILL


def provenance_map(indicators: Optional[Mapping[str, Any]]) -> dict[str, str]:
    """读取指标快照中的来源标记；缺失或格式异常时返回空字典。"""
    if not isinstance(indicators, Mapping):
        return {}
    raw = indicators.get(PROVENANCE_KEY)
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def source_of(indicators: Optional[Mapping[str, Any]], field: str) -> Optional[str]:
    """返回字段的来源标记，未标注时返回 ``None``（来源未知）。"""
    return provenance_map(indicators).get(field)


def is_imputed(indicators: Optional[Mapping[str, Any]], field: str) -> bool:
    """字段是否来自回填或默认值。来源未知按“未知”处理，不作为回填判定。"""
    return source_of(indicators, field) in IMPUTED_SOURCES


def imputed_fields(
    indicators: Optional[Mapping[str, Any]],
    fields: Optional[Iterable[str]] = None,
) -> list[str]:
    """列出被回填或被默认的字段，保持传入顺序。"""
    candidates = list(fields) if fields is not None else sorted(provenance_map(indicators))
    return [field for field in candidates if is_imputed(indicators, field)]


def imputed_feature_names(
    indicators: Optional[Mapping[str, Any]],
    feature_sources: Mapping[str, str],
) -> list[str]:
    """把“被回填的字段”映射为模型特征名，例如 ``total_n`` -> ``TN``。"""
    return [
        feature
        for feature, source_field in feature_sources.items()
        if is_imputed(indicators, source_field)
    ]


def empty_provenance(indicators: Optional[Mapping[str, Any]], fields: Sequence[str]) -> dict[str, str]:
    """为尚未标注的字段生成来源标记草案（默认 ``region_mean_backfill``）。"""
    existing = provenance_map(indicators)
    return {
        field: SOURCE_REGION_MEAN_BACKFILL
        for field in fields
        if field not in existing and field != PROVENANCE_KEY
    }


def detect_constant_fields(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    min_share: float = 0.95,
    max_others: int = 10,
    excluded_fields: Iterable[str] = STRUCTURAL_FIELDS,
) -> list[dict[str, Any]]:
    """识别“跨地块常量”字段。

    判定条件：字段的最高频取值占比不低于 ``min_share``，且不属于该取值的**离群地块数**
    不超过 ``max_others``（用于容忍少量验证地块等特例）。结构性枚举字段与已标注字段
    会被跳过。

    返回按最高频占比降序排列的判定结果，供标注脚本输出与写入使用。
    """
    excluded = set(excluded_fields)
    counters: dict[str, Counter] = {}
    total = len(snapshots)

    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping):
            continue
        marked = provenance_map(snapshot)
        for field, value in snapshot.items():
            key = str(field)
            if key == PROVENANCE_KEY or key in excluded or key in marked:
                continue
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            counters.setdefault(key, Counter())[str(value)] += 1

    results: list[dict[str, Any]] = []
    for field, counter in counters.items():
        non_null = sum(counter.values())
        if non_null == 0:
            continue
        top_value, top_count = counter.most_common(1)[0]
        share = top_count / non_null
        if share >= min_share and (non_null - top_count) <= max_others:
            results.append({
                "field": field,
                "distinct": len(counter),
                "top_value": top_value,
                "top_share": round(share, 6),
                "non_null": non_null,
                "outliers": non_null - top_count,
                "total": total,
            })
    results.sort(key=lambda item: (-item["top_share"], item["field"]))
    return results
