from flask import Flask
from sqlalchemy import inspect, text

from framework.models.user import db
from scripts.migrate_literature_ingestion import ensure_literature_ingestion_schema


def test_additive_migration_preserves_legacy_document_table(tmp_path):
    app = Flask("literature-migration-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'legacy.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        with db.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE kb_document ("
                "id INTEGER PRIMARY KEY, doc_name VARCHAR(255) NOT NULL, "
                "file_path VARCHAR(500) NOT NULL, file_type VARCHAR(20) NOT NULL, "
                "status SMALLINT DEFAULT 1, create_by INTEGER NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO kb_document "
                "(id, doc_name, file_path, file_type, status, create_by) "
                "VALUES (1, 'legacy.txt', 'legacy.txt', 'txt', 1, 7)"
            ))

        ensure_literature_ingestion_schema(db.engine)
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("kb_document")}
        assert {
            "document_kind", "processing_stage", "review_status",
            "bibliographic_metadata", "parse_metadata", "idempotency_key",
        }.issubset(columns)
        assert inspector.has_table("kb_ingestion_batch")
        assert inspector.has_table("kb_ingestion_item")
        with db.engine.connect() as connection:
            row = connection.execute(text(
                "SELECT doc_name, status, review_status FROM kb_document WHERE id=1"
            )).one()
        assert tuple(row) == ("legacy.txt", 1, "approved")
