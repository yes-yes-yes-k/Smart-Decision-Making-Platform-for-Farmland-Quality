from framework.agents.cd_conversation import query_cd
from framework.domain.other_models import heavy_metal_cd, heavy_metal_cd_spatial


def test_capability_catalog_distinguishes_prediction_coverage_by_source():
    result = query_cd("capabilities")
    prediction = result["capabilities"]["results"]
    assert prediction["levels_by_source"]["ported"] == ("township",)
    assert "county" in prediction["levels_by_source"]["native"]
    assert prediction["unit_status"] == "unverified"
    assert len(result["flux"]) == 8


def test_explicit_prediction_year_does_not_read_undated_records(monkeypatch):
    def unexpected_query(*args, **kwargs):
        raise AssertionError("Undated prediction records must not be queried")

    monkeypatch.setattr(heavy_metal_cd_spatial, "region_statistics", unexpected_query)
    result = query_cd("results", model_id="crop_cd", year=2025)
    assert result["status"] == "unsupported_year"


def test_prediction_statistics_keep_sources_separate(monkeypatch):
    def region_statistics(model_id, region_type, region_id, source):
        return {
            "source": source, "region_id": region_id, "unit_status": "unverified",
            "has_data": source == "ported" and region_type == "township",
            "ported_unavailable_for_region_type": source == "ported" and region_type != "township",
        }

    monkeypatch.setattr(heavy_metal_cd_spatial, "region_statistics", region_statistics)
    result = query_cd("results", model_id="crop_cd", region_type="township", region_id="T1")
    assert set(result["sources"]) == {"native", "ported"}
    assert all(item["unit_status"] == "unverified" for item in result["sources"].values())
    assert result["sources"]["native"]["status"] == "no_data"
    assert result["sources"]["ported"]["status"] == "ok"
    county = query_cd("results", model_id="crop_cd", region_type="county", region_id="C1")
    assert county["sources"]["ported"]["status"] == "unsupported_region_level"


def test_missing_solution_does_not_use_model_default(monkeypatch):
    def unexpected_prediction(*args, **kwargs):
        raise AssertionError("Missing parameter must be requested before prediction")

    monkeypatch.setattr(heavy_metal_cd, "predict", unexpected_prediction)
    contract = next(item for item in heavy_metal_cd.available_models() if item["model_id"] == "crop_cd")
    parameters = {field: 1.0 for field in contract["input_fields"] if field != "solution"}
    result = query_cd("predict", model_id="crop_cd", parameters=parameters)
    assert result["missing_fields"] == ["solution"]


def test_cd_turn_uses_same_result_in_normal_and_streaming_chat(monkeypatch):
    from framework.agents import cd_conversation
    from framework.agents.orchestrator import MultiAgentOrchestrator

    result = {"status": "ok", "answer": "Cd 统计结果"}
    monkeypatch.setattr(cd_conversation, "answer_cd", lambda request, history: result)
    orchestrator = MultiAgentOrchestrator()
    request = {"question": "查询镉统计"}
    assert orchestrator.run(request) == result
    events = list(orchestrator.run_stream(request))
    assert events[-1] == {"type": "done", "data": result}


def test_prediction_draft_merges_only_with_same_scope():
    from framework.agents.cd_conversation import _draft_context

    contract = next(item for item in heavy_metal_cd.available_models() if item["model_id"] == "crop_cd")
    first, second = contract["input_fields"][:2]
    initial = query_cd("predict", model_id="crop_cd", year=2024, parameters={first: 1})
    token = _draft_context.set(initial["draft"])
    try:
        updated = query_cd("predict", parameters={second: 2})
        assert updated["draft"]["parameters"] == {first: 1, second: 2}
        changed_year = query_cd("predict", year=2025, parameters={second: 3})
        assert changed_year["draft"]["parameters"] == {second: 3}
        changed_region = query_cd("predict", region_name="新地区", parameters={second: 4})
        assert changed_region["draft"]["parameters"] == {second: 4}
    finally:
        _draft_context.reset(token)


def test_parameter_query_forwards_parcel_year_and_returns_definitions(monkeypatch):
    from framework.domain.other_models import heavy_metal_cd_db

    def read_parcel(parcel_id, model_id, *, year):
        return {"data": {}, "missing_fields": ["solution"], "year": year}

    monkeypatch.setattr(heavy_metal_cd_db, "build_inputs", read_parcel)
    result = query_cd("parameters", model_id="crop_cd", parcel_id="P1", year=2024)
    assert result["parcel_parameters"]["year"] == 2024
    assert result["parameter_definitions"]["solution"]["unit"] == "无量纲"


def test_complete_prediction_requires_units_and_checks_ranges(monkeypatch):
    from framework.domain.other_models.cd_parameter_contract import FIELD_DEFINITIONS

    contract = next(item for item in heavy_metal_cd.available_models() if item["model_id"] == "crop_cd")
    parameters = dict.fromkeys(contract["input_fields"], 1.0)
    units = {field: FIELD_DEFINITIONS[field][1] for field in parameters}
    monkeypatch.setattr(heavy_metal_cd, "predict", lambda model_id, data: {"status": "success"})
    missing_units = query_cd("predict", model_id="crop_cd", parameters=parameters)
    assert set(missing_units["input_issues"]) == set(parameters)
    invalid = query_cd("predict", model_id="crop_cd", parameters={**parameters, "sand_fraction": 101},
                       parameter_units=units)
    assert set(invalid["input_issues"]) == {"sand_fraction"}
    valid = query_cd("predict", model_id="crop_cd", parameters=parameters, parameter_units=units)
    assert valid["status"] == "success"
    assert valid["model_version"] == contract["artifact_checksums"]


def test_failed_cd_tool_is_reported_as_service_unavailable(monkeypatch):
    from framework.agents.cd_conversation import answer_cd
    from framework.config import Config
    from framework.llm.service import llm_service

    monkeypatch.setattr(Config, "FUNCTION_CALLING_ENABLED", True)
    monkeypatch.setattr(llm_service, "generate_with_tools", lambda **kwargs: {
        "success": True, "content": "无数据", "tool_calls_trace": [{"success": False}],
    })
    result = answer_cd({"question": "查镉"}, None)
    assert result["model_results"]["models"]["cd_conversation"]["status"] == "service_unavailable"


def test_year_switch_reloads_only_matching_measured_parameters(monkeypatch):
    from framework.agents.cd_conversation import _draft_context
    from framework.domain.other_models import heavy_metal_cd_db

    def read_parcel(parcel_id, model_id, *, year):
        return {"status": "need_input", "data": {"available_phosphorus": year, "total_nitrogen": 1},
                "provenance": {"available_phosphorus": "measured", "total_nitrogen": "default"}}

    monkeypatch.setattr(heavy_metal_cd_db, "build_inputs", read_parcel)
    initial = query_cd("predict", model_id="crop_cd", parcel_id="P1", year=2024)
    token = _draft_context.set(initial["draft"])
    try:
        updated = query_cd("predict", parcel_id="P1", year=2025)
        assert updated["draft"]["parameters"] == {"available_phosphorus": 2025}
        assert updated["draft"]["parameter_sources"]["available_phosphorus"]["year"] == 2025
    finally:
        _draft_context.reset(token)
