from datetime import datetime, timezone
from types import SimpleNamespace

from framework.api.services import farmland_statistics
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
        {
            "parcel_id": "P1",
            "area_mu": 2,
            "soil_indicators": '{"quality_grade": "9等"}',
            "assessment_result": {"result": {"quality_grade": "8等"}},
        },
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


def test_parcel_response_uses_versioned_calculation_for_parcel_2038():
    parcel = SimpleNamespace(
        parcel_id="2038",
        area_code="440205",
        soil_indicators={
            "quality_grade": "9",
            "composite_index": 0.707,
            "soil_ph": 5.504503,
            "organic_matter": 31.80049,
            "available_phosphorus": 50.578899,
            "available_potassium": 51.145582,
            "bulk_density": 1.16,
            "topsoil_thickness": 100.0,
            "plow_layer_thickness": 20.0,
            "soil_texture": "壤土",
            "irrigation_condition": "不满足",
            "drainage_capacity": "满足",
            "terrain_position": "山地坡中",
            "soil_structure": "上松下紧型",
        },
    )

    response = _parcel_response(
        parcel,
        area_mu=1737.44,
        assessment={"quality_grade": "8", "composite_index": 0.7531518984529598},
        version={"resultId": 12, "modelVersion": "quality-grade-2.1.0"},
    )

    assert response["qualityGrade"] == "8"
    assert response["compositeIndex"] == 0.7532
    assert response["qualityAssessment"]["resultId"] == 12


def test_live_query_materializes_clip_and_short_circuits_contained_parcels():
    sql = str(farmland_statistics._live_statistics_sql("SELECT geom FROM region"))

    assert "scope AS MATERIALIZED" in sql
    assert "clipped AS MATERIALIZED" in sql
    assert "measured AS MATERIALIZED" in sql
    assert "ST_CoveredBy(p.geom, scope.geom)" in sql
    assert sql.count("ST_Intersection(p.geom, scope.geom)") == 1
    assert sql.count("ST_Area(clipped_geom::geography)") == 1


def test_aggregate_uses_precomputed_rows_for_administrative_region(monkeypatch):
    timestamp = datetime(2024, 1, 2, tzinfo=timezone.utc)
    cached_rows = [{
        "parcel_id": "P1",
        "area_code": "440281",
        "area_mu": 2.0,
        "soil_indicators": {"soil_ph": 5.5},
        "updated_at": timestamp,
    }]
    monkeypatch.setattr(
        farmland_statistics,
        "_scope_sql",
        lambda _scope: (
            "SELECT geom FROM unused",
            {},
            {
                "type": "administrative_region",
                "regionType": "county",
                "regionId": "440281",
                "displayName": "test",
            },
        ),
    )
    monkeypatch.setattr(
        farmland_statistics,
        "_precomputed_statistics_rows",
        lambda _scope: cached_rows,
    )

    result = farmland_statistics.aggregate_statistics({
        "scope": {
            "type": "administrative_region",
            "region_type": "county",
            "region_id": "440281",
        },
        "metrics": ["soil_ph"],
    })

    assert result["scopeSummary"] == {"parcelCount": 1, "totalAreaMu": 2.0}
    assert result["metrics"][0]["table"]["average"] == 5.5
