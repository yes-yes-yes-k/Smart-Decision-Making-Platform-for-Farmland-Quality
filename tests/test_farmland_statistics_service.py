from datetime import datetime, timezone
from types import SimpleNamespace

import json

import pytest

from framework.api.services import farmland_statistics as service
from framework.api.services.farmland_statistics import (
    StatisticsError,
    _parcel_response,
    _scope_sql,
    list_boundaries,
    list_viewport_parcels,
    metric_metadata,
    summarize_rows,
)
from framework.domain.statistics.indicator_definitions import CLASSIFICATION_VERSION
from framework.domain.statistics.quality_audit import audit_indicator_rows


class _MappingResult:
    def __init__(self, *, rows=None, first=None):
        self._rows = rows or []
        self._first = first

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._first


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
            "assessment_result": {
                "result": {"quality_grade": 8, "composite_index": 0.7532},
            },
        },
    ], ["quality_grade"])
    metric = result["metrics"][0]
    assert metric["table"]["average"] == 8.0
    assert metric["distribution"][7]["parcelCount"] == 1


def test_parcel_response_uses_passed_versioned_assessment():
    parcel = SimpleNamespace(
        parcel_id="2038",
        area_code="440205",
        soil_indicators={"quality_grade": 9, "composite_index": 0.42},
    )

    response = _parcel_response(
        parcel,
        area_mu=1737.44,
        assessment={"quality_grade": 8, "composite_index": 0.7532},
        version={"resultId": 12, "modelVersion": "quality-grade-2.1.0"},
    )

    assert response["qualityGrade"] == 8
    assert response["metrics"]["quality_grade"]["value"] == 8
    assert response["qualityAssessment"]["resultId"] == 12


def test_parcel_response_includes_full_geometry_area_in_mu():
    parcel = SimpleNamespace(
        parcel_id="P1",
        area_code="440281",
        soil_indicators={
            "quality_grade": 8,
            "organic_matter": 19.178225,
            "soil_ph": 5.578967,
            "available_phosphorus": 27.682971,
            "available_potassium": 82.5,
            "bulk_density": 1.31,
            "plow_layer_thickness": 20,
            "topsoil_thickness": 80,
        },
    )

    response = _parcel_response(parcel, area_mu=379.850149)

    assert response["areaMu"] == 379.8501
    assert response["availablePotassium"] == 82.5
    assert response["bulkDensity"] == 1.31
    assert response["plowLayerThickness"] == 20
    assert response["effectiveSoilDepth"] == 80
    assert {
        "quality_grade", "soil_ph", "organic_matter", "available_phosphorus",
        "available_potassium", "bulk_density", "plow_layer_thickness",
        "effective_soil_depth",
    }.issubset(response["metrics"])
    assert response["metrics"]["available_potassium"] == {
        "metricKey": "available_potassium",
        "label": "速效钾含量",
        "groupKey": "soil_nutrients",
        "order": 40,
        "valueType": "number",
        "value": 82.5,
        "unit": "mg/kg",
        "bucketKey": "medium_low",
        "bucketLabel": "中低",
        "rangeLabel": "(50,100]",
        "color": "#FC8D59",
        "dataSource": None,
        "measurementYear": None,
        "isImputed": None,
        "imputationMethod": None,
        "qualityFlag": "provenance_missing",
    }


def test_parcel_response_uses_null_area_when_geometry_is_missing():
    parcel = SimpleNamespace(parcel_id="P2", area_code="440281", soil_indicators={})

    response = _parcel_response(parcel, area_mu=None)

    assert response["areaMu"] is None


def test_classification_version_is_shared_by_metadata_summary_and_parcel():
    metadata = metric_metadata()
    summary = summarize_rows([], ["soil_ph"])
    parcel = SimpleNamespace(parcel_id="P3", area_code="440281", soil_indicators={})

    assert metadata["classificationVersion"] == CLASSIFICATION_VERSION
    assert {item["classificationVersion"] for item in metadata["metrics"]} == {
        CLASSIFICATION_VERSION
    }
    assert summary["classificationVersion"] == CLASSIFICATION_VERSION
    assert _parcel_response(parcel, None)["classificationVersion"] == CLASSIFICATION_VERSION


