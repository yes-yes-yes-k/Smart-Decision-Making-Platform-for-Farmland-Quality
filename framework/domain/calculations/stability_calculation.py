# framework/domain/calculations/stability_calculation.py
"""Model-1 耕地质量稳定性与退化风险评价 — 移植自 模型1_九模块总流程.py。

9 个模块:
1. 等级边界安全度 (SAFE_ABS)
2. 指标支撑均衡度 (BAL_ABS)
3. 关键指标临界度 (KEY_ABS)
4. 空间邻域一致性 (NEI_ABS) — PostGIS ST_DWithin 查询
5. 历史变化趋势 (H_ABS) — parcel_history_snapshot 3 期数据
6. 掉级风险 (DOWNGRADE_ABS)
7. 关键因子退化风险 (DEGRADE_ABS)
8. 退化空间集聚风险 (CLUSTER_ABS) — PostGIS + history
9. 持续低质风险 (PERSIST_ABS)
"""
from __future__ import annotations

import math
from typing import Dict, List

from framework.domain.calculations.coefficients import ALL_INDICATORS


def calculate_boundary_safety(zhqz: float, grade: int, qmin: float, qmax: float) -> Dict:
    """模块1: 等级边界安全度。

    SAFE_ABS = clip((ZHQZ - qmax + grade * w) / w, 0, 1)
    w = (qmax - qmin) / 10
    """
    if qmax <= qmin:
        return {"SAFE_ABS": None, "reason": "invalid_range"}
    w = (qmax - qmin) / 10
    raw = (zhqz - qmax + grade * w) / w
    safe_abs = max(0.0, min(1.0, raw))
    return {"SAFE_ABS": safe_abs}


def calculate_support_balance(memberships: List[float], weights: List[float]) -> Dict:
    """模块2: 指标支撑均衡度。

    BAL_ABS = 1 - sqrt(clip(v / d, 0, inf))
    m = 加权隶属度均值, var = 加权方差, d = m * (1 - m)
    """
    total_weight = sum(weights)
    if total_weight <= 0:
        return {"BAL_ABS": None, "reason": "zero_weights"}
    m = sum(mi * wi for mi, wi in zip(memberships, weights)) / total_weight
    var = sum(wi * (mi - m) ** 2 for mi, wi in zip(memberships, weights)) / total_weight
    d = m * (1 - m)
    if d <= 0:
        return {"BAL_ABS": 1.0 if m >= 1 else 0.0}
    ratio = var / d
    ratio = max(0.0, ratio)
    bal_abs = 1.0 - math.sqrt(ratio)
    bal_abs = max(0.0, min(1.0, bal_abs))
    return {"BAL_ABS": bal_abs, "BAL_M": m, "BAL_VAR": var}


def calculate_key_criticality(memberships: List[float], weights: List[float],
                              indicators: List[str]) -> Dict:
    """模块3: 关键指标临界度。

    KEY_FAC = 对等级边界影响最大的指标
    KEY_ABS = 1 - clip(margin / c, 0, 1)
    """
    # 关键指标: 隶属度最低的（最接近临界）
    min_idx = memberships.index(min(memberships))
    key_fac = indicators[min_idx]
    # 临界度: 1 - 隶属度
    key_abs = 1.0 - memberships[min_idx]
    key_abs = max(0.0, min(1.0, key_abs))
    return {"KEY_FAC": key_fac, "KEY_ABS": key_abs}


def calculate_neighborhood_consistency(neighbors: List[Dict], self_grade: str) -> Dict:
    """模块4: 空间邻域一致性（PostGIS ST_DWithin 查询结果）。

    邻域等级加权一致性: 邻域中等级 >= 自身等级的比例
    """
    if not neighbors:
        return {"NEI_ABS": None, "reason": "no_neighbors"}
    consistent = sum(
        1 for n in neighbors
        if _grade_value(n.get("quality_grade")) >= _grade_value(self_grade)
    )
    nei_abs = consistent / len(neighbors)
    return {"NEI_ABS": nei_abs, "neighbor_count": len(neighbors)}


def calculate_history_trend(history: List[Dict]) -> Dict:
    """模块5: 历史变化趋势。

    H_ABS = (1 - delta) / 2, delta = 标准化斜率
    """
    if len(history) < 2:
        return {"H_ABS": None, "reason": "insufficient_history"}
    # 按年份排序
    sorted_hist = sorted(history, key=lambda x: x.get("survey_year", 0))
    indices = [h.get("composite_index", 0) for h in sorted_hist]
    years = [h.get("survey_year", 0) for h in sorted_hist]
    # 简单线性回归斜率
    n = len(indices)
    mean_x = sum(years) / n
    mean_y = sum(indices) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(years, indices))
    denominator = sum((x - mean_x) ** 2 for x in years)
    if denominator == 0:
        return {"H_ABS": None, "reason": "zero_variance"}
    slope = numerator / denominator
    # 标准化 delta
    delta = max(-1.0, min(1.0, slope * 10))  # 缩放
    h_abs = (1 - delta) / 2
    return {"H_ABS": max(0.0, min(1.0, h_abs))}


