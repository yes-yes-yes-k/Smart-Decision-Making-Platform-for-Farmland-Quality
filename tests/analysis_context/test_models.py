from datetime import datetime, timezone

import sqlalchemy as sa
from flask import Flask

from framework.models import (
    AreaCodeRegionMap,
    Conversation,
    Message,
    ModelExecutionLog,
    ParcelInfo,
    SpatialRegionCatalog,
    ThematicModelRegistry,
    db,
)
from scripts.seed_spatial_region_catalog import seed_spatial_region_catalog


def _app():
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    return app


def test_analysis_context_schema_and_serialization():
    app = _app()
    with app.app_context():
        db.create_all()
        inspector = sa.inspect(db.engine)
        assert {"analysis_object", "context_version", "analysis_object_updated_at"} <= {
            column["name"] for column in inspector.get_columns("kb_conversation")
        }
        assert "analysis_context_snapshot" in {
            column["name"] for column in inspector.get_columns("kb_message")
        }
        assert inspector.has_table("spatial_region_catalog")
        assert "legacy_parcel_code" in {
            column["name"] for column in inspector.get_columns("parcel_info")
        }
        conversation = Conversation(user_id=1, analysis_object={"type": "parcel", "id": "P001"}, context_version=2)
        message = Message(
            conversation_id=1, role="user", content="x",
            analysis_context_snapshot={"mode": "spatial", "version": 1, "object": {"id": "P000"}},
        )
        assert conversation.to_dict()["analysis_context"]["version"] == 2
        assert message.to_dict()["analysis_context_snapshot"]["object"]["id"] == "P000"


def test_execution_log_accepts_two_agents_with_one_trace():
    app = _app()
    with app.app_context():
        db.create_all()
        for agent_id in ("model-1", "model-3"):
            db.session.add(ThematicModelRegistry(
                agent_id=agent_id, model_id=agent_id, name=agent_id, domain="soil",
                question_type=1, analysis_scale="parcel", data_type="result",
            ))
        db.session.commit()
        for agent_id in ("model-1", "model-3"):
            db.session.add(ModelExecutionLog(
                trace_id="trace-1", agent_id=agent_id, question_type=1, status="ok",
                started_at=datetime.now(timezone.utc), analysis_object_type="parcel",
                analysis_object_id="P001", area_code="440281", context_version=1,
            ))
        db.session.commit()
        assert ModelExecutionLog.query.filter_by(trace_id="trace-1").count() == 2
        columns = {column["name"] for column in sa.inspect(db.engine).get_columns("model_execution_log")}
        assert set((
            "analysis_object_type", "analysis_object_id", "area_code", "context_version",
            "analysis_context_snapshot", "model_version", "data_as_of", "data_version",
        )) <= columns
        table = ModelExecutionLog.__table__
        assert isinstance(table.c.data_as_of.type, sa.String)
        assert table.c.data_as_of.type.length == 32
        assert isinstance(table.c.data_version.type, sa.String)
        assert table.c.data_version.type.length == 32


def test_legacy_parcel_code_is_unique():
    app = _app()
    with app.app_context():
        db.create_all()
        db.session.add_all([
            ParcelInfo(parcel_id="P1", legacy_parcel_code="OLD"),
            ParcelInfo(parcel_id="P2", legacy_parcel_code="OLD"),
        ])
        try:
            db.session.commit()
        except sa.exc.IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError("legacy parcel code must be unique")


def test_seed_catalog_uses_only_enabled_exact_rows_and_is_idempotent():
    app = _app()
    with app.app_context():
        db.create_all()
        db.session.add_all([
            AreaCodeRegionMap(area_code="440281", region_name="乐昌市", primary="HN", secondary="MNY", ejnyq_idx=0, enabled=True),
            AreaCodeRegionMap(area_code="440282", region_name="禁用县", primary="HN", secondary="MNY", ejnyq_idx=0, enabled=False),
        ])
        db.session.commit()
        assert seed_spatial_region_catalog() == {"inserted": 1, "updated": 0, "skipped": 0}
        assert seed_spatial_region_catalog() == {"inserted": 0, "updated": 0, "skipped": 1}
        row = SpatialRegionCatalog.query.one()
        assert row.object_id == "440281"
        assert row.parent_object_type is None and row.parent_object_id is None
