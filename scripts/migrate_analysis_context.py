"""Analysis-context schema migration with idempotent upgrade and guarded rollback."""
from __future__ import annotations

import argparse
from collections.abc import Sequence

import sqlalchemy as sa


CONVERSATION_COLUMNS = {
    "analysis_object": "JSON",
    "context_version": "INTEGER NOT NULL DEFAULT 0",
    "analysis_object_updated_at": "DATETIME",
}
MESSAGE_COLUMNS = {"analysis_context_snapshot": "JSON"}
EXECUTION_COLUMNS = {
    "analysis_object_type": "VARCHAR(16)",
    "analysis_object_id": "VARCHAR(64)",
    "area_code": "VARCHAR(32)",
    "context_version": "INTEGER",
    "analysis_context_snapshot": "JSON",
    "model_version": "VARCHAR(32)",
    "data_as_of": "DATETIME",
    "data_version": "VARCHAR(64)",
}


def _columns(connection, table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(connection).get_columns(table)}


def _add_columns(connection, table: str, specs: dict[str, str]) -> None:
    inspector = sa.inspect(connection)
    if not inspector.has_table(table):
        return
    present = _columns(connection, table)
    preparer = connection.dialect.identifier_preparer
    table_sql = preparer.quote(table)
    for name, ddl_type in specs.items():
        if name not in present:
            connection.execute(sa.text(
                f"ALTER TABLE {table_sql} ADD COLUMN {preparer.quote(name)} {ddl_type}"
            ))


def ensure_analysis_context_columns(connection) -> None:
    _add_columns(connection, "kb_conversation", CONVERSATION_COLUMNS)
    _add_columns(connection, "kb_message", MESSAGE_COLUMNS)
    _add_columns(connection, "parcel_info", {"legacy_parcel_code": "VARCHAR(64)"})


def ensure_legacy_parcel_index(connection) -> None:
    inspector = sa.inspect(connection)
    if not inspector.has_table("parcel_info"):
        return
    indexes = {item["name"] for item in inspector.get_indexes("parcel_info")}
    unique_names = {item.get("name") for item in inspector.get_unique_constraints("parcel_info")}
    if not ({"idx_parcel_info_legacy_parcel_code", "uk_parcel_info_legacy_parcel_code"} & (indexes | unique_names)):
        connection.execute(sa.text(
            "CREATE UNIQUE INDEX idx_parcel_info_legacy_parcel_code "
            "ON parcel_info (legacy_parcel_code)"
        ))


