from __future__ import annotations

from flask import Flask

from framework.agents.base import BaseAgent
from framework.domain.assessment.versioned_results import MODEL_RUNTIME_VERSIONS
from framework.models import ParcelInfo, VersionedModelResult, db


class _GradeCalculationAgent(BaseAgent):
    def __init__(self):
        super().__init__("test", "test", "quality-grade-evaluation", "grade")
        self.calls = 0

    def execute(self, task):
        self.calls += 1
        return {
            "status": "ok",
            "result": {
                "parcel_id": task["parcel_id"],
                "quality_grade": "8",
                "composite_index": 0.7531,
                "call": self.calls,
            },
        }

    def answer_question(self, question, context):
        return {}


def _app():
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    return app


def test_all_six_models_have_explicit_runtime_versions():
    assert set(MODEL_RUNTIME_VERSIONS) == {f"model-{number}" for number in range(1, 7)}
    assert all(version != "unknown" for version in MODEL_RUNTIME_VERSIONS.values())


def test_repeated_execution_reads_the_same_versioned_row():
    app = _app()
    with app.app_context():
        ParcelInfo.__table__.create(db.engine)
        VersionedModelResult.__table__.create(db.engine)
        db.session.add(ParcelInfo(
            parcel_id="P-1",
            area_code="440205",
            soil_indicators={"soil_ph": 5.5},
        ))
        db.session.commit()

        agent = _GradeCalculationAgent()
        first = agent.execute({"parcel_id": "P-1", "area_code": "440205"})
        # Different consumers may or may not carry area_code; the authoritative
        # parcel row must still produce the same identity.
        second = agent.execute({"parcel_id": "P-1"})

        assert agent.calls == 1
        assert first["result"] == second["result"]
        assert first["versioned_result"]["resultId"] == second["versioned_result"]["resultId"]
        assert first["versioned_result"]["cacheHit"] is False
        assert second["versioned_result"]["cacheHit"] is True
        assert VersionedModelResult.query.filter_by(is_current=True).count() == 1


def test_changed_authoritative_input_publishes_a_new_current_row():
    app = _app()
    with app.app_context():
        ParcelInfo.__table__.create(db.engine)
        VersionedModelResult.__table__.create(db.engine)
        parcel = ParcelInfo(
            parcel_id="P-1",
            area_code="440205",
            soil_indicators={"soil_ph": 5.5},
        )
        db.session.add(parcel)
        db.session.commit()

        agent = _GradeCalculationAgent()
        first = agent.execute({"parcel_id": "P-1"})
        parcel.soil_indicators = {"soil_ph": 6.2}
        db.session.commit()
        second = agent.execute({"parcel_id": "P-1"})

        assert agent.calls == 2
        assert first["versioned_result"]["inputHash"] != second["versioned_result"]["inputHash"]
        assert VersionedModelResult.query.count() == 2
        current = VersionedModelResult.query.filter_by(is_current=True).one()
        assert current.id == second["versioned_result"]["resultId"]
