from datetime import datetime, timezone
from types import SimpleNamespace

import json

import pytest

from framework.api.services import farmland_statistics as service
from framework.api.services.farmland_statistics import _parcel_response, list_boundaries, summarize_rows


class _MappingResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


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


def test_metric_catalog_is_grouped_ordered_and_reports_observed_years(monkeypatch):
    monkeypatch.setattr(service, "_catalog_rows", lambda: [
        {
            "data_year": 2024,
            "soil_indicators": {
                "soil_ph": 5.8,
                "organic_matter": 18.0,
                "soil_texture": "壤土",
                "irrigation_condition": "满足",
            },
            "quality_grade": "4等",
            "composite_index": 0.76,
        },
        {
            "data_year": 2021,
            "soil_indicators": {"soil_ph": 5.6, "total_n": 1.1},
            "quality_grade": "5等",
            "composite_index": 0.71,
        },
    ])

    catalog = service.metric_metadata()
    metrics = {item["metricKey"]: item for item in catalog["metrics"]}

    assert catalog["classificationVersion"] == "2026-09-21.1"
    assert [group["key"] for group in catalog["groups"]] == [
        "quality_evaluation", "soil_nutrients", "physical_properties",
        "pollution_status", "farmland_conditions",
    ]
    assert catalog["defaultYear"] == 2024
    assert metrics["soil_ph"]["label"] == "土壤 pH"
    assert metrics["soil_ph"]["dataYears"] == [2024, 2021]
    assert metrics["total_nitrogen"]["dataYears"] == [2021]
    assert metrics["total_nitrogen"]["availability"] == "partial"
    assert metrics["cadmium"]["availability"] == "unavailable"


def test_summary_supports_categorical_metrics():
    result = summarize_rows([
        {"area_mu": 2, "soil_indicators": {"soil_texture": "壤土"}},
        {"area_mu": 1, "soil_indicators": {"soil_texture": "砂土"}},
        {"area_mu": 3, "soil_indicators": {"soil_texture": "壤土"}},
    ], ["soil_texture"], data_year=2024)

    metric = result["metrics"][0]
    distribution = {item["key"]: item for item in metric["distribution"]}
    assert metric["valueType"] == "category"
    assert metric["dataYear"] == 2024
    assert metric["table"]["average"] is None
    assert distribution["壤土"]["parcelCount"] == 2
    assert distribution["壤土"]["areaMu"] == 5.0


def test_scope_contract_echoes_normalized_viewport():
    _sql, _params, scope = service._scope_sql({
        "type": "viewport", "bbox": [113, 24, 114, 25],
    })
    assert scope == {
        "scopeVersion": 1,
        "type": "viewport",
        "bbox": [113.0, 24.0, 114.0, 25.0],
        "srid": 4326,
    }


def test_boundaries_respect_min_zoom_without_database(monkeypatch):
    monkeypatch.setattr(
        service.db.session,
        "execute",
        lambda *_args, **_kwargs: pytest.fail("low zoom must not query the database"),
    )
    result = list_boundaries("village", zoom="10")
    assert result["suppressedByZoom"] is True
    assert result["features"] == []


def test_boundaries_return_hierarchical_geojson(monkeypatch):
    rows = [{
        "object_type": "township",
        "object_id": "440281001",
        "display_name": "乐城街道",
        "area_code": "440281001",
        "parent_object_type": "county",
        "parent_object_id": "440281",
        "metadata": {"selectable": True},
        "geometry": json.dumps({"type": "MultiPolygon", "coordinates": []}),
    }]
    monkeypatch.setattr(
        service.db.session, "execute", lambda *_args, **_kwargs: _MappingResult(rows),
    )
    result = list_boundaries(
        "township", parent_type="county", parent_id="440281",
        bbox="112,24,114,26", zoom="10",
    )
    feature = result["features"][0]
    assert feature["properties"]["parentId"] == "440281"
    assert feature["properties"]["minZoom"] == 9
    assert feature["geometry"]["type"] == "MultiPolygon"