def test_summary_and_parcel_use_the_same_bucket_and_color():
    indicators = {"available_potassium": 82.5}
    summary = summarize_rows([{
        "parcel_id": "P4",
        "area_mu": 1,
        "soil_indicators": indicators,
    }], ["available_potassium"])
    parcel = SimpleNamespace(parcel_id="P4", area_code="440281", soil_indicators=indicators)
    detail_metric = _parcel_response(parcel, 1)["metrics"]["available_potassium"]
    summary_bucket = next(
        bucket for bucket in summary["metrics"][0]["distribution"]
        if bucket["parcelCount"] == 1
    )

    assert detail_metric["bucketKey"] == summary_bucket["key"]
    assert detail_metric["bucketLabel"] == summary_bucket["label"]
    assert detail_metric["rangeLabel"] == summary_bucket["rangeLabel"]
    assert detail_metric["color"] == summary_bucket["color"]


def test_lightweight_parcel_response_returns_only_requested_metric():
    parcel = SimpleNamespace(
        parcel_id="P5",
        area_code="440281",
        soil_indicators={
            "soil_ph": 5.2,
            "indicator_provenance": {
                "soil_ph": {
                    "data_source": "lab",
                    "measurement_year": 2024,
                    "is_imputed": False,
                    "imputation_method": None,
                    "quality_flag": "verified",
                }
            },
        },
    )

    response = _parcel_response(parcel, 10, "soil_ph")

    assert "metrics" not in response
    assert response["metric"]["metricKey"] == "soil_ph"
    assert response["metric"]["dataSource"] == "lab"
    assert response["metric"]["measurementYear"] == 2024
    assert response["metric"]["isImputed"] is False


def test_pick_rejects_excessive_tolerance_before_database(monkeypatch):
    monkeypatch.setattr(
        service.db.session,
        "execute",
        lambda *_args, **_kwargs: pytest.fail("invalid tolerance must not query the database"),
    )

    with pytest.raises(StatisticsError) as error:
        service.pick_parcel(113, 24, tolerance_meters=51)

    assert error.value.code == "invalid_tolerance"


def test_boundaries_respect_min_zoom_without_querying_database(monkeypatch):
    monkeypatch.setattr(
        service.db.session,
        "execute",
        lambda *_args, **_kwargs: pytest.fail("low zoom must not query the database"),
    )

    result = list_boundaries("village", zoom="10")

    assert result["type"] == "FeatureCollection"
    assert result["minZoom"] == 12
    assert result["suppressedByZoom"] is True
    assert result["features"] == []


def test_boundaries_return_geojson_properties(monkeypatch):
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
        service.db.session,
        "execute",
        lambda *_args, **_kwargs: _MappingResult(rows=rows),
    )

    result = list_boundaries(
        "township",
        parent_type="county",
        parent_id="440281",
        bbox="112,24,114,26",
        zoom="10",
    )

    assert result["suppressedByZoom"] is False
    assert result["truncated"] is False
    assert result["features"][0]["properties"] == {
        "regionType": "township",
        "regionId": "440281001",
        "displayName": "乐城街道",
        "areaCode": "440281001",
        "parentType": "county",
        "parentId": "440281",
        "selectable": True,
        "minZoom": 9,
        "maxZoom": None,
    }