def calculate_downgrade_risk(history: List[Dict]) -> Dict:
    """模块6: 掉级风险（等级下降幅度概率）。"""
    if len(history) < 2:
        return {"DOWNGRADE_ABS": None, "reason": "insufficient_history"}
    sorted_hist = sorted(history, key=lambda x: x.get("survey_year", 0))
    grades = [_grade_value(h.get("quality_grade")) for h in sorted_hist]
    # 等级下降（数字增大表示等级降低）
    downgrades = sum(
        1 for i in range(1, len(grades)) if grades[i] > grades[i - 1]
    )
    risk = downgrades / (len(grades) - 1)
    return {"DOWNGRADE_ABS": risk}


def calculate_factor_degradation(history: List[Dict]) -> Dict:
    """模块7: 关键因子退化风险。"""
    if len(history) < 2:
        return {"DEGRADE_ABS": None, "reason": "insufficient_history"}
    sorted_hist = sorted(history, key=lambda x: x.get("survey_year", 0))
    indices = [h.get("composite_index", 0) for h in sorted_hist]
    # 退化率: 指数下降幅度
    if indices[0] <= 0:
        return {"DEGRADE_ABS": 0.0}
    degradation = (indices[0] - indices[-1]) / indices[0]
    return {"DEGRADE_ABS": max(0.0, min(1.0, degradation))}


def calculate_degradation_clustering(neighbors: List[Dict]) -> Dict:
    """模块8: 退化空间集聚风险（邻域退化密度）。"""
    if not neighbors:
        return {"CLUSTER_ABS": None, "reason": "no_neighbors"}
    degraded = sum(
        1 for n in neighbors if _grade_value(n.get("quality_grade")) >= 7
    )
    return {"CLUSTER_ABS": degraded / len(neighbors)}


def calculate_persistent_low_quality(history: List[Dict]) -> Dict:
    """模块9: 持续低质风险（连续低等级期数）。"""
    if not history:
        return {"PERSIST_ABS": None, "reason": "insufficient_history"}
    sorted_hist = sorted(history, key=lambda x: x.get("survey_year", 0))
    low_count = sum(
        1 for h in sorted_hist if _grade_value(h.get("quality_grade")) >= 7
    )
    persist = low_count / len(sorted_hist)
    return {"PERSIST_ABS": persist}


def calculate_stability(parcel_info: Dict, history: List[Dict],
                       neighbors: List[Dict]) -> Dict:
    """完整 9 模块稳定性计算。

    Args:
        parcel_info: 地块信息（含 indicators, quality_index, quality_grade）。
        history: 历史快照列表（parcel_history_snapshot 记录）。
        neighbors: 邻域地块列表（PostGIS ST_DWithin 查询结果）。

    Returns:
        dict: module_1 ~ module_9 各模块结果。
    """
    indicators = parcel_info.get("indicators", {})
    quality_index = parcel_info.get("quality_index", 0.5)
    quality_grade = parcel_info.get("quality_grade", "5")

    # 派生隶属度和权重（调用 Model-2 计算）
    mapped = indicators  # 假设已映射
    try:
        from framework.domain.calculations.grade_calculation import evaluate_land_quality
        area_code = parcel_info.get("area_code", "440281")
        _, _, memberships = evaluate_land_quality(mapped, area_code)
        from framework.domain.calculations.coefficients import (
            AREA_TO_REGION, MODEL2_COEFFICIENTS,
        )
        ejnyq_idx = AREA_TO_REGION.get(area_code, {}).get("ejnyq_idx", 0)
        weights = MODEL2_COEFFICIENTS[ejnyq_idx]["weights"]
    except Exception:
        memberships = [0.5] * 12
        weights = [1 / 12] * 12

    # 模块 1-3
    m1 = calculate_boundary_safety(quality_index, _grade_value(quality_grade), 0.0, 1.0)
    m2 = calculate_support_balance(memberships, weights)
    m3 = calculate_key_criticality(memberships, weights, ALL_INDICATORS)

    # 模块 4: 空间邻域
    m4 = calculate_neighborhood_consistency(neighbors, quality_grade)

    # 模块 5-9: 历史数据
    m5 = calculate_history_trend(history)
    m6 = calculate_downgrade_risk(history)
    m7 = calculate_factor_degradation(history)
    m8 = calculate_degradation_clustering(neighbors)
    m9 = calculate_persistent_low_quality(history)

    return {
        "module_1": m1, "module_2": m2, "module_3": m3,
        "module_4": m4, "module_5": m5, "module_6": m6,
        "module_7": m7, "module_8": m8, "module_9": m9,
    }


def _grade_value(grade) -> int:
    """等级字符串 → 数值（"1"=最好 → 10=最差）。"""
    if grade is None:
        return 10
    try:
        return int(str(grade).strip())
    except (ValueError, TypeError):
        return 10
