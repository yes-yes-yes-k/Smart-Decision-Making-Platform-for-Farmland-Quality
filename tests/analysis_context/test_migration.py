import sqlalchemy as sa
import pytest

from scripts.migrate_analysis_context import downgrade_schema, upgrade_schema


def _create_legacy_schema(engine):
    metadata = sa.MetaData()
    sa.Table(
        "kb_conversation", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    sa.Table(
        "kb_message", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    sa.Table(
        "parcel_info", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("parcel_id", sa.String(64), nullable=False),
    )
    sa.Table(
        "model_execution_log", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.UniqueConstraint("trace_id", name="uk_model_execution_log_trace_id"),
    )
    metadata.create_all(engine)


def _column_names(engine, table):
    return {column["name"] for column in sa.inspect(engine).get_columns(table)}


def test_upgrade_is_idempotent_and_downgrade_restores_legacy_schema(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _create_legacy_schema(engine)
    upgrade_schema(engine)
    upgrade_schema(engine)
    inspector = sa.inspect(engine)
    assert inspector.has_table("spatial_region_catalog")
    assert "analysis_object" in _column_names(engine, "kb_conversation")
    assert "analysis_context_snapshot" in _column_names(engine, "kb_message")
    assert "analysis_object_type" in _column_names(engine, "model_execution_log")
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO model_execution_log (trace_id, agent_id, status) VALUES "
            "('trace-1', 'model-1', 'ok'), ('trace-1', 'model-3', 'ok')"
        ))
        connection.execute(sa.text("DELETE FROM model_execution_log"))
    downgrade_schema(engine)
    inspector = sa.inspect(engine)
    assert not inspector.has_table("spatial_region_catalog")
    assert "analysis_object" not in _column_names(engine, "kb_conversation")
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO model_execution_log (trace_id, agent_id, status) VALUES "
                "('trace-2', 'model-1', 'ok'), ('trace-2', 'model-3', 'ok')"
            ))


def test_downgrade_refuses_non_empty_context_without_force(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'guard.db'}")
    _create_legacy_schema(engine)
    upgrade_schema(engine)
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO kb_conversation (id, analysis_object) VALUES (1, '{\"type\": \"parcel\"}')"
        ))
    with pytest.raises(RuntimeError, match="refusing to discard"):
        downgrade_schema(engine)
    downgrade_schema(engine, force=True)