def test_viewport_parcels_return_lightweight_thematic_features(monkeypatch):
    rows = [{
        "parcel_id": "P10",
        "area_code": "440281",
        "soil_indicators": {
            "soil_ph": 5.2,
            "indicator_provenance": {
                "soil_ph": {
                    "data_source": "model1_shapefile",
                    "measurement_year": 2024,
                    "is_imputed": False,
                    "quality_flag": "source_unverified",
                }
            },
        },
        "updated_at": datetime(2024, 1, 2, tzinfo=timezone.utc),
        "geometry": '{"type":"Point","coordinates":[113,24]}',
    }]
    monkeypatch.setattr(
        service.db.session,
        "execute",
        lambda *_args, **_kwargs: _MappingResult(rows=rows),
    )

    result = list_viewport_parcels(
        "112,23,114,25", "soil_ph", geometry_mode="centroid", limit="100"
    )

    assert result["type"] == "FeatureCollection"
    assert result["truncated"] is False
    assert result["features"][0]["geometry"]["type"] == "Point"
    properties = result["features"][0]["properties"]
    assert properties["parcelId"] == "P10"
    assert properties["bucketKey"] == "strong_acid"
    assert properties["color"] == "#EF8A62"
    assert properties["dataSource"] == "model1_shapefile"


def test_viewport_parcels_reject_unknown_metric_before_database(monkeypatch):
    monkeypatch.setattr(
        service.db.session,
        "execute",
        lambda *_args, **_kwargs: pytest.fail("invalid metric must not query the database"),
    )

    with pytest.raises(StatisticsError) as error:
        list_viewport_parcels("112,23,114,25", "unknown_metric")

    assert error.value.code == "invalid_metric"


def test_quality_audit_flags_constant_values_and_summarizes_provenance():
    rows = [
        {
            "soil_indicators": {
                "plow_layer_thickness": 20,
                "indicator_provenance": {
                    "plow_layer_thickness": {
                        "data_source": "model1_shapefile",
                        "measurement_year": 2024,
                        "is_imputed": False,
                        "quality_flag": "low_variability",
                    }
                },
            },
            "updated_at": datetime(2024, 1, 2, tzinfo=timezone.utc),
        },
        {
            "soil_indicators": {
                "plow_layer_thickness": 20,
                "indicator_provenance": {
                    "plow_layer_thickness": {
                        "data_source": "model1_shapefile",
                        "measurement_year": 2024,
                        "is_imputed": False,
                        "quality_flag": "low_variability",
                    }
                },
            },
            "updated_at": datetime(2024, 1, 2, tzinfo=timezone.utc),
        },
    ]

    report = audit_indicator_rows(rows)
    metric = next(item for item in report["metrics"] if item["metricKey"] == "plow_layer_thickness")

    assert metric["nonEmptyRate"] == 100.0
    assert metric["uniqueValueCount"] == 1
    assert "constant_value" in metric["qualityFlags"]
    assert metric["provenance"]["dataSources"] == {"model1_shapefile": 2}
    assert metric["provenance"]["isImputed"] == {"false": 2}


def test_multi_region_scope_keeps_input_order_and_uses_union(monkeypatch):
    rows = [
        {"object_id": "440282", "display_name": "南雄市", "has_geom": True},
        {"object_id": "440281", "display_name": "乐昌市", "has_geom": True},
    ]
    monkeypatch.setattr(
        service.db.session,
        "execute",
        lambda *_args, **_kwargs: _MappingResult(rows=rows),
    )

    query, params, response = _scope_sql({
        "type": "administrative_regions",
        "region_type": "county",
        "region_ids": ["440281", "440282"],
    })

    assert "ST_UnaryUnion(ST_Collect(geom))" in query
    assert params["region_ids"] == ["440281", "440282"]
    assert [region["displayName"] for region in response["regions"]] == ["乐昌市", "南雄市"]


def test_polygon_scope_validates_and_normalizes_geometry(monkeypatch):
    monkeypatch.setattr(
        service.db.session,
        "execute",
        lambda *_args, **_kwargs: _MappingResult(first={
            "is_valid": True,
            "reason": "Valid Geometry",
            "area_sq_km": 12.34567,
        }),
    )
    geometry = {
        "type": "Polygon",
        "coordinates": [[[113, 24], [114, 24], [114, 25], [113, 24]]],
    }

    query, params, response = _scope_sql({"type": "polygon", "geometry": geometry})

    assert "ST_ForcePolygonCCW" in query
    assert json.loads(params["geojson"]) == geometry
    assert response == {
        "scopeVersion": 1,
        "type": "polygon",
        "geometryType": "Polygon",
        "vertexCount": 4,
        "areaSqKm": 12.3457,
        "srid": 4326,
    }


