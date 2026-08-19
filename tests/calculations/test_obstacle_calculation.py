# tests/calculations/test_obstacle_calculation.py
"""Model-3 障碍诊断计算模块测试。"""
from framework.domain.calculations.obstacle_calculation import (
    calc_continuous,
    calc_discrete,
    calc_obstacle_level,
    calc_obstacle_degree,
    diagnosis_row,
)


# ---------- calc_continuous 连续指标隶属度 ----------

def test_calc_continuous_at_peak():
    """u=c 时峰型隶属度为 1.0。"""
    coef = {"a": 0.256941, "c": 6.7, "L": 4.0, "U": 9.5}
    assert abs(calc_continuous(6.7, coef) - 1.0) < 1e-6


def test_calc_continuous_out_of_range():
    """超出 [L, U] 区间返回 0。"""
    coef = {"a": 0.256941, "c": 6.7, "L": 4.0, "U": 9.5}
    assert calc_continuous(3.5, coef) == 0.0  # 低于 L
    assert calc_continuous(10.0, coef) == 0.0  # 高于 U


def test_calc_continuous_partial():
    """区间内偏离最优值时返回 (0, 1) 之间的隶属度。"""
    coef = {"a": 0.256941, "c": 6.7, "L": 4.0, "U": 9.5}
    result = calc_continuous(5.5, coef)
    expected = 1.0 / (1.0 + 0.256941 * (5.5 - 6.7) ** 2)
    assert abs(result - expected) < 1e-6
    assert 0.0 < result < 1.0


def test_calc_continuous_none_value():
    """u=None 返回 0.0。"""
    coef = {"a": 0.256941, "c": 6.7, "L": 4.0, "U": 9.5}
    assert calc_continuous(None, coef) == 0.0


# ---------- calc_discrete 离散指标隶属度 ----------

def test_calc_discrete_known_code():
    coef = {"FS": 1.0, "S": 0.8, "BS": 0.6, "US": 0.3}
    assert calc_discrete("FS", coef) == 1.0
    assert calc_discrete("US", coef) == 0.3


def test_calc_discrete_unknown_code():
    """未知代码或 None 返回 0.0。"""
    coef = {"FS": 1.0, "S": 0.8}
    assert calc_discrete("UNKNOWN", coef) == 0.0
    assert calc_discrete(None, coef) == 0.0


# ---------- calc_obstacle_level 障碍等级判定 ----------

def test_obstacle_level_ph_heavy():
    """pH <= 4.5 → 重度障碍。"""
    assert calc_obstacle_level("SJD", 4.0) == "重度障碍"
    assert calc_obstacle_level("SJD", 4.5) == "重度障碍"


def test_obstacle_level_ph_none():
    """pH 6.5-7.5 → 无障碍。"""
    assert calc_obstacle_level("SJD", 7.0) == "无障碍"


def test_obstacle_level_organic_matter():
    """有机质 > 25 → 无障碍, <=10 → 重度。"""
    assert calc_obstacle_level("YJZ", 30.0) == "无障碍"
    assert calc_obstacle_level("YJZ", 8.0) == "重度障碍"


def test_obstacle_level_concept_ggnl():
    """概念指标 GGNL 按代码映射。"""
    assert calc_obstacle_level("GGNL", "US") == "重度障碍"
    assert calc_obstacle_level("GGNL", "FS") == "无障碍"


def test_obstacle_level_gczd_by_membership():
    """GCZD 标记 by_membership, 按隶属度判定。"""
    assert calc_obstacle_level("GCZD", "RT", 1.0) == "无障碍"
    assert calc_obstacle_level("GCZD", "SRST", 0.4) == "重度障碍"
    assert calc_obstacle_level("GCZD", "FNT", 0.65) == "中度障碍"
    assert calc_obstacle_level("GCZD", "NRT", 0.8) == "轻度障碍"


def test_obstacle_level_dxbw_by_membership():
    """DXBW 标记 by_membership, 按隶属度判定。"""
    assert calc_obstacle_level("DXBW", "PLT", 1.0) == "无障碍"
    assert calc_obstacle_level("DXBW", "MSU", 0.2) == "重度障碍"
    assert calc_obstacle_level("DXBW", "LHR", 0.6) == "中度障碍"


# ---------- calc_obstacle_degree 障碍度计算 ----------

def test_obstacle_degree_sums_to_one():
    """障碍度之和归一化为 1.0。"""
    memberships = [0.8, 0.6, 0.9, 0.5, 0.7, 0.8, 0.6, 1.0, 0.8, 0.6, 0.5, 0.4]
    weights = [0.07, 0.10, 0.06, 0.07, 0.05, 0.06, 0.06, 0.09, 0.11, 0.14, 0.13, 0.08]
    degrees = calc_obstacle_degree(memberships, weights)
    assert abs(sum(degrees) - 1.0) < 1e-6
    assert all(0.0 <= d <= 1.0 for d in degrees)


def test_obstacle_degree_all_full_membership():
    """所有隶属度为 1 时障碍度全为 0 (sum=0)。"""
    memberships = [1.0] * 12
    weights = [0.07, 0.10, 0.06, 0.07, 0.05, 0.06, 0.06, 0.09, 0.11, 0.14, 0.13, 0.08]
    degrees = calc_obstacle_degree(memberships, weights)
    assert degrees == [0.0] * 12


# ---------- diagnosis_row 主要/次要因子识别 ----------

LECHANG_INDICATORS = {
    "SJD": 5.5, "YJZ": 20.0, "YXL": 15.0, "SXJ": 100.0,
    "TRRZ": 1.2, "YXTCHD": 80.0, "GCHD": 15.0,
    "GCZD": "RT", "GGNL": "FS", "PSNL": "CM", "DXBW": "LHR", "ZDGX": "TLBC",
}


def test_diagnosis_row_lechang_multi_obstacle():
    """乐昌地块: 多障碍, 主要因子 DXBW/YJZ, 次要 YXL/SXJ。"""
    result = diagnosis_row(LECHANG_INDICATORS, "440281")
    assert result["obstacle_type"] == "多障碍"
    assert result["primary_factors"] == ["DXBW", "YJZ"]
    assert result["secondary_factors"] == ["YXL", "SXJ"]
    assert len(result["obstacle_degrees"]) == 12
    assert abs(sum(result["obstacle_degrees"].values()) - 1.0) < 1e-6
    assert len(result["memberships"]) == 12
    assert len(result["obstacle_levels"]) == 12
    # GCZD=RT 隶属度 1.0 → 无障碍
    assert result["obstacle_levels"]["GCZD"] == "无障碍"
    # DXBW=LHR 隶属度 0.6 → 中度障碍
    assert result["obstacle_levels"]["DXBW"] == "中度障碍"


def test_diagnosis_row_no_obstacle():
    """所有指标达最优值时 → 无明显障碍。"""
    ideal = {
        "SJD": 6.7, "YJZ": 38.0, "YXL": 40.0, "SXJ": 205.0,
        "TRRZ": 1.35, "YXTCHD": 100.0, "GCHD": 20.2,
        "GCZD": "RT", "GGNL": "FS", "PSNL": "CM", "DXBW": "PLT", "ZDGX": "TLBC",
    }
    result = diagnosis_row(ideal, "440281")
    assert result["obstacle_type"] == "无明显障碍"
    assert result["primary_factors"] == []
    assert result["secondary_factors"] == []
