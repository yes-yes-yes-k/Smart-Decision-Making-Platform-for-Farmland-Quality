"""Model-2 耕地质量等级评价 — 移植自 模型2/evaluation.py + config.py。

隶属度函数:
- 峰型 (SJD, TRRZ): 1/(1+a*(u-c)^2), 超出 [ut1,ut2] 为 0
- 戒上型 (其余5个数值): <=ut1 为 0, [ut1,c) 用公式, >=c 为 1.0
- 概念型 (5个): 查找表映射
"""
from __future__ import annotations
from typing import List, Tuple
from framework.domain.calculations.coefficients import (
    MODEL2_COEFFICIENTS, GRADE_CONFIG,
    NUMERIC_INDICATORS, CONCEPT_INDICATORS, PEAK_TYPE_INDICES,
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
    primary = region["primary"]
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

    # 5 个概念指标隶属度
    concept_mem_keys = ["mem_zdgc", "mem_ggnl", "mem_psnl", "mem_dxbw", "mem_zdgx"]
    for abbr, mem_key in zip(CONCEPT_INDICATORS, concept_mem_keys):
        code = indicators.get(abbr)
        memberships.append(membership_concept(code, coef[mem_key]))

    # 加权综合指数
    weights = coef["weights"]
    quality_index = sum(m * w for m, w in zip(memberships, weights))

    # 等级判定
    bounds, labels = GRADE_CONFIG[primary]
    grade = determine_grade(quality_index, bounds, labels)

    return quality_index, grade, memberships
