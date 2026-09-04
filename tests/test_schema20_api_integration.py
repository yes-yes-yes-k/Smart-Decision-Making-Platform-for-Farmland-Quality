"""专题模型 HTTP API 的 Schema 2.0/1.0 集成测试。"""

import pytest

from framework.agents.output_contract import normalize_execution


class _QualityAgent:
    agent_id = "model-2"
    model_id = "quality-grade-evaluation"
    capability = {"model_id": model_id}


def _model_result(status="ok"):
    execution = {
        "status": status,
        "result": {
            "quality_grade": "3等",
            "composite_index": 0.76,
            "indicators": [],
            "obstacle_degree": [],
        },
        "data_source": "csv",
    }
    return normalize_execution(_QualityAgent(), {"parcel_id": "P-2"}, execution)


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    from flask_jwt_extended import create_access_token
    from framework.api.app import create_app
    from framework.config import SQLiteConfig
    from framework.models.user import User, db

    monkeypatch.setattr(SQLiteConfig, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{(tmp_path / 'api.db').as_posix()}")
    monkeypatch.setattr(SQLiteConfig, "SQLALCHEMY_ENGINE_OPTIONS", {})
    app = create_app("sqlite")
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        user = User(username="schema20-api", password="x")
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
    yield app.test_client(), {"Authorization": f"Bearer {token}"}
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_models_run_defaults_to_schema_20(api_client, monkeypatch):
    client, headers = api_client
    monkeypatch.setattr(
        "framework.api.routes.models.core_engine.run_thematic_model",
        lambda payload: _model_result(),
    )

    response = client.post("/api/v1/models/run", json={"model_id": "quality-grade-evaluation"}, headers=headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["schema_version"] == "2.0"
    assert body["status"] == "ok"
    assert body["trace_id"]
    assert set(body["data"]) == {"model_id", "status", "subject", "result", "meta", "issues"}
    assert set(body["data"]["result"]) == {"quality_grade", "composite_index", "indicators", "obstacle_degree"}


def test_models_run_supports_schema_10_projection(api_client, monkeypatch):
    client, headers = api_client
    monkeypatch.setattr(
        "framework.api.routes.models.core_engine.run_thematic_model",
        lambda payload: _model_result(),
    )

    response = client.post(
        "/api/v1/models/run",
        json={"model_id": "quality-grade-evaluation", "response_schema": "1.0"},
        headers=headers,
    )

    body = response.get_json()
    assert body["schema_version"] == "1.0"
    assert body["deprecation"]["code"] == "SCHEMA_1_DEPRECATED"
    assert body["data"]["analysis"] == body["data"]["evidence"]
    assert body["data"]["analysis"]["quality_grade"] == "3等"


@pytest.mark.parametrize("business_status", ["rejected", "unavailable", "error"])
def test_models_run_keeps_business_failures_inside_data(api_client, monkeypatch, business_status):
    client, headers = api_client
    monkeypatch.setattr(
        "framework.api.routes.models.core_engine.run_thematic_model",
        lambda payload: _model_result(business_status),
    )

    response = client.post("/api/v1/models/run", json={"model_id": "quality-grade-evaluation"}, headers=headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["data"]["status"] == business_status
    assert body["data"]["result"] is None
    assert body["data"]["issues"]


@pytest.mark.parametrize(
    "payload,error_code",
    [
        ({}, "MISSING_MODEL_ID"),
        ({"model_id": "quality-grade-evaluation", "response_schema": "3.0"}, "INVALID_RESPONSE_SCHEMA"),
    ],
)
def test_models_run_rejects_http_parameter_errors_without_execution(api_client, monkeypatch, payload, error_code):
    client, headers = api_client

    def must_not_run(_payload):
        raise AssertionError("参数错误时不应执行模型")

    monkeypatch.setattr("framework.api.routes.models.core_engine.run_thematic_model", must_not_run)
    response = client.post("/api/v1/models/run", json=payload, headers=headers)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == error_code
