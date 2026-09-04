"""专题模型、聊天序列化和兼容投影的 Schema 2.0 验收测试。"""
import json
import pytest

from framework.agents.output_contract import (
    LEGACY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    normalize_execution,
    validate_result,
)
from framework.api.routes.chat import _serialize_chat_response


class _Agent:
    agent_id = "model-1"
    model_id = "stability-risk-evaluation"
    capability = {"model_id": "stability-risk-evaluation"}


def test_zero_values_and_all_results_are_normalized_without_duplicates():
    result = normalize_execution(
        _Agent(),
        {"parcel_id": "P-1"},
        {
            "status": "ok",
            "data_source": "precomputed",
            "result": {
                "score": 0,
                "grade": "10",
                "all_results": {"module_1": {"SAFE_ABS": 0}},
            },
        },
    )
    assert result["result"]["score"] == 0
    assert "all_results" not in result["result"]
    assert result["result"]["modules"]["module_1"]["SAFE_ABS"] == 0
    assert validate_result(result)[0]
    json.dumps(result, allow_nan=False)


def test_chat_serializer_has_single_routing_and_optional_models():
    model = normalize_execution(
        type("A", (), {"agent_id": "model-2", "model_id": "quality-grade-evaluation", "capability": {"model_id": "quality-grade-evaluation"}})(),
        {"parcel_code": "P-2"},
        {"status": "ok", "result": {"quality_grade": "一等", "composite_index": 0.0}, "data_source": "csv"},
    )
    result = {"status": "ok", "question_type": 2, "answer": "已完成", "sources": [], "recommendations": [], "models": {"model-2": model}, "trace_id": "t-1"}
    compact = _serialize_chat_response(result, 7)
    assert compact["schema_version"] == SCHEMA_VERSION
    assert set(compact["data"]) == {"message_id", "answer", "sources", "recommendations", "routing"}
    expanded = _serialize_chat_response(result, 7, include_model_results=True)
    assert "models" in expanded["data"]
    assert "details" not in json.dumps(expanded, ensure_ascii=False)
    legacy = _serialize_chat_response(result, 7, include_model_results=True, response_schema=LEGACY_SCHEMA_VERSION)
    assert legacy["schema_version"] == LEGACY_SCHEMA_VERSION
    assert "analysis" in legacy["data"]["models"]["model-2"]


@pytest.mark.parametrize("agent_id,model_id,raw_result", [
    ("model-1", "stability-risk-evaluation", {"region": "440281", "score": 0, "grade": "5", "modules": {"module_1": {"SAFE_ABS": 0}}}),
    ("model-2", "quality-grade-evaluation", {"quality_grade": "5", "composite_index": 0, "indicators": [], "obstacle_degree": []}),
    ("model-3", "obstacle-diagnosis", {"obstacle_type": "无明显障碍", "primary_factors": [], "secondary_factors": [], "obstacle_degrees": {}, "obstacle_levels": {}, "obstacle_combination": None}),
    ("model-4", "acidification-remediation", {"acidification_level": "中", "background_acid": 0, "acid_deposition_input": 0, "crop_acid_output": 0, "nitrogen_cycle_acid": 0, "agricultural_acid": 0, "soil_conditioner_dosage": 0, "woody_peat_dosage": 0, "sub_model": "upland_compound"}),
    ("model-5", "organic-matter-improvement", {"soc_prediction": 0, "dose_prediction": 0, "soc_confidence": 0, "dose_confidence": 0, "region": "global", "land_type": None, "imputed_features": []}),
    ("model-6", "comprehensive-fertility-improvement", None),
])
def test_all_formal_models_have_strict_public_envelope(agent_id, model_id, raw_result):
    agent = type("Agent", (), {"agent_id": agent_id, "model_id": model_id, "capability": {"model_id": model_id}})()
    envelope = normalize_execution(agent, {"parcel_id": "P"}, {"status": "ok", "result": raw_result, "data_source": "test"})
    assert set(envelope) == {"model_id", "status", "subject", "result", "meta", "issues"}
    assert validate_result(envelope)[0]
    assert all(key not in envelope for key in ("model", "capability", "analysis", "evidence", "findings", "reliability", "fallback", "degraded"))
    json.dumps(envelope, ensure_ascii=False, allow_nan=False)


def test_schema_projection_reduces_model1_payload_and_preserves_result():
    modules = {f"module_{i}": {"score": i, "diagnostic": "x" * 100} for i in range(1, 10)}
    envelope = normalize_execution(_Agent(), {"parcel_id": "P"}, {"status": "ok", "result": {"score": 0.7, "modules": modules}, "data_source": "precomputed"})
    from framework.agents.output_contract import chat_compact, legacy_projection
    compact = chat_compact(envelope)
    legacy = legacy_projection(envelope)
    assert len(json.dumps(compact, ensure_ascii=False)) < len(json.dumps(legacy, ensure_ascii=False))
    assert compact["result"]["score"] == envelope["result"]["score"]


def test_legacy_switch_does_not_change_model_result():
    from framework.agents.output_contract import legacy_projection, public_full
    envelope = normalize_execution(
        _Agent(), {"parcel_id": "P"},
        {"status": "ok", "result": {"score": 0.5, "grade": "5", "modules": {}}, "data_source": "precomputed"},
    )
    legacy = legacy_projection(envelope)
    assert legacy["evidence"] == public_full(envelope)["result"]
