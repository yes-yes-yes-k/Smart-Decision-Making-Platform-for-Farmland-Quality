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
