from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
import pytest

from framework.api.routes.acidification_measurements import acidification_measurements_bp
from framework.migrations.acidification_measurement import ensure_acidification_measurement_table
from framework.models import AcidificationMeasurement, Conversation, Message, db


@pytest.fixture
def records():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", JWT_SECRET_KEY="measurement-test-secret-key-32-bytes")
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(acidification_measurements_bp, url_prefix="/records")
    with app.app_context():
        for model in (Conversation, Message, AcidificationMeasurement):
            model.__table__.create(db.engine)
        db.session.add_all([Conversation(id=1, user_id=10), Conversation(id=2, user_id=20)])
        db.session.commit()
        token = create_access_token(identity="10")
        yield app.test_client(), {"Authorization": "Bearer " + token}
        db.session.remove()


def test_measurement_roundtrip_and_owner_boundary(records):
    client, headers = records
    payload = {"parcel_id": "P1", "mode": "prediction", "input_data": {"soil_ph": 5.2}, "source_info": {"source": "lab"}}
    created = client.post("/records/conversations/1/acidification-measurements", headers=headers, json=payload)
    assert created.status_code == 201
    record = created.get_json()["data"]
    assert record["source_info"] == payload["source_info"]
    assert record["status"] == "draft" and record["created_at"]
    assert client.get("/records/conversations/2/acidification-measurements", headers=headers).status_code == 404
    assert client.patch(f"/records/{record['id']}", headers=headers, json={"conversation_id": 2, "status": "completed", "result_data": {"ph": 5.5}}).status_code == 404
    updated = client.patch(f"/records/{record['id']}", headers=headers, json={"conversation_id": 1, "status": "completed", "result_data": {"ph": 5.5}})
    assert updated.status_code == 200
    loaded = client.get("/records/conversations/1/acidification-measurements", headers=headers).get_json()["data"]
    assert loaded[0]["status"] == "completed"
    assert loaded[0]["result_data"] == {"ph": 5.5}


def test_measurement_schema_upgrade_is_idempotent(records):
    with db.engine.begin() as connection:
        ensure_acidification_measurement_table(connection)
        ensure_acidification_measurement_table(connection)
    assert AcidificationMeasurement.query.count() == 0
