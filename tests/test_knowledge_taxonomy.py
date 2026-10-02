import pytest

from framework.knowledge.taxonomy import (
    DOMAIN_CODES,
    classify_label_candidates,
    domain_metadata,
    expand_with_parent_domains,
    normalize_label_codes,
    primary_domain_for_category,
)


def test_confirmed_domain_codes_are_stable():
    assert DOMAIN_CODES == (
        "heavy_metal", "food_security", "cultivated_land_quality",
    )


def test_topic_label_expands_to_parent_domain():
    assert expand_with_parent_domains(["heavy_metal.cadmium"]) == [
        "heavy_metal.cadmium", "heavy_metal",
    ]


def test_invalid_label_is_rejected():
    with pytest.raises(ValueError, match="不支持"):
        normalize_label_codes(["unknown_domain"])


def test_classifier_creates_cross_domain_review_candidates():
    candidates = classify_label_candidates(
        "研究镉污染对粮食安全和耕地质量等级评价的影响",
        exclude=["cultivated_land_quality"],
    )
    codes = {item["label_code"] for item in candidates}
    assert "heavy_metal" in codes
    assert "heavy_metal.cadmium" in codes
    assert "food_security" in codes
    assert "cultivated_land_quality" not in codes


def test_chemical_symbols_require_token_boundaries():
    candidates = classify_label_candidates(
        "classification based on crop characteristics and remote sensing"
    )
    codes = {item["label_code"] for item in candidates}
    assert "heavy_metal.arsenic" not in codes
    assert "heavy_metal.chromium" not in codes


def test_domain_metadata_has_explicit_false_values():
    assert domain_metadata(["food_security"]) == {
        "domain_heavy_metal": False,
        "domain_food_security": True,
        "domain_cultivated_land_quality": False,
    }


def test_legacy_quality_categories_map_to_cultivated_domain():
    assert primary_domain_for_category("acidification") == "cultivated_land_quality"
