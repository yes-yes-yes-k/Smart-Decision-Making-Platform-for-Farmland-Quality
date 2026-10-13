# tests/calculations/test_grade_calculation.py
import math
from pathlib import Path

import pytest
from framework.domain.calculations.grade_calculation import (
    membership_numeric, membership_concept, evaluate_land_quality, determine_grade,
    determine_model2_grade,
)
from framework.domain.calculations.coefficients import (
    MODEL2_COEFFICIENTS, MODEL2_GRADE_LIMITS, GRADE_CONFIG,
)

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


def test_model2_grade_uses_secondary_region_limits():
    """Model-2 等级必须使用二级农业区原始 limits。"""
    assert determine_model2_grade(0.9170, MODEL2_GRADE_LIMITS[3]) == "1"
    assert determine_model2_grade(0.7532, MODEL2_GRADE_LIMITS[3]) == "8"
    assert determine_model2_grade(0.7199, MODEL2_GRADE_LIMITS[3]) == "10"


def test_parcel_2038_matches_reference_model2_port():
    """地块 2038 的在线计算与原 Model-2 Python 移植结果一致。"""
    indicators = {
        "SJD": 5.504503, "YJZ": 31.80049, "YXL": 50.578899,
        "SXJ": 51.145582, "TRRZ": 1.16, "YXTCHD": 100.0, "GCHD": 20.0,
        "GCZD": "RT", "PSNL": "M", "GGNL": "US", "DXBW": "MSM",
        "ZDGX": "TLBC",
    }

    quality_index, grade, memberships = evaluate_land_quality(indicators, "440205")

    assert quality_index == pytest.approx(0.7531518984529598)
    assert grade == "8"
    # 排水、灌溉和南岭地形隶属度的顺序/系数不得再交换。
    assert memberships[8:11] == [0.8, 0.3, 0.45]


def test_online_model2_matches_reference_engine_for_deployed_csv():
    """在线 DB 计算与已验证的原 Model-2 引擎逐地块数值等价。"""
    from ai_culti_demo.farmland_grade_eval.config import EvaluationConfig
    from ai_culti_demo.farmland_grade_eval.data_loader import load_parcels_from_csv
    from ai_culti_demo.farmland_grade_eval.evaluation import (
        evaluate_land_quality as evaluate_reference,
    )

    csv_path = (
        Path(__file__).resolve().parents[2]
        / "bin" / "farmland_quality_eval" / "Farmland_quality_Level_Database.csv"
    )
    parcels = load_parcels_from_csv(str(csv_path))
    area_codes = {
        1: "440281", 2: "440232", 3: "440224", 4: "440282", 5: "440222",
        6: "440233", 7: "440205", 8: "440203", 9: "440204", 10: "440229",
    }
    textures = ["SRST", "SRT", "RT", "FRT", "SNRT", "NRT", "FNRT", "SNT", "RNT", "FNT", "NT", "ZNT"]
    drainage = ["CM", "M", "JM", "BM"]
    irrigation = ["FS", "S", "BS", "US"]
    terrains = ["PLT", "PMG", "PUG", "WVB", "MB", "LHR", "MPH", "UHR", "MSL", "MSM", "MSU"]
    structures = ["TLBC", "St", "IL", "Ct", "TCBL", "TL", "Lt"]
    config = EvaluationConfig()

    for parcel in parcels:
        expected = evaluate_reference(config, parcel)
        indicators = {
            "SJD": parcel.sjd, "YJZ": parcel.yjz, "YXL": parcel.yxl,
            "SXJ": parcel.sxj, "TRRZ": parcel.trrz,
            "YXTCHD": parcel.yxtchd, "GCHD": parcel.gchd,
            "GCZD": textures[parcel.zdgc - 1],
            "PSNL": drainage[parcel.psnl - 1],
            "GGNL": irrigation[parcel.ggnl - 1],
            "DXBW": terrains[parcel.dxbw - 1],
            "ZDGX": structures[parcel.zdgx - 1],
        }

        actual_index, actual_grade, actual_memberships = evaluate_land_quality(
            indicators, area_codes[parcel.xqmc]
        )

        assert actual_index == pytest.approx(expected.quality_index), parcel.tybh
        assert actual_grade == str(expected.grade), parcel.tybh
        assert actual_memberships == pytest.approx(expected.y), parcel.tybh
