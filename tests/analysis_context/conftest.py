from datetime import datetime, timezone

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from framework.analysis_context.contracts import (
    AnalysisContext, AnalysisObject, CalculationMode, ObjectType,
)
from framework.analysis_context.service import ResolvedRequestContext
from framework.api.routes.chat import chat_bp
from framework.models import User, db


@pytest.fixture
def chat_app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY="task-9-test-secret-at-least-thirty-two-bytes",
    )
    JWTManager(app)
    db.init_app(app)
    app.register_blueprint(chat_bp, url_prefix="/api/v1/chat")
    with app.app_context():
        db.create_all()
        user = User(username="task9", password="x")
        db.session.add(user)
        db.session.commit()
        app.config["TASK9_USER_ID"] = user.id
        app.config["TASK9_TOKEN"] = create_access_token(identity=str(user.id))
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def auth_header(chat_app):
    return {"Authorization": f"Bearer {chat_app.config['TASK9_TOKEN']}"}


@pytest.fixture
def parcel_context():
    obj = AnalysisObject(
        type=ObjectType.PARCEL,
        id="P001",
        display_name="地块 P001",
        area_code="440281",
        parent_path=(),
        source="test",
        validated_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
    )
    return ResolvedRequestContext(
        context=AnalysisContext(CalculationMode.SPATIAL, 1, obj),
        validated_identifiers={"parcel_id": "P001", "parcel_code": "A0001"},
        deprecations=(),
        scenario_inputs={},
    )
