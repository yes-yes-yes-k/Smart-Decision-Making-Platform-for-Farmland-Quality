from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from framework.api.routes import acidification_rf as routes


def _client():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="acidification-rf-test-secret-at-least-32-bytes",
    )
    JWTManager(app)
    app.register_blueprint(routes.acidification_rf_bp, url_prefix="/rf")
    with app.app_context():
        token = create_access_token(identity="7")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_requires_authentication():
    client, _headers = _client()
    assert client.get("/rf/models").status_code == 401
    assert client.post("/rf/predict", json={}).status_code == 401


def test_models_lists_shipped_manifests():
    client, headers = _client()
    response = client.get("/rf/models", headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert [(m["model_id"], m["data_type"], m["land_type"]) for m in payload["models"]] == [
        (33, "reduce", "dryland"),
        (35, "reflux", "dryland"),
        (38, "reflux", "paddy_field"),
    ]


def test_predict_reduce_returns_converted_result():
    client, headers = _client()
    response = client.post(
        "/rf/predict",
        json={
            "model_id": 33,
            "data": {"init_pH": 5, "target_pH": 6, "H": 1, "Al": 2, "OM": 3,
                     "NO3": 4, "NH4": 5, "CEC": 6},
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "success"
    assert body["predictions"][0]["unit"] == "t/mu"


def test_predict_partial_input_is_degraded():
    client, headers = _client()
    response = client.post(
        "/rf/predict",
        json={
            "model_id": 35,
            "data": [
                {"H": 1, "Al": 2, "OM": 3, "NO3": 4, "NH4": 5, "CEC": 6},
                {"H": 2, "Al": 3, "OM": None, "NO3": 5, "NH4": 6, "CEC": 7},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "degraded"
    assert body["imputed_fields"] == ["OM"]


def test_predict_missing_data_is_400():
    client, headers = _client()
    assert client.post("/rf/predict", json={"model_id": 33}, headers=headers).status_code == 400
    assert client.post(
        "/rf/predict", json={"model_id": "abc", "data": {}}, headers=headers
    ).status_code == 400


def test_parcel_prefill_returns_provenance_and_missing(monkeypatch):
    from framework.domain.data import parcel_data_accessor as pda

    snapshot = pda.ParcelDataSnapshot(
        parcel_id="1894",
        area_code="lechang",
        parcel_code=None,
        land_type="paddy",
        fertilizer_type="urea",
        target_ph=None,
        indicators={
            "soil_ph": 5.31, "organic_matter": 30.0,
            "exchangeable_hydrogen": 0.295, "exchangeable_aluminum": 4.026,
            "cation_exchange_capacity": 11.18,
            "provenance": {
                "soil_ph": "measured", "organic_matter": "measured",
                "exchangeable_hydrogen": "region_mean_backfill",
                "exchangeable_aluminum": "region_mean_backfill",
                "cation_exchange_capacity": "region_mean_backfill",
            },
        },
        source_version="parcel:x",
    )
    monkeypatch.setattr(pda.ParcelDataAccessor, "get_parcel_snapshot", lambda self, pid: snapshot)

    client, headers = _client()
    response = client.get("/rf/parcels/1894/prefill", headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["parcel_id"] == "1894"
    assert body["model_id"] == 38
    assert body["status"] == "need_input"
    assert "FeO" in body["missing_fields"]
    assert body["provenance"]["OM"] == "measured"
    assert body["provenance"]["CEC"] == "region_mean_backfill"


def test_parcel_prefill_404_when_missing(monkeypatch):
    from framework.domain.data import parcel_data_accessor as pda

    monkeypatch.setattr(pda.ParcelDataAccessor, "get_parcel_snapshot", lambda self, pid: None)
    client, headers = _client()
    response = client.get("/rf/parcels/NOPE/prefill", headers=headers)
    assert response.status_code == 404
    assert response.get_json()["reason"] == "parcel_not_found"


def test_parcel_prefill_rejects_reflux_land_type_mismatch(monkeypatch):
    from framework.domain.data import parcel_data_accessor as pda

    snapshot = pda.ParcelDataSnapshot("1", None, None, "paddy", None, None,
                                      {"soil_ph": 5.4, "provenance": {}}, "parcel:x")
    monkeypatch.setattr(pda.ParcelDataAccessor, "get_parcel_snapshot", lambda self, pid: snapshot)

    client, headers = _client()
    # 水田地块 + 旱地 reflux 模型 35 → land_type_mismatch
    response = client.get("/rf/parcels/1/prefill?model_id=35", headers=headers)
    assert response.status_code == 400
    assert response.get_json()["reason"] == "land_type_mismatch"


def test_parcel_prefill_allows_reduce_for_paddy(monkeypatch):
    from framework.domain.data import parcel_data_accessor as pda

    snapshot = pda.ParcelDataSnapshot("1", None, None, "paddy", None, None,
                                      {"soil_ph": 5.4, "provenance": {}}, "parcel:x")
    monkeypatch.setattr(pda.ParcelDataAccessor, "get_parcel_snapshot", lambda self, pid: snapshot)

    client, headers = _client()
    # 旧系统语义：水田降酸使用旱地 reduce 模型 33，prefill 应放行
    response = client.get("/rf/parcels/1/prefill?model_id=33", headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["model_id"] == 33
    assert body["data_type"] == "reduce"


def test_predict_with_assumptions_is_degraded():
    client, headers = _client()
    response = client.post(
        "/rf/predict",
        json={
            "model_id": 35,
            "data": {"H": 1, "Al": 2, "OM": 3, "NO3": 31.24, "NH4": 5.13, "CEC": 6},
            "assumptions": {"NO3": "training_median", "NH4": "training_median"},
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "degraded"
    assert body["assumed_fields"] == {"NO3": "training_median", "NH4": "training_median"}


def test_predict_invalid_assumptions_is_400():
    client, headers = _client()
    response = client.post(
        "/rf/predict",
        json={"model_id": 35, "data": {"H": 1}, "assumptions": ["NO3"]},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.get_json()["reason"] == "invalid_assumptions"


def test_parcel_prefill_includes_suggestions(monkeypatch):
    from framework.domain.data import parcel_data_accessor as pda

    snapshot = pda.ParcelDataSnapshot(
        "3291", "lechang", None, "upland", "urea", None,
        {"soil_ph": 5.4, "organic_matter": 37.6,
         "exchangeable_hydrogen": 0.2949, "exchangeable_aluminum": 4.0262,
         "cation_exchange_capacity": 11.1782,
         "provenance": {"soil_ph": "measured", "organic_matter": "measured",
                        "exchangeable_hydrogen": "region_mean_backfill",
                        "exchangeable_aluminum": "region_mean_backfill",
                        "cation_exchange_capacity": "region_mean_backfill"}},
        "parcel:x",
    )
    monkeypatch.setattr(pda.ParcelDataAccessor, "get_parcel_snapshot", lambda self, pid: snapshot)

    client, headers = _client()
    body = client.get("/rf/parcels/3291/prefill", headers=headers).get_json()
    assert body["suggestions"]["NO3"]["value"] == 31.24
    assert body["suggestions"]["NO3"]["basis"] == "training_median"
    assert body["suggestions"]["NH4"]["dataset"] == "dataset_81"


def test_predict_unknown_model_is_500_class_not_400(monkeypatch):
    def _unavailable(model_id, data, assumptions=None):
        return {"status": "rejected", "reason": "model_unavailable",
                "model_id": model_id, "predictions": []}

    monkeypatch.setattr(routes.acidification_rf, "predict", _unavailable)
    client, headers = _client()
    response = client.post("/rf/predict", json={"model_id": 99, "data": {}}, headers=headers)
    assert response.status_code == 503
    assert response.get_json()["reason"] == "model_unavailable"
