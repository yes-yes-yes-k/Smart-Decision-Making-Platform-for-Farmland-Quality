"""model-5 有机质培肥 ML 接入验收测试。"""

from pathlib import Path

import pytest


PYTHON_FEATURES = {
    "pH": 6.2,
    "SOCbe": 22.0,
    "TN": 1.1,
    "TP": 0.8,
    "TK": 18.0,
    "AP": 25.0,
    "AK": 80.0,
    "Gap": 5.0,
    "Fertilizer type": 1,
}

EXTERNAL_FEATURES = {
    "SJD": 6.2,
    "YJZ": 22.0,
    "TD": 1.1,
    "TL": 0.8,
    "TJ": 18.0,
    "YXL": 25.0,
    "SXJ": 80.0,
    "YJZTSZ": 5.0,
    "YJFLX": 1,
}


def test_model5_is_the_only_fertility_engine_entrypoint():
    from framework.domain.other_models import model_5_execution
    import framework.domain.other_models as other_models

    assert callable(model_5_execution)
    assert not hasattr(other_models, "model_6_execution")
    assert not (Path(__file__).parents[1] / "framework/domain/other_models/model_6.py").exists()


def test_external_fields_and_sombe_are_normalized():
    from framework.domain.other_models.model_5 import _normalize_input

    normalized = _normalize_input({**EXTERNAL_FEATURES, "SOMbe": 22.0})
    assert normalized == {
        "pH": 6.2,
        "SOCbe": 22.0,
        "TN": 1.1,
        "TP": 0.8,
        "TK": 18.0,
        "AP": 25.0,
        "AK": 80.0,
        "Gap": 5.0,
        "Fertilizer type": 1,
    }


def test_external_and_standard_conflict_is_rejected():
    from framework.domain.other_models.model_5 import model_5_execution

    result = model_5_execution({**EXTERNAL_FEATURES, "SOCbe": 18.0})
    assert result["status"] == "rejected"
    assert result["reason"] == "input_conflict"
    assert result["model_id"] == "model-5"


def test_model5_global_and_shaoguan_paths_return_real_metadata():
    from framework.domain.other_models.model_5 import model_5_execution

    global_result = model_5_execution({**PYTHON_FEATURES, "area_code": "other"})
    upland_result = model_5_execution({**PYTHON_FEATURES, "area_code": "lechang"}, land_type="upland")
    paddy_result = model_5_execution({**PYTHON_FEATURES, "area_code": "lechang"}, land_type="paddy")

    for result in (global_result, upland_result, paddy_result):
        assert result["status"] == "success"
        assert result["model_id"] == "model-5"
        assert result["simulated"] is False
        assert result["soc_prediction"] is not None
        assert result["dose_prediction"] is not None

    assert global_result["region"] == "global"
    assert global_result["land_type"] is None
    assert upland_result["model_version"] == "SG_RF_v2_20260804"
    assert upland_result["land_type"] == "upland"
    assert paddy_result["model_version"] == "SG_RF_v2_20260804"
    assert paddy_result["land_type"] == "paddy"


def test_model5_accepts_land_type_inside_input_and_imputes_missing_features():
    from framework.domain.other_models.model_5 import model_5_execution

    result = model_5_execution({"area_code": "lechang", "land_type": "paddy", "pH": 6.2})
    assert result["status"] == "success"
    assert result["land_type"] == "paddy"
    assert result["imputation_applied"] is True
    assert result["imputed_features"]


def test_model5_rejects_out_of_range_input():
    from framework.domain.other_models.model_5 import model_5_execution

    result = model_5_execution({**PYTHON_FEATURES, "pH": 99})
    assert result["status"] == "rejected"
    assert result["reason"] == "input_out_of_range"
    assert result["soc_prediction"] is None
    assert result["dose_prediction"] is None


def test_model5_dependency_unavailable_has_machine_readable_fallback(monkeypatch):
    import framework.domain.other_models.model_5 as model5

    monkeypatch.setattr(model5, "_SKLEARN_AVAILABLE", False)
    result = model5.model_5_execution({"pH": 6.2})
    assert result["status"] == "fallback"
    assert result["fallback_reason"] == "sklearn_missing"
    assert result["model_id"] == "model-5"
    assert result["simulated"] is True


def test_organic_agent_and_model_registry_keep_model6_placeholder():
    from framework.agents.manager import AgentManager, _StubAgent
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent

    manager = AgentManager()
    assert isinstance(manager.agents["model-5"], OrganicMatterAgent)
    assert isinstance(manager.agents["model-6"], _StubAgent)
    assert manager.agents["model-6"].capability["agent_id"] == "model-6"
    assert manager.agents["model-6"].capability["model_id"] == "comprehensive-fertility-improvement"
    assert manager.agents["model-6"].capability["name"] == "耕地综合地力改良提升模型"

    result = manager.agents["model-5"].execute({"area_code": "lechang", "land_type": "upland", **EXTERNAL_FEATURES})
    assert result["status"] == "success"
    assert result["result"]["model_id"] == "model-5"
    assert result["metadata"]["simulated"] is False


