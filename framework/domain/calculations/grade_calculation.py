"""Model-2 耕地质量等级评价 — 移植自 模型2/evaluation.py + config.py。

隶属度函数:
- 峰型 (SJD, TRRZ): 1/(1+a*(u-c)^2), 超出 [ut1,ut2] 为 0
- 戒上型 (其余5个数值): <=ut1 为 0, [ut1,c) 用公式, >=c 为 1.0
- 概念型 (5个): 查找表映射
"""
from __future__ import annotations
from typing import List, Tuple
from framework.domain.calculations.coefficients import (
    MODEL2_COEFFICIENTS, MODEL2_GRADE_LIMITS,
    NUMERIC_INDICATORS, PEAK_TYPE_INDICES,
)
from framework.domain.calculations.region_mapping_service import get_region_mapping


def membership_numeric(u: float, a: float, c: float, ut1: float, ut2: float, idx: int) -> float:
    """数值指标隶属度（移植自 evaluation.py membership_numeric）。

    Args:
        u: 指标值。
        a, c, ut1, ut2: 隶属度参数（按二级农业区配置）。
        idx: 0-based 指标索引（0-6 对应 SJD/YJZ/YXL/SXJ/TRRZ/YXTCHD/GCHD）。

    Returns:
        隶属度 ∈ [0, 1]。
    """
    if u is None:
        return 0.0
    if idx in PEAK_TYPE_INDICES:  # 峰型（SJD pH, TRRZ 容重）
        if u <= ut1 or u >= ut2:
            return 0.0
        return 1.0 / (1.0 + a * (u - c) ** 2)
    else:  # 戒上型
        if u <= ut1:
            return 0.0
        if u < c:
            return 1.0 / (1.0 + a * (u - c) ** 2)
        return 1.0


def membership_concept(code: str, lookup_table: dict) -> float:
    """概念指标隶属度（查找表映射）。

    Args:
        code: 离散指标代码（如 RT/FS/CM）。
        lookup_table: {code: membership} 字典。

    Returns:
        隶属度 ∈ [0, 1]，未知代码返回 0.0。
    """
    if code is None:
        return 0.0
    return lookup_table.get(code, 0.0)


def determine_grade(quality_index: float, bounds: list, labels: list) -> str:
    """按等级阈值判定耕地质量等级（移植自 evaluation.py 等级判定）。

    Args:
        quality_index: 综合指数。
        bounds: 等级边界列表（升序）。
        labels: 等级标签列表（对应 bounds）。

    Returns:
        等级字符串（"1"-"10"）。
    """
    grade = labels[-1]  # 默认最低等级
    for i in range(len(bounds) - 1):
        if quality_index >= bounds[i + 1]:
            continue
        grade = labels[i]
        break
    return grade


def determine_model2_grade(quality_index: float, limits: list[float]) -> str:
    """按 Model-2 原始降序分界判定 1–10 等。

    ``limits[0]`` 是 1 等下限，``limits[8]`` 是 9 等下限；
    低于所有分界时为 10 等。
    """
    for grade, lower_bound in enumerate(limits, start=1):
        if quality_index >= lower_bound:
            return str(grade)
    return "10"


def grade_boundary_note(quality_index: float, area_code: str) -> str:
    """返回“距离更好等级仅差不到 0.01”的临界提示；非临界返回空字符串。

    等级阈值按二级农业区不同，因此提示必须基于当前区域的分界值。
    """
    region = get_region_mapping(area_code)
    limits = MODEL2_GRADE_LIMITS[region["ejnyq_idx"]]
    grade = int(determine_model2_grade(quality_index, limits))
    if grade <= 1:
        return "已处于最高等级（1 等）。"
    gap = limits[grade - 2] - quality_index
    if gap <= 0.005:
        return f"距 {grade - 1} 等仅差不到 0.01，处于等级临界。"
    return ""


def evaluate_land_quality(indicators: dict, area_code: str) -> Tuple[float, str, List[float]]:
    """12 指标加权综合评价（移植自 evaluation.py evaluate_land_quality）。

    Args:
        indicators: 映射后的指标 dict（键为 SJD/YJZ/.../ZDGX 缩写）。
        area_code: 行政区码（如 "440281" 乐昌）。

    Returns:
        (quality_index, grade, memberships): 综合指数、等级、12 个隶属度列表。
    """
    region = get_region_mapping(area_code)
    ejnyq_idx = region["ejnyq_idx"]
    coef = MODEL2_COEFFICIENTS[ejnyq_idx]

    # 7 个数值指标隶属度
    memberships = []
    for i, abbr in enumerate(NUMERIC_INDICATORS):
        u = indicators.get(abbr)
        a = coef["a"][i]
        c = coef["c"][i]
        ut1 = coef["ut1"][i]
        ut2 = coef["ut2"][i]
        memberships.append(membership_numeric(u, a, c, ut1, ut2, i))

    # 5 个概念指标必须保持 Model-2 原始顺序：
    # GCZD, PSNL, GGNL, DXBW, ZDGX。排水/灌溉顺序颠倒会将两者的权重交换。
    concept_memberships = (
        ("GCZD", "mem_zdgc"),
        ("PSNL", "mem_psnl"),
        ("GGNL", "mem_ggnl"),
        ("DXBW", "mem_dxbw"),
        ("ZDGX", "mem_zdgx"),
    )
    for abbr, mem_key in concept_memberships:
        code = indicators.get(abbr)
        memberships.append(membership_concept(code, coef[mem_key]))

    # 加权综合指数
    weights = coef["weights"]
    quality_index = sum(m * w for m, w in zip(memberships, weights))

    # 等级判定
    grade = determine_model2_grade(quality_index, MODEL2_GRADE_LIMITS[ejnyq_idx])

    return quality_index, grade, memberships


def evaluate_soil_indicators(
    soil_indicators: dict, area_code: str
) -> Tuple[float, str, List[float]]:
    """从 ``parcel_info.soil_indicators`` 执行统一的 Model-2 评价。

    地图查询与智能体共用此入口，避免各自复制字段映射和等级分界。
    """
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    mapped = ParcelDataAccessor()._map_indicators_to_inputs(soil_indicators, "model-2")
    return evaluate_land_quality(mapped, area_code)
