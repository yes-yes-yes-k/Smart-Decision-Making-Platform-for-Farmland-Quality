"""Model-3 耕地障碍诊断 — 移植自 模型3/evaluation.py + config.py。

包含:
- 连续/离散指标隶属度 (calc_continuous / calc_discrete)
- 障碍等级判定 (calc_obstacle_level, GCZD/DXBW 按 by_membership 隶属度判定)
- 障碍度计算 ((1-membership)*weight/sum)
- 障碍诊断 (diagnosis_row: 主要/次要因子识别)
"""
from __future__ import annotations
from typing import Dict, List, Any

from framework.domain.calculations.coefficients import (
    MODEL3_COEFFICIENTS, MODEL3_WEIGHTS,
    OBSTACLE_THRESHOLDS, ALL_INDICATORS, NUMERIC_INDICATORS,
    CONCEPT_INDICATORS,
)
from framework.domain.calculations.region_mapping_service import get_region_mapping

_LEVEL_LABELS = {"heavy": "重度障碍", "moderate": "中度障碍",
                 "light": "轻度障碍", "none": "无障碍"}
_LEVEL_ORDER = ["heavy", "moderate", "light", "none"]


def calc_continuous(u, coef: Dict[str, Any]) -> float:
    """连续指标隶属度（移植自 evaluation.py calc_continuous）。

    在 [L, U] 内使用峰型公式 1/(1+a*(u-c)^2)；超出范围返回 0.0。

    Args:
        u: 指标原始值。
        coef: {"a", "c", "L", "U"} 隶属度参数（按一级农业区配置）。

    Returns:
        隶属度 ∈ [0, 1]；u 为 None 或非数值时返回 0.0。
    """
    if u is None:
        return 0.0
    try:
        u = float(u)
    except (TypeError, ValueError):
        return 0.0
    a = coef["a"]
    c = coef["c"]
    L = coef.get("L")
    U = coef.get("U")
    if L is not None and u < L:
        return 0.0
    if U is not None and u > U:
        return 0.0
    return 1.0 / (1.0 + a * (u - c) ** 2)


def calc_discrete(code, coef: Dict) -> float:
    """离散指标隶属度（查找表映射，移植自 evaluation.py calc_discrete）。

    Args:
        code: 离散指标代码（如 RT/FS/CM）。
        coef: {code: membership} 查找表。

    Returns:
        隶属度 ∈ [0, 1]；未知代码或 None 返回 0.0。
    """
    if code is None:
        return 0.0
    return coef.get(code, 0.0)


def calc_obstacle_level(indicator: str, value, membership=None):
    """按阈值判定障碍等级（移植自 config.py calc_obstacle_level）。

    GCZD/DXBW 在 OBSTACLE_THRESHOLDS 中标记为 "by_membership"，
    按 membership 隶属度值判定（需传入该指标的隶属度）。
    其余数值指标按区间判定，概念指标按代码列表判定。

    Args:
        indicator: 指标缩写（SJD/YJZ/.../ZDGX）。
        value: 指标原始值（数值或代码字符串）。
        membership: 该指标的隶属度（仅 GCZD/DXBW 使用）。

    Returns:
        "重度障碍" / "中度障碍" / "轻度障碍" / "无障碍"；无法判定时返回 None。
    """
    thresholds = OBSTACLE_THRESHOLDS.get(indicator)
    if thresholds is None:
        return None

    # by_membership 特殊处理（GCZD/DXBW 按隶属度判定）
    if thresholds == "by_membership":
        if membership is None:
            return None
        try:
            membership = float(membership)
        except (TypeError, ValueError):
            return None
        # 严格复制原模型的开闭区间，避免 0.5/0.6 等边界同时
        # 命中两个等级后被错分到更重的等级。
        if indicator == "GCZD":
            if 0.4 <= membership < 0.6:
                return _LEVEL_LABELS["heavy"]
            if 0.6 <= membership <= 0.7:
                return _LEVEL_LABELS["moderate"]
            if 0.75 <= membership <= 0.85:
                return _LEVEL_LABELS["light"]
            if 0.9 <= membership <= 1.0:
                return _LEVEL_LABELS["none"]
        elif indicator == "DXBW":
            if 0.2 <= membership < 0.5:
                return _LEVEL_LABELS["heavy"]
            if 0.5 <= membership <= 0.68:
                return _LEVEL_LABELS["moderate"]
            if 0.7 <= membership <= 0.8:
                return _LEVEL_LABELS["light"]
            if 0.9 <= membership <= 1.0:
                return _LEVEL_LABELS["none"]
        return None

    # 概念指标按代码列表判定
    if indicator in CONCEPT_INDICATORS:
        for level in _LEVEL_ORDER:
            if value in thresholds.get(level, []):
                return _LEVEL_LABELS[level]
        return None

    # 数值指标按原模型的精确开闭区间判定。
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if indicator == "SJD":
        if v <= 4.5 or v > 9.5:
            return _LEVEL_LABELS["heavy"]
        if v <= 5.5 or v > 8.5:
            return _LEVEL_LABELS["moderate"]
        if v < 6.5 or v > 7.5:
            return _LEVEL_LABELS["light"]
        return _LEVEL_LABELS["none"]
    if indicator in {"YJZ", "YXL", "SXJ"}:
        cutoffs = {
            "YJZ": (10.0, 20.0, 25.0),
            "YXL": (10.0, 20.0, 35.0),
            "SXJ": (50.0, 100.0, 150.0),
        }[indicator]
        if v <= cutoffs[0]:
            return _LEVEL_LABELS["heavy"]
        if v <= cutoffs[1]:
            return _LEVEL_LABELS["moderate"]
        if v <= cutoffs[2]:
            return _LEVEL_LABELS["light"]
        return _LEVEL_LABELS["none"]
    if indicator == "TRRZ":
        if v <= 0.9 or v > 1.4:
            return _LEVEL_LABELS["heavy"]
        if v < 0.95 or v > 1.3:
            return _LEVEL_LABELS["moderate"]
        if v < 1.0 or v > 1.2:
            return _LEVEL_LABELS["light"]
        return _LEVEL_LABELS["none"]
    if indicator == "GCHD":
        if v <= 10:
            return _LEVEL_LABELS["heavy"]
        if v <= 15:
            return _LEVEL_LABELS["moderate"]
        if v < 20:
            return _LEVEL_LABELS["light"]
        return _LEVEL_LABELS["none"]
    if indicator == "YXTCHD":
        if v < 60:
            return _LEVEL_LABELS["heavy"]
        if v < 80:
            return _LEVEL_LABELS["moderate"]
        if v < 100:
            return _LEVEL_LABELS["light"]
        return _LEVEL_LABELS["none"]
    return None