def test_model5_thematic_api_exposes_ml_metadata():
    from src.ai_culti_demo.thematic_models import run_thematic_model

    result = run_thematic_model({
        "model_id": "organic-matter-improvement",
        "area_code": "lechang",
        "land_type": "upland",
        **PYTHON_FEATURES,
    })
    assert result["status"] == "ok"
    assert result["model_id"] == "organic-matter-improvement"
    assert result["meta"]["model_version"] == "SG_RF_v2_20260804"
    assert result["meta"]["simulated"] is False
    assert result["result"]["dose_prediction"] is not None


def _authenticated_client():
    """创建带 JWT 的 Flask 测试客户端。"""
    from framework.api.app import create_app
    from framework.models.user import User, db
    from flask_jwt_extended import create_access_token

    app = create_app("sqlite")
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        username = "model5-integration-user"
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username, password="x")
            db.session.add(user)
            db.session.commit()
        token = create_access_token(identity=str(user.id))
    return app, {"Authorization": f"Bearer {token}"}


def test_model5_run_api_returns_public_model_and_version():
    app, headers = _authenticated_client()
    payload = {
        "model_id": "organic-matter-improvement",
        "area_code": "lechang",
        "land_type": "paddy",
        **EXTERNAL_FEATURES,
    }
    response = app.test_client().post("/api/v1/models/run", json=payload, headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["schema_version"] == "2.0"
    data = body["data"]
    assert data["model_id"] == "organic-matter-improvement"
    assert data["meta"]["model_version"] == "SG_RF_v2_20260804"
    assert data["meta"]["simulated"] is False
    assert data["result"]["dose_prediction"] is not None


def test_model5_run_api_exposes_input_conflict():
    app, headers = _authenticated_client()
    payload = {
        "model_id": "organic-matter-improvement",
        "area_code": "lechang",
        "land_type": "upland",
        **EXTERNAL_FEATURES,
        "SOCbe": 18.0,
    }
    response = app.test_client().post("/api/v1/models/run", json=payload, headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    data = body["data"]
    assert data["status"] == "rejected"
    assert data["result"] is None
    assert data["issues"][0]["code"] == "INPUT_CONFLICT"
    assert data["model_id"] == "organic-matter-improvement"


def test_chat_api_type5_transmits_top_level_fertility_fields():
    app, headers = _authenticated_client()
    payload = {
        "message": "有机肥每亩施用量多少？",
        "area_code": "lechang",
        "land_type": "upland",
        "include_model_results": True,
        **EXTERNAL_FEATURES,
    }
    response = app.test_client().post("/api/v1/chat/", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["routing"]["question_type"] == 5
    assert list(data["models"]) == ["model-5"]
    model_result = data["models"]["model-5"]
    assert model_result["model_id"] == "organic-matter-improvement"
    assert model_result["meta"]["model_version"] == "SG_RF_v2_20260804"
    assert model_result["meta"]["simulated"] is False


def test_type5_routes_model5_and_type6_routes_placeholder():
    from framework.agents.manager import AgentManager

    manager = AgentManager()
    type5 = manager.process(
        "有机肥每亩施用量多少？",
        {"question_type": 5, "area_code": "lechang", "land_type": "paddy", **PYTHON_FEATURES},
    )
    type6 = manager.process("显式占位模型请求", {"question_type": 6})

    assert list(type5["models"]) == ["model-5"]
    assert type5["models"]["model-5"]["model_id"] == "organic-matter-improvement"
    assert type5["models"]["model-5"]["result"]["dose_prediction"] is not None
    assert list(type6["models"]) == ["model-6"]
    placeholder = type6["models"]["model-6"]
    assert placeholder["status"] == "unavailable"
    assert placeholder["result"] is None
    assert placeholder["meta"]["simulated"] is True
    assert placeholder["issues"][0]["code"] == "MODEL_NOT_IMPLEMENTED"


@pytest.mark.parametrize("source", [EXTERNAL_FEATURES, PYTHON_FEATURES])
def test_model5_agent_handles_nested_indicator_payload(source):
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent

    result = OrganicMatterAgent().execute({
        "area_code": "lechang",
        "land_type": "upland",
        "indicators": source,
    })
    assert result["status"] == "success"
    assert result["result"]["model_id"] == "model-5"
