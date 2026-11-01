from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from framework.api.routes import farmland_statistics as routes


def _client():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="farmland-statistics-test-secret-at-least-32-bytes",
    )
    JWTManager(app)
    app.register_blueprint(routes.farmland_statistics_bp, url_prefix="/stats")
    with app.app_context():
        token = create_access_token(identity="7")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_metrics_requires_authentication():
    client, _headers = _client()
    assert client.get("/stats/metrics").status_code == 401


def test_aggregate_returns_service_payload(monkeypatch):
    client, headers = _client()
    monkeypatch.setattr(routes, "aggregate_statistics", lambda body: {"received": body})
    response = client.post(
        "/stats/aggregate",
        json={"scope": {"type": "viewport", "bbox": [113, 24, 114, 25]}},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["received"]["scope"]["type"] == "viewport"


def test_service_error_preserves_code_and_status(monkeypatch):
    client, headers = _client()
    monkeypatch.setattr(
        routes,
        "get_parcel_summary",
        lambda _parcel_id: (_ for _ in ()).throw(
            routes.StatisticsError("parcel_not_found", "地块不存在", 404)
        ),
    )
    response = client.get("/stats/parcels/missing", headers=headers)
    assert response.status_code == 404
    assert response.get_json()["code"] == "parcel_not_found"


def test_parcel_summary_exposes_area_in_mu(monkeypatch):
    client, headers = _client()
    monkeypatch.setattr(
        routes,
        "get_parcel_summary",
        lambda _parcel_id: {"parcelId": "1007", "areaMu": 379.8501},
    )

    response = client.get("/stats/parcels/1007", headers=headers)

    assert response.status_code == 200
    assert response.get_json()["data"]["areaMu"] == 379.8501


def test_boundaries_forwards_map_filters(monkeypatch):
    client, headers = _client()
    received = {}

    def fake_list_boundaries(**kwargs):
        received.update(kwargs)
        return {"type": "FeatureCollection", "features": []}

    monkeypatch.setattr(routes, "list_boundaries", fake_list_boundaries)

    response = client.get(
        "/stats/boundaries?region_type=township&parent_type=county&parent_id=440281"
        "&bbox=112,24,114,26&zoom=10",
        headers=headers,
    )

    assert response.status_code == 200
    assert received == {
        "region_type": "township",
        "parent_type": "county",
        "parent_id": "440281",
        "bbox": "112,24,114,26",
        "zoom": "10",
    }


def test_pick_forwards_metric_and_tolerance(monkeypatch):
    client, headers = _client()
    received = {}

    def fake_pick(longitude, latitude, **kwargs):
        received.update(longitude=longitude, latitude=latitude, **kwargs)
        return {"parcelId": "P1"}

    monkeypatch.setattr(routes, "pick_parcel", fake_pick)

    response = client.post(
        "/stats/parcels/pick",
        json={
            "longitude": 113.1,
            "latitude": 24.9,
            "metric": "soil_ph",
            "toleranceMeters": 8,
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert received == {
        "longitude": 113.1,
        "latitude": 24.9,
        "metric_key": "soil_ph",
        "tolerance_meters": 8,
    }


def test_viewport_parcels_forwards_query_parameters(monkeypatch):
    client, headers = _client()
    received = {}

    def fake_viewport(**kwargs):
        received.update(kwargs)
        return {"type": "FeatureCollection", "features": []}

    monkeypatch.setattr(routes, "list_viewport_parcels", fake_viewport)

    response = client.get(
        "/stats/parcels/viewport?bbox=112,24,114,26&metric=organic_matter"
        "&geometry=simplified&zoom=14&limit=500",
        headers=headers,
    )

    assert response.status_code == 200
    assert received == {
        "bbox": "112,24,114,26",
        "metric_key": "organic_matter",
        "geometry_mode": "simplified",
        "zoom": "14",
        "limit": "500",
    }


def test_quality_audit_returns_service_payload(monkeypatch):
    client, headers = _client()
    monkeypatch.setattr(routes, "indicator_quality_audit", lambda: {"parcelCount": 5488})

    response = client.get("/stats/quality/audit", headers=headers)

    assert response.status_code == 200
    assert response.get_json()["data"]["parcelCount"] == 5488


def test_pick_rate_limit_returns_429_and_retry_after(monkeypatch):
    client, headers = _client()
    monkeypatch.setattr(routes._PICK_LIMITER, "allow", lambda _key: False)

    response = client.post(
        "/stats/parcels/pick",
        json={"longitude": 113.1, "latitude": 24.9},
        headers=headers,
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"
    assert response.get_json()["code"] == "rate_limited"


def test_years_endpoint_returns_selectable_years(monkeypatch):
    client, headers = _client()
    monkeypatch.setattr(routes, "list_available_years", lambda: {
        "years": [{"year": 2024, "parcelCount": 5488, "selectable": True}],
        "defaultYear": 2024,
    })
    response = client.get("/stats/years", headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["defaultYear"] == 2024


def test_parcel_query_uses_same_scope_contract(monkeypatch):
    client, headers = _client()
    monkeypatch.setattr(routes, "query_parcels", lambda body: {
        "scope": body["scope"], "dataYear": body["year"], "items": [],
    })
    body = {
        "scope": {"type": "viewport", "bbox": [113, 24, 114, 25]},
        "year": 2024,
        "metrics": ["soil_ph"],
    }
    response = client.post("/stats/parcels/query", json=body, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["scope"] == body["scope"]


def test_parcel_detail_forwards_selected_year(monkeypatch):
    client, headers = _client()
    captured = {}

    def fake_summary(parcel_id, *, year, metric_key):
        captured.update(parcel_id=parcel_id, year=year, metric_key=metric_key)
        return {"parcelId": parcel_id, "dataYear": int(year)}

    monkeypatch.setattr(routes, "get_parcel_summary", fake_summary)
    response = client.get("/stats/parcels/1007?year=2021", headers=headers)
    assert response.status_code == 200
    assert captured == {"parcel_id": "1007", "year": "2021", "metric_key": None}
