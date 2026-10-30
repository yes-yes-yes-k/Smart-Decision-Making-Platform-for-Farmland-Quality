import json
import math

from framework.agents.output_contract import (
    chat_compact,
    legacy_projection,
    llm_context,
    normalize_execution,
    sanitize_json,
    validate_result,
)


class _Agent:
    model_id = "model-2"
    agent_id = "model-2"
    capability = {"model_id": "quality-grade-evaluation"}


def test_normalize_execution_has_stable_envelope():
    result = normalize_execution(
        _Agent(),
        {"parcel_code": "P-1", "area_code": "440281"},
        {
            "status": "ok",
            "result": {
                "quality_grade": "一等",
                "composite_index": 0.88,
                "indicators": {"pH": 6.2},
                "obstacle_degree": [],
            },
            "data_source": "db",
            "simulated": False,
        },
    )
    assert set(result) == {"model_id", "status", "subject", "result", "meta", "issues"}
    assert result["model_id"] == "quality-grade-evaluation"
    assert result["subject"] == {"type": "parcel", "id": "P-1"}
    assert result["meta"]["data_source"] == "db"
    assert validate_result(result)[0]


def test_normalize_execution_exposes_shared_calculation_identity():
    result = normalize_execution(
        _Agent(),
        {"parcel_id": "P-1"},
        {
            "status": "ok",
            "result": {"quality_grade": "8", "composite_index": 0.7531},
            "versioned_result": {
                "resultId": 42,
                "modelVersion": "quality-grade-2.1.0",
                "coefficientVersion": "shaoguan-model2-2026.10.13",
                "inputHash": "abc123",
                "calculatedAt": "2026-10-13T01:02:03+00:00",
            },
        },
    )

    assert result["meta"]["calculation_result_id"] == 42
    assert result["meta"]["model_version"] == "quality-grade-2.1.0"
    assert result["meta"]["input_hash"] == "abc123"


def test_model6_is_unavailable():
    agent = type("Agent", (), {
        "model_id": "model-6",
        "agent_id": "model-6",
        "capability": {"model_id": "comprehensive-fertility-improvement"},
    })()
    result = normalize_execution(agent, {"parcel_id": "1"}, {"status": "ok", "result": {"stub": True}})
    assert result["status"] == "unavailable"
    assert result["result"] is None
    assert result["issues"][0]["code"] == "MODEL_NOT_IMPLEMENTED"


def test_sanitize_non_finite_and_strict_json():
    issues = []
    value = sanitize_json({"a": math.nan, "b": [math.inf, -math.inf]}, issues)
    assert value == {"a": None, "b": [None, None]}
    assert len(issues) == 3
    json.dumps(value, allow_nan=False)


def test_projections_do_not_expose_internal_details():
    model = normalize_execution(_Agent(), {"parcel_code": "P-1"}, {"status": "ok", "result": {"quality_grade": "一等"}, "data_source": "csv"})
    compact = chat_compact(model)
    context = llm_context(model)
    legacy = legacy_projection(model)
    assert "details" not in compact
    assert "details" not in context
    assert legacy["analysis"]["quality_grade"] == "一等"


def test_model5_database_dose_only_result_is_complete_for_db_capability():
    agent = type("Agent", (), {
        "model_id":"organic-matter-improvement",
        "agent_id":"model-5",
        "capability":{"model_id":"organic-matter-improvement"},
    })()
    result = normalize_execution(
        agent,
        {"parcel_id":"4190", "land_type":"upland"},
        {
            "status":"ok", "data_source":"rf_model", "simulated":False,
            "model_version":"upland-dose-test-v1",
            "result":{"parcel_id":"4190", "dose":223.7, "model_version":"upland-dose-test-v1"},
        },
    )
    assert result["status"] == "ok"
    assert result["result"]["dose_prediction"] == 223.7
    assert result["result"]["dose"] == 223.7
    assert result["result"]["manure_dosage"] == 223.7
    assert result["result"]["potential_increase"] is None
    assert not result["issues"]


def test_model5_ml_partial_result_still_reports_missing_predictions():
    agent = type("Agent", (), {
        "model_id":"organic-matter-improvement",
        "agent_id":"model-5",
        "capability":{"model_id":"organic-matter-improvement"},
    })()
    result = normalize_execution(
        agent,
        {"parcel_id":"4190", "land_type":"upland"},
        {
            "status":"ok", "data_source":"global_etr", "simulated":False,
            "model_version":"global-test-v1",
            "result":{"parcel_id":"4190", "dose_prediction":223.7, "model_version":"global-test-v1"},
        },
    )
    assert result["status"] == "degraded"
    assert result["issues"][0]["code"] == "PARTIAL_PREDICTION"


def test_model5_untrusted_aliases_are_cleared_in_every_projection():
    agent = type("Agent", (), {
        "model_id": "organic-matter-improvement",
        "agent_id": "model-5",
        "capability": {"model_id": "organic-matter-improvement"},
    })()
    model = normalize_execution(
        agent,
        {"parcel_id": "P-1"},
        {
            "status": "degraded",
            "data_source": "rule_fallback",
            "simulated": True,
            "result": {"manure_dosage": 1000.0, "potential_increase": 1.5, "dose": 135.0},
        },
    )
    assert model["status"] == "degraded"
    assert "MODEL5_QUANTITATIVE_UNAVAILABLE" in {item["code"] for item in model["issues"]}
    for projected in (model, chat_compact(model), llm_context(model)):
        result = projected["result"]
        assert result.get("dose_prediction") is None
        assert result.get("dose") is None
        assert result.get("manure_dosage") is None
        assert result.get("potential_increase") is None
    legacy = legacy_projection(model)
    assert legacy["evidence"]["dose_prediction"] is None
    assert legacy["deprecation"]["code"] == "MODEL5_QUANTITATIVE_UNAVAILABLE"