@pytest.mark.parametrize("geometry", [
    {"type": "Point", "coordinates": [113, 24]},
    {"type": "Polygon", "coordinates": [[[113, 24], [114, 24], [114, 25], [113, 25]]]},
    {"type": "Polygon", "coordinates": [[[181, 24], [114, 24], [114, 25], [181, 24]]]},
])
def test_polygon_scope_rejects_invalid_geojson_before_database(monkeypatch, geometry):
    monkeypatch.setattr(
        service.db.session,
        "execute",
        lambda *_args, **_kwargs: pytest.fail("invalid GeoJSON must not query the database"),
    )

    with pytest.raises(StatisticsError) as error:
        _scope_sql({"type": "polygon", "geometry": geometry})

    assert error.value.code == "invalid_geometry"


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

    catalog = metric_metadata()
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
    _sql, _params, scope = _scope_sql({
        "type": "viewport", "bbox": [113, 24, 114, 25],
    })
    assert scope == {
        "scopeVersion": 1,
        "type": "viewport",
        "bbox": [113.0, 24.0, 114.0, 25.0],
        "srid": 4326,
    }


def test_live_query_materializes_clip_and_short_circuits_contained_parcels():
    sql = str(service._live_statistics_sql(
        "SELECT geom FROM region",
        "SELECT 1 AS parcel_pk, 'P1' AS parcel_id, NULL AS area_code, "
        "NULL AS geom, '{}'::json AS soil_indicators, NULL::text AS quality_grade, "
        "NULL::double precision AS composite_index, NULL::timestamptz AS updated_at",
    ))

    assert "scope AS MATERIALIZED" in sql
    assert "data AS MATERIALIZED" in sql
    assert "clipped AS MATERIALIZED" in sql
    assert "parcel_areas AS MATERIALIZED" in sql
    assert "ST_CoveredBy(data.geom, scope.geom)" in sql
    assert sql.count("ST_Intersection(data.geom, scope.geom)") == 1
    assert sql.count("ST_Area(clipped_geom::geography)") == 1


def test_aggregate_uses_precomputed_rows_for_administrative_region(monkeypatch):
    timestamp = datetime(2024, 1, 2, tzinfo=timezone.utc)
    cached_rows = [{
        "parcel_id": "P1",
        "area_code": "440281",
        "area_mu": 2.0,
        "soil_indicators": {"soil_ph": 5.5},
        "quality_grade": None,
        "composite_index": None,
        "updated_at": timestamp,
    }]
    monkeypatch.setattr(service, "_resolve_year", lambda _value: 2024)
    monkeypatch.setattr(
        service,
        "_scope_sql",
        lambda _scope: (
            "SELECT geom FROM unused",
            {},
            {
                "scopeVersion": 1,
                "type": "administrative_region",
                "regionType": "county",
                "regionId": "440281",
                "displayName": "test",
            },
        ),
    )
    monkeypatch.setattr(service, "_dataset_sql", lambda _year: ("SELECT 1", {}))
    monkeypatch.setattr(
        service,
        "_precomputed_statistics_rows",
        lambda _scope, _dataset, _params: cached_rows,
    )

    result = service.aggregate_statistics({
        "scope": {
            "type": "administrative_region",
            "region_type": "county",
            "region_id": "440281",
        },
        "metrics": ["soil_ph"],
    })

    assert result["scopeSummary"] == {"parcelCount": 1, "totalAreaMu": 2.0}
    assert result["metrics"][0]["table"]["average"] == 5.5


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

    assert response["qualityGrade"] == 8  # Canonical metric values are numeric.
    assert response["compositeIndex"] == 0.7532
    assert response["qualityAssessment"]["resultId"] == 12