def ensure_spatial_region_catalog(connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "spatial_region_catalog", metadata,
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("object_type", sa.String(16), nullable=False),
        sa.Column("object_id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("area_code", sa.String(32)),
        sa.Column("parent_object_type", sa.String(16)),
        sa.Column("parent_object_id", sa.String(64)),
        sa.Column("layer_id", sa.BigInteger),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("metadata", sa.JSON),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("object_type", "object_id", name="uk_spatial_region_catalog_object"),
        sa.Index("idx_spatial_region_catalog_area_code", "area_code"),
        sa.Index("idx_spatial_region_catalog_parent", "parent_object_type", "parent_object_id"),
        sa.Index("idx_spatial_region_catalog_enabled", "enabled"),
    )
    metadata.create_all(connection, checkfirst=True)


def ensure_execution_log_provenance(connection) -> None:
    _add_columns(connection, "model_execution_log", EXECUTION_COLUMNS)
    inspector = sa.inspect(connection)
    if not inspector.has_table("model_execution_log"):
        return
    indexes = {item["name"] for item in inspector.get_indexes("model_execution_log")}
    definitions = {
        "idx_model_execution_log_object": "analysis_object_type, analysis_object_id",
        "idx_model_execution_log_area_agent_status": "area_code, agent_id, status",
    }
    for name, columns in definitions.items():
        if name not in indexes:
            connection.execute(sa.text(f"CREATE INDEX {name} ON model_execution_log ({columns})"))


def _sqlite_trace_is_unique(connection) -> bool:
    rows = connection.execute(sa.text("PRAGMA index_list('model_execution_log')")).mappings()
    for row in rows:
        if row["unique"]:
            cols = connection.execute(sa.text(f"PRAGMA index_info('{row['name']}')")).mappings()
            if [col["name"] for col in cols] == ["trace_id"]:
                return True
    return False


def _sqlite_rebuild_execution_log(connection, *, unique_trace: bool) -> None:
    inspector = sa.inspect(connection)
    old_columns = inspector.get_columns("model_execution_log")
    old_names = [column["name"] for column in old_columns]
    metadata = sa.MetaData()
    source = sa.Table("model_execution_log", metadata, autoload_with=connection)
    temp_metadata = sa.MetaData()
    copied_columns = []
    for column in source.columns:
        copied_columns.append(sa.Column(
            column.name, column.type, primary_key=column.primary_key,
            nullable=column.nullable, server_default=column.server_default,
        ))
    constraints = []
    if unique_trace:
        constraints.append(sa.UniqueConstraint("trace_id", name="uk_model_execution_log_trace_id"))
    temp = sa.Table("model_execution_log__migration", temp_metadata, *copied_columns, *constraints)
    temp.create(connection)
    quoted = ", ".join(connection.dialect.identifier_preparer.quote(name) for name in old_names)
    connection.execute(sa.text(
        f"INSERT INTO model_execution_log__migration ({quoted}) "
        f"SELECT {quoted} FROM model_execution_log"
    ))
    source.drop(connection)
    connection.execute(sa.text("ALTER TABLE model_execution_log__migration RENAME TO model_execution_log"))


def replace_unique_trace_constraint_with_index(connection) -> None:
    inspector = sa.inspect(connection)
    if not inspector.has_table("model_execution_log"):
        return
    dialect = connection.dialect.name
    if dialect == "sqlite" and _sqlite_trace_is_unique(connection):
        _sqlite_rebuild_execution_log(connection, unique_trace=False)
    elif dialect in {"postgresql", "mysql"}:
        unique_names = {item.get("name") for item in inspector.get_unique_constraints("model_execution_log")}
        if "uk_model_execution_log_trace_id" in unique_names:
            if dialect == "postgresql":
                connection.execute(sa.text(
                    "ALTER TABLE model_execution_log DROP CONSTRAINT uk_model_execution_log_trace_id"
                ))
            else:
                connection.execute(sa.text(
                    "ALTER TABLE model_execution_log DROP INDEX uk_model_execution_log_trace_id"
                ))
    indexes = {item["name"] for item in sa.inspect(connection).get_indexes("model_execution_log")}
    if "idx_model_execution_log_trace_id" not in indexes:
        connection.execute(sa.text(
            "CREATE INDEX idx_model_execution_log_trace_id ON model_execution_log (trace_id)"
        ))


def upgrade_schema(engine) -> None:
    with engine.begin() as connection:
        ensure_analysis_context_columns(connection)
        ensure_legacy_parcel_index(connection)
        ensure_spatial_region_catalog(connection)
        ensure_execution_log_provenance(connection)
        replace_unique_trace_constraint_with_index(connection)


def assert_context_columns_empty(engine) -> None:
    checks = {
        "kb_conversation": ["analysis_object", "analysis_object_updated_at"],
        "kb_message": ["analysis_context_snapshot"],
        "model_execution_log": list(EXECUTION_COLUMNS),
        "parcel_info": ["legacy_parcel_code"],
    }
    with engine.connect() as connection:
        inspector = sa.inspect(connection)
        for table, columns in checks.items():
            if not inspector.has_table(table):
                continue
            existing = _columns(connection, table)
            for column in columns:
                if column in existing:
                    count = connection.execute(sa.text(
                        f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL"
                    )).scalar_one()
                    if count:
                        raise RuntimeError(f"refusing to discard non-empty {table}.{column}")
        if inspector.has_table("kb_conversation") and "context_version" in _columns(connection, "kb_conversation"):
            count = connection.execute(sa.text(
                "SELECT COUNT(*) FROM kb_conversation WHERE context_version <> 0"
            )).scalar_one()
            if count:
                raise RuntimeError("refusing to discard non-default kb_conversation.context_version")
        if inspector.has_table("spatial_region_catalog"):
            count = connection.execute(sa.text("SELECT COUNT(*) FROM spatial_region_catalog")).scalar_one()
            if count:
                raise RuntimeError("refusing to discard non-empty spatial_region_catalog")


def _sqlite_drop_columns(connection, table: str, names: set[str]) -> None:
    if not sa.inspect(connection).has_table(table):
        return
    for index in sa.inspect(connection).get_indexes(table):
        if names.intersection(index.get("column_names") or ()):
            connection.execute(sa.text(f"DROP INDEX IF EXISTS {index['name']}"))
    for name in names & _columns(connection, table):
        connection.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {name}"))


def restore_unique_trace_constraint(connection) -> None:
    if not sa.inspect(connection).has_table("model_execution_log"):
        return
    if connection.dialect.name == "sqlite":
        if not _sqlite_trace_is_unique(connection):
            _sqlite_rebuild_execution_log(connection, unique_trace=True)
        return
    connection.execute(sa.text("DROP INDEX IF EXISTS idx_model_execution_log_trace_id"))
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text(
            "ALTER TABLE model_execution_log ADD CONSTRAINT uk_model_execution_log_trace_id UNIQUE (trace_id)"
        ))
    else:
        connection.execute(sa.text(
            "ALTER TABLE model_execution_log ADD CONSTRAINT uk_model_execution_log_trace_id UNIQUE (trace_id)"
        ))


def drop_analysis_context_objects(connection) -> None:
    if sa.inspect(connection).has_table("spatial_region_catalog"):
        connection.execute(sa.text("DROP TABLE spatial_region_catalog"))
    for table, columns in (
        ("kb_conversation", set(CONVERSATION_COLUMNS)),
        ("kb_message", set(MESSAGE_COLUMNS)),
        ("model_execution_log", set(EXECUTION_COLUMNS)),
        ("parcel_info", {"legacy_parcel_code"}),
    ):
        _sqlite_drop_columns(connection, table, columns)


def downgrade_schema(engine, *, force: bool = False) -> None:
    if not force:
        assert_context_columns_empty(engine)
    with engine.begin() as connection:
        restore_unique_trace_constraint(connection)
        drop_analysis_context_objects(connection)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("direction", choices=("upgrade", "downgrade"))
    parser.add_argument("--config", default="default")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from framework.api.app import create_app
    from framework.models import db
    app = create_app(args.config)
    with app.app_context():
        if args.direction == "upgrade":
            upgrade_schema(db.engine)
        else:
            downgrade_schema(db.engine, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