def calc_obstacle_degree(memberships: List[float], weights: List[float]) -> List[float]:
    """计算障碍度（移植自 calculatorall.py / evaluation.py）。

    obstacle_degree[i] = (1-membership[i])*weight[i] / sum((1-m)*w)

    Args:
        memberships: 隶属度列表。
        weights: 权重列表（与 memberships 等长）。

    Returns:
        障碍度列表，和为 1.0（sum > 0 时）；sum <= 0 时全为 0.0。
    """
    zads = [(1.0 - m) * w for m, w in zip(memberships, weights)]
    total = sum(zads)
    if total <= 0:
        return [0.0] * len(zads)
    return [z / total for z in zads]


def diagnosis_row(indicators: Dict[str, Any], area_code: str) -> Dict:
    """完整障碍诊断评价（主要/次要因子识别）。

    流程: 区域定位 → 12 指标隶属度 → 障碍度 → 主要/次要因子识别。

    主要因子: 障碍度 >= 0.20；次要因子: 0.10 <= 障碍度 < 0.20。
    障碍类型: 无主要因子→"无明显障碍"；单一主要且无次要→"单一障碍"；否则→"多障碍"。

    Args:
        indicators: 映射后的指标 dict（键为 SJD/YJZ/.../ZDGX 缩写）。
        area_code: 行政区码（如 "440281" 乐昌）。

    Returns:
        dict: obstacle_type, primary_factors, secondary_factors,
              obstacle_levels, obstacle_degrees, memberships。
    """
    region = get_region_mapping(area_code)
    primary = region["primary"]
    secondary = region["secondary"]
    coef = MODEL3_COEFFICIENTS[primary]
    weights_dict = MODEL3_WEIGHTS[secondary]

    # 12 指标隶属度（7 数值 + 5 概念）
    memberships: Dict[str, float] = {}
    for abbr in NUMERIC_INDICATORS:
        memberships[abbr] = calc_continuous(indicators.get(abbr), coef[abbr])
    for abbr in CONCEPT_INDICATORS:
        memberships[abbr] = calc_discrete(indicators.get(abbr), coef[abbr])

    # 权重与隶属度按 ALL_INDICATORS 顺序对齐
    weights = [weights_dict[ind] for ind in ALL_INDICATORS]
    mem_list = [memberships[ind] for ind in ALL_INDICATORS]
    degrees = calc_obstacle_degree(mem_list, weights)
    degree_map = dict(zip(ALL_INDICATORS, degrees))

    # 障碍等级（GCZD/DXBW 依赖隶属度）
    levels: Dict[str, Any] = {}
    for abbr in ALL_INDICATORS:
        levels[abbr] = calc_obstacle_level(abbr, indicators.get(abbr), memberships[abbr])

    # 主要/次要因子识别（按障碍度降序）
    pairs = sorted(zip(ALL_INDICATORS, degrees), key=lambda x: x[1], reverse=True)
    primary_factors = [ind for ind, deg in pairs if deg >= 0.20]
    secondary_factors = [ind for ind, deg in pairs if 0.10 <= deg < 0.20]

    if not primary_factors:
        obstacle_type = "无明显障碍"
    elif len(primary_factors) == 1 and not secondary_factors:
        obstacle_type = "单一障碍"
    else:
        obstacle_type = "多障碍"

    return {
        "obstacle_type": obstacle_type,
        "primary_factors": primary_factors,
        "secondary_factors": secondary_factors,
        "obstacle_levels": levels,
        "obstacle_degrees": degree_map,
        "memberships": memberships,
    }
