# tests/calculations/test_grade_calculation.py
import math
from framework.domain.calculations.grade_calculation import (
    membership_numeric, membership_concept, evaluate_land_quality, determine_grade
)
from framework.domain.calculations.coefficients import MODEL2_COEFFICIENTS, GRADE_CONFIG

def test_peak_type_sjd_at_optimal():
    """SJD 峰型: u=c=6.7 时隶属度=1.0."""
    # idx 0 = SJD, 峰型
    result = membership_numeric(6.7, 0.221129, 6.7, 4.0, 9.5, 0)
    assert abs(result - 1.0) < 1e-6

def test_peak_type_sjd_outside_range():
    """SJD 峰型: u <= ut1 或 u >= ut2 时返回 0."""
    assert membership_numeric(3.0, 0.221129, 6.7, 4.0, 9.5, 0) == 0.0
    assert membership_numeric(10.0, 0.221129, 6.7, 4.0, 9.5, 0) == 0.0

def test_peak_type_trrz_within_range():
    """TRRZ 峰型: ut1 < u < ut2 时用公式, u=c 时为 1.0."""
    # idx 4 = TRRZ, 峰型 (PEAK_TYPE_INDICES={0,4})
    assert membership_numeric(1.35, 2.786523, 1.35, 0.90, 2.10, 4) == 1.0
    expected = 1.0 / (1.0 + 2.786523 * (2.0 - 1.35) ** 2)
    assert abs(membership_numeric(2.0, 2.786523, 1.35, 0.90, 2.10, 4) - expected) < 1e-6

def test_peak_type_trrz_below_ut1():
    """TRRZ 峰型: u <= ut1 时返回 0."""
    assert membership_numeric(0.85, 2.786523, 1.35, 0.90, 2.10, 4) == 0.0

def test_upper_limit_yjz_between_ut1_and_c():
    """YJZ 戒上型: ut1 < u < c 时用公式."""
    # idx 1 = YJZ, 戒上型, c=38, ut1=6.0
    result = membership_numeric(20.0, 0.002163, 38.0, 6.0, 38.0, 1)
    expected = 1.0 / (1.0 + 0.002163 * (20.0 - 38.0) ** 2)
    assert abs(result - expected) < 1e-6
    assert 0.0 < result < 1.0

def test_membership_concept_loam_rt():
    """概念指标: RT 代码 → 查找隶属度."""
    lookup = {"RT": 1.0, "SRT": 0.75}
    assert membership_concept("RT", lookup) == 1.0
    assert membership_concept("UNKNOWN", lookup) == 0.0

def test_determine_grade_hn():
    """HN 等级判定: qi >= 0.865 → 1 等."""
    bounds, labels = GRADE_CONFIG["HN"]
    assert determine_grade(0.90, bounds, labels) == "1"
    assert determine_grade(0.75, bounds, labels) == "6"
    assert determine_grade(0.50, bounds, labels) == "10"

def test_evaluate_land_quality_lechang():
    """乐昌地块完整评价: 返回 quality_index ∈ [0,1], grade ∈ 1-10."""
    indicators = {
        "SJD": 5.5, "YJZ": 20.0, "YXL": 15.0, "SXJ": 100.0,
        "TRRZ": 1.2, "YXTCHD": 80.0, "GCHD": 15.0,
        "GCZD": "RT", "GGNL": "FS", "PSNL": "CM", "DXBW": "LHR", "ZDGX": "TLBC",
    }
    quality_index, grade, memberships = evaluate_land_quality(indicators, "440281")
    assert 0.0 <= quality_index <= 1.0
    assert grade in [str(i) for i in range(1, 11)]
    assert len(memberships) == 12
