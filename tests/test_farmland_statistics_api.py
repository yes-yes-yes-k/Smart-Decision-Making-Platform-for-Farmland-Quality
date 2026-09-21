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


def test_years_endpoint_returns_selectable_years(monkeypatch):
    client, headers = _client()
    monkeypatch.setattr(routes, "list_available_years", lambda: {
        "years": [{"year": 2024, "parcelCount": 5488, "selectable": True}],
        "defaultYear": 2024,
    })
    response = client.get("/stats/years", headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["defaultYear"] == 2024


def test_boundary_endpoint_forwards_hierarchy_and_map_filters(monkeypatch):
    client, headers = _client()
    captured = {}

    def fake_boundaries(**kwargs):
        captured.update(kwargs)
        return {"type": "FeatureCollection", "features": []}

    monkeypatch.setattr(routes, "list_boundaries", fake_boundaries)
    response = client.get(
        "/stats/boundaries?region_type=township&parent_type=county&parent_id=440281&zoom=10",
        headers=headers,
    )
    assert response.status_code == 200
    assert captured == {
        "region_type": "township", "parent_type": "county", "parent_id": "440281",
        "bbox": None, "zoom": "10",
    }


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

    def fake_summary(parcel_id, *, year):
        captured.update(parcel_id=parcel_id, year=year)
        return {"parcelId": parcel_id, "dataYear": int(year)}

    monkeypatch.setattr(routes, "get_parcel_summary", fake_summary)
    response = client.get("/stats/parcels/1007?year=2021", headers=headers)
    assert response.status_code == 200
    assert captured == {"parcel_id": "1007", "year": "2021"}
