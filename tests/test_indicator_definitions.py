import pytest

from framework.domain.statistics import classify_indicator, get_indicator_definition


@pytest.mark.parametrize(("metric", "value", "bucket"), [
    ("soil_ph", 4.49, "very_strong_acid"),
    ("soil_ph", 4.5, "strong_acid"),
    ("soil_ph", 5.5, "acid"),
    ("soil_ph", 6.5, "neutral"),
    ("soil_ph", 7.5, "neutral"),
    ("soil_ph", 7.51, "alkaline"),
    ("organic_matter", 10, "low"),
    ("organic_matter", 20, "medium_low"),
    ("organic_matter", 25, "medium_high"),
    ("organic_matter", 40, "high"),
    ("organic_matter", 400, "high"),
    ("available_phosphorus", 35, "medium_high"),
    ("available_phosphorus", 40, "high"),
    ("available_phosphorus", 41, "high"),
    ("available_potassium", 150, "medium_high"),
    ("available_potassium", 201, "high"),
    ("bulk_density", 0.9, "low"),
    ("bulk_density", 1.0, "normal"),
    ("bulk_density", 1.2, "normal"),
    ("bulk_density", 1.4, "high"),
    ("bulk_density", 2.1, "very_high"),
    ("plow_layer_thickness", 15, "low"),
    ("plow_layer_thickness", 19.9, "medium"),
    ("plow_layer_thickness", 20, "high"),
    ("effective_soil_depth", 60, "low"),
    ("effective_soil_depth", 80, "medium"),
    ("effective_soil_depth", 100, "high"),
    ("quality_grade", "3等", "grade_3"),
])
def test_indicator_boundaries(metric, value, bucket):
    assert classify_indicator(metric, value).key == bucket


def test_values_outside_positive_domains_are_unclassified():
    assert classify_indicator("organic_matter", 0) is None
    assert classify_indicator("bulk_density", 0) is None
    assert classify_indicator("effective_soil_depth", -1) is None


def test_over_40_uses_the_same_high_color():
    for metric in ("organic_matter", "available_phosphorus"):
        at_40 = classify_indicator(metric, 40)
        over_40 = classify_indicator(metric, 400)
        assert at_40.key == over_40.key == "high"
        assert at_40.color == over_40.color
        assert get_indicator_definition(metric).buckets[-1].upper is None


def test_effective_depth_uses_imported_topsoil_field():
    definition = get_indicator_definition("effective_soil_depth")
    assert definition.source_field == "topsoil_thickness"
