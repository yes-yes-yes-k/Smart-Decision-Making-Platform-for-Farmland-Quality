from datetime import datetime, timezone
from types import SimpleNamespace

from framework.api.services.farmland_statistics import _parcel_response, summarize_rows


def test_summary_is_area_weighted_and_keeps_unclassified_separate():
    timestamp = datetime(2024, 1, 2, tzinfo=timezone.utc)
    rows = [
        {"parcel_id": "P1", "area_mu": 1, "soil_indicators": {"organic_matter": 10}, "updated_at": timestamp},
        {"parcel_id": "P2", "area_mu": 3, "soil_indicators": {"organic_matter": 20}, "updated_at": timestamp},
        {"parcel_id": "P3", "area_mu": 2, "soil_indicators": {"organic_matter": -1}, "updated_at": timestamp},
    ]

    result = summarize_rows(rows, ["organic_matter"])
    metric = result["metrics"][0]
    buckets = {item["key"]: item for item in metric["distribution"]}

    assert result["scopeSummary"] == {"parcelCount": 3, "totalAreaMu": 6.0}
    assert metric["table"]["average"] == 17.5
    assert metric["table"]["validParcelCount"] == 2
    assert metric["table"]["validAreaMu"] == 4.0
    assert metric["table"]["range"] == {"min": 10.0, "max": 20.0}
    assert buckets["low"]["parcelCount"] == 1
    assert buckets["medium_low"]["areaMu"] == 3.0
    assert buckets["medium_low"]["areaPercent"] == 75.0
    assert metric["unclassified"] == {"parcelCount": 1, "areaMu": 2.0}


def test_summary_parses_json_text_and_quality_grade():
    result = summarize_rows([
        {"parcel_id": "P1", "area_mu": 2, "soil_indicators": '{"quality_grade": "8等"}'},
    ], ["quality_grade"])
    metric = result["metrics"][0]
    assert metric["table"]["average"] == 8.0
    assert metric["distribution"][7]["parcelCount"] == 1


def test_parcel_response_includes_full_geometry_area_in_mu():
    parcel = SimpleNamespace(
        parcel_id="P1",
        area_code="440281",
        soil_indicators={
            "quality_grade": 8,
            "organic_matter": 19.178225,
            "soil_ph": 5.578967,
            "available_phosphorus": 27.682971,
        },
    )

    response = _parcel_response(parcel, area_mu=379.850149)

    assert response["areaMu"] == 379.8501


def test_parcel_response_uses_null_area_when_geometry_is_missing():
    parcel = SimpleNamespace(parcel_id="P2", area_code="440281", soil_indicators={})

    response = _parcel_response(parcel, area_mu=None)

    assert response["areaMu"] is None
