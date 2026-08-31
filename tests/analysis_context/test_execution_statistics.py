from datetime import date, datetime, timezone

import pytest
from flask import Flask
from sqlalchemy import inspect

from framework.models import ModelExecutionLog, ThematicModelRegistry, db
from framework.observability.analysis_context_metrics import query_execution_statistics


@pytest.fixture
def statistics_app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.add(ThematicModelRegistry(
            agent_id="model-4", model_id="acidification-remediation", name="酸化改良",
            domain="acidification", question_type=4, analysis_scale="地块", data_type="处方用量",
        ))
        for trace_id, area_code, object_type, status, started_at in (
            ("t1", "440281", "parcel", "ok", datetime(2026, 8, 10, tzinfo=timezone.utc)),
            ("t2", "440281", "parcel", "ok", datetime(2026, 8, 20, tzinfo=timezone.utc)),
            ("t3", "440282", "parcel", "error", datetime(2026, 8, 20, tzinfo=timezone.utc)),
            ("t4", "440281", "county", "ok", datetime(2026, 8, 20, tzinfo=timezone.utc)),
            ("t5", "440281", "parcel", "ok", datetime(2026, 9, 1, tzinfo=timezone.utc)),
        ):
            db.session.add(ModelExecutionLog(
                trace_id=trace_id, agent_id="model-4", question_type=4,
                area_code=area_code, analysis_object_type=object_type,
                status=status, started_at=started_at,
            ))
        db.session.commit()
    yield app


def test_execution_statistics_group_by_area_model_and_status(statistics_app):
    with statistics_app.app_context():
        rows = query_execution_statistics(
            object_type="parcel", area_code="440281",
            date_from=date(2026, 8, 1), date_to=date(2026, 8, 31),
        )
        assert rows == [{
            "area_code": "440281", "agent_id": "model-4", "status": "ok", "count": 2,
        }]


def test_execution_statistics_indexes_and_query_source(statistics_app):
    with statistics_app.app_context():
        index_names = {
            item["name"] for item in inspect(db.engine).get_indexes("model_execution_log")
        }
        assert {
            "idx_model_execution_log_object",
            "idx_model_execution_log_area_agent_status",
            "idx_model_execution_log_agent_id",
            "idx_model_execution_log_started_at",
        }.issubset(index_names)
        sql = str(db.session.query(
            ModelExecutionLog.area_code, ModelExecutionLog.agent_id,
        ).statement).lower()
        assert "model_execution_log" in sql
        assert "kb_conversation" not in sql
