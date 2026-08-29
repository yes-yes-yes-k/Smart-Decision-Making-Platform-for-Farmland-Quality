"""六个专题模型在 Schema 2.0 下的状态和数据来源矩阵。"""

import json

import pytest

from framework.agents.output_contract import normalize_execution, validate_result


MODEL_CASES = {
    "model-1": (
        "stability-risk-evaluation",
        {"region": "440281", "score": 0.8, "grade": "稳定", "modules": {"module_1": {"score": 0.8}}},
        {"region", "score", "grade", "modules"},
    ),
    "model-2": (
        "quality-grade-evaluation",
        {"quality_grade": "3等", "composite_index": 0.76, "indicators": [], "obstacle_degree": []},
        {"quality_grade", "composite_index", "indicators", "obstacle_degree"},
    ),
    "model-3": (
        "obstacle-diagnosis",
        {"obstacle_type": "酸化", "primary_factors": ["pH"], "secondary_factors": [], "obstacle_degrees": [], "obstacle_levels": [], "obstacle_combination": "pH"},
        {"obstacle_type", "primary_factors", "secondary_factors", "obstacle_degrees", "obstacle_levels", "obstacle_combination"},
    ),
    "model-4": (
        "acidification-remediation",
        {"acidification_level": "中度", "background_acid": 1.0, "acid_deposition_input": 2.0, "crop_acid_output": 3.0, "nitrogen_cycle_acid": 4.0, "agricultural_acid": 5.0, "soil_conditioner_dosage": 6.0, "woody_peat_dosage": 7.0, "sub_model": "upland"},
        {"acidification_level", "background_acid", "acid_deposition_input", "crop_acid_output", "nitrogen_cycle_acid", "agricultural_acid", "soil_conditioner_dosage", "woody_peat_dosage", "sub_model"},
    ),
    "model-5": (
        "organic-matter-improvement",
        {"soc_prediction": 20.1, "dose_prediction": 9.2, "soc_confidence": 0.91, "dose_confidence": 0.88, "region": "lechang", "land_type": "paddy", "imputed_features": []},
        {"soc_prediction", "dose_prediction", "soc_confidence", "dose_confidence", "region", "land_type", "imputed_features"},
    ),
}


def _agent(agent_id: str, model_id: str):
    return type(
        "SchemaAgent",
        (),
        {"agent_id": agent_id, "model_id": model_id, "capability": {"model_id": model_id}},
    )()


@pytest.mark.parametrize("agent_id", MODEL_CASES)
@pytest.mark.parametrize(
    "raw_status,simulated,expected_status",
    [
        ("ok", False, "ok"),
        ("ok", True, "degraded"),
        ("rejected", False, "rejected"),
        ("unavailable", False, "unavailable"),
        ("error", False, "error"),
    ],
)
def test_models_1_to_5_share_status_semantics(agent_id, raw_status, simulated, expected_status):
    model_id, raw_result, expected_fields = MODEL_CASES[agent_id]
    envelope = normalize_execution(
        _agent(agent_id, model_id),
        {"parcel_id": "P-1"},
        {
            "status": raw_status,
            "result": raw_result,
            "simulated": simulated,
            "data_source": "test-source",
        },
    )

    assert envelope["status"] == expected_status
    assert validate_result(envelope)[0]
    if expected_status in {"ok", "degraded"}:
        assert set(envelope["result"]) == expected_fields
    else:
        assert envelope["result"] is None
    if expected_status == "ok":
        assert envelope["issues"] == []
    else:
        assert envelope["issues"]
    json.dumps(envelope, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize("agent_id", MODEL_CASES)
def test_models_1_to_5_keep_result_fields_stable_across_sources(agent_id):
    model_id, raw_result, expected_fields = MODEL_CASES[agent_id]
    agent = _agent(agent_id, model_id)

    database = normalize_execution(
        agent,
        {"parcel_id": "P-1"},
        {"status": "ok", "result": raw_result, "data_source": "database"},
    )
    file_result = normalize_execution(
        agent,
        {"parcel_id": "P-1"},
        {"status": "ok", "result": raw_result, "data_source": "csv"},
    )

    assert set(database["result"]) == set(file_result["result"]) == expected_fields
    assert database["meta"]["data_source"] == "database"
    assert file_result["meta"]["data_source"] == "csv"


def test_model_6_is_explicitly_unavailable_for_every_execution_shape():
    agent = _agent("model-6", "comprehensive-fertility-improvement")

    for execution in (
        {"status": "ok", "result": {"stub": True}},
        {"status": "degraded", "result": {}},
        {"status": "error", "error": "boom"},
    ):
        envelope = normalize_execution(agent, {"parcel_id": "P-6"}, execution)
        assert envelope["status"] == "unavailable"
        assert envelope["result"] is None
        assert envelope["meta"]["data_source"] == "stub"
        assert envelope["meta"]["simulated"] is True
        assert [issue["code"] for issue in envelope["issues"]] == ["MODEL_NOT_IMPLEMENTED"]
        assert validate_result(envelope)[0]
