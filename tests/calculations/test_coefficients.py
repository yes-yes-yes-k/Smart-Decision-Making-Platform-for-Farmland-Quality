# tests/calculations/test_coefficients.py
from framework.domain.calculations.coefficients import (
    AREA_TO_REGION, MODEL2_COEFFICIENTS, MODEL3_COEFFICIENTS, MODEL3_WEIGHTS,
    GRADE_CONFIG, DISCRETE_CN_MAP, DISCRETE_EN_MAP,
)

def test_area_to_region_lechang():
    """乐昌 440281 → 南岭丘陵 NL, 华南 HN, ejnyq_idx 3."""
    info = AREA_TO_REGION["440281"]
    assert info["secondary"] == "NL"
    assert info["primary"] == "HN"
    assert info["ejnyq_idx"] == 3

def test_model2_coefficients_has_4_regions():
    """Model-2 系数有 4 个二级农业区 (index 0-3)."""
    assert len(MODEL2_COEFFICIENTS) == 4
    for idx in range(4):
        coef = MODEL2_COEFFICIENTS[idx]
        assert len(coef["a"]) == 7  # 7 个数值指标
        assert len(coef["weights"]) == 12  # 12 个指标权重

def test_discrete_en_map_loam_to_rt():
    """英文 loam → 代码 RT."""
    assert DISCRETE_EN_MAP["GCZD"]["loam"] == "RT"
    assert DISCRETE_EN_MAP["GCZD"]["sandy_loam"] == "SRT"

def test_discrete_en_map_dry_to_bm():
    """英文 dry → PSNL 代码 BM, GGNL 代码 US."""
    assert DISCRETE_EN_MAP["PSNL"]["dry"] == "BM"
    assert DISCRETE_EN_MAP["GGNL"]["dry"] == "US"

def test_discrete_cn_map_preserved():
    """原始中文映射保留."""
    assert DISCRETE_CN_MAP["GCZD"]["壤土"] == "RT"

def test_grade_config_hn_thresholds():
    """HN 等级阈值: >=0.885 为 1 等."""
    bounds, labels = GRADE_CONFIG["HN"]
    assert bounds[0] == 0
    assert bounds[1] == 0.6650
    assert labels[0] == "10"  # < 0.6650 为 10 等
    assert labels[9] == "1"  # >= 0.8850 为 1 等
