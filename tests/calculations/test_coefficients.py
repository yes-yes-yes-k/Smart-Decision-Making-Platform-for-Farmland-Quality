# tests/calculations/test_coefficients.py
from framework.domain.calculations.coefficients import (
    AREA_TO_REGION, MODEL2_COEFFICIENTS, MODEL3_COEFFICIENTS, MODEL3_WEIGHTS,
    GRADE_CONFIG, DISCRETE_CN_MAP, DISCRETE_EN_MAP,
)
from framework.domain.calculations.region_mapping_service import (
    get_region_mapping, refresh_region_cache, validate_region_mappings,
    DEFAULT_REGION_MAPPING,
)

def test_area_to_region_lechang():
    """乐昌 440281 → 南岭丘陵 NL, 华南 HN, ejnyq_idx 3."""
    info = AREA_TO_REGION["440281"]
    assert info["secondary"] == "NL"
    assert info["primary"] == "HN"
    assert info["ejnyq_idx"] == 3


def test_area_to_region_covers_all_imported_shaoguan_counties():
    imported_codes = {
        "440203", "440204", "440205", "440222", "440224",
        "440229", "440232", "440233", "440281", "440282",
    }
    assert imported_codes <= AREA_TO_REGION.keys()
    assert AREA_TO_REGION["440203"]["ejnyq_idx"] == 0  # 武江区/MNY
    assert AREA_TO_REGION["440205"]["ejnyq_idx"] == 3  # 曲江区/NL

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


# ===== get_region_mapping 服务层测试 =====

def test_get_region_mapping_hardcoded_fallback_lechang():
    """硬编码回退：乐昌 440281 在 DB 不可用时从 AREA_TO_REGION 返回."""
    refresh_region_cache()  # 清空缓存，强制重新加载（DB 不可用→空缓存→回退硬编码）
    result = get_region_mapping("440281")
    assert result["primary"] == "HN"
    assert result["secondary"] == "NL"
    assert result["ejnyq_idx"] == 3

def test_get_region_mapping_unknown_area_code_degrades():
    """未知 area_code 降级到默认值."""
    refresh_region_cache()
    result = get_region_mapping("999999")
    assert result == DEFAULT_REGION_MAPPING
    assert result["primary"] == "HN"
    assert result["secondary"] == "MNY"
    assert result["ejnyq_idx"] == 0

def test_get_region_mapping_returns_dict_not_shared_reference():
    """返回的 dict 应为独立副本，避免调用方修改污染缓存."""
    refresh_region_cache()
    result = get_region_mapping("999999")
    result["primary"] = "MODIFIED"
    result2 = get_region_mapping("999999")
    assert result2["primary"] == "HN"  # 默认值未被污染

def test_refresh_region_cache_clears_cache():
    """refresh_region_cache 清空缓存，下次查询重新加载."""
    # 先填充缓存
    get_region_mapping("440281")
    refresh_region_cache()
    # 再次查询，应重新加载（不报错即通过）
    result = get_region_mapping("440281")
    assert result["ejnyq_idx"] == 3

def test_validate_region_mappings_passes_for_hardcoded():
    """验证硬编码 AREA_TO_REGION 中的映射与系数配置一致."""
    refresh_region_cache()
    is_valid, issues = validate_region_mappings()
    assert is_valid, f"映射一致性验证失败: {issues}"
    assert len(issues) == 0
