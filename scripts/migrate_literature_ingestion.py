"""Additive migration helpers for the literature ingestion workflow.

The project does not currently use Alembic.  This module follows the existing
startup compatibility pattern: add nullable/defaulted columns, create new
tables, and never drop or rewrite existing data.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / '.env')


DOCUMENT_COLUMNS = {
    "doc_type": "VARCHAR(30) DEFAULT 'other'",
    "idempotency_key": "VARCHAR(128)",
    "document_kind": "VARCHAR(40) NOT NULL DEFAULT 'other'",
    "title": "VARCHAR(500)",
    "language": "VARCHAR(40)",
    "doi_normalized": "VARCHAR(300)",
    "standard_number_normalized": "VARCHAR(200)",
    "issuing_authority": "VARCHAR(300)",
    "authority_status": "VARCHAR(30) NOT NULL DEFAULT 'unverified'",
    "bibliographic_metadata": "JSON",
    "provenance_metadata": "JSON",
    "parse_metadata": "JSON",
    "processing_stage": "VARCHAR(40)",
    "failure_code": "VARCHAR(80)",
    "failure_message": "VARCHAR(1000)",
    "retryable": "BOOLEAN NOT NULL DEFAULT FALSE",
    "review_status": "VARCHAR(20) NOT NULL DEFAULT 'approved'",
    "reviewed_by": "INTEGER",
    "reviewed_at": "TIMESTAMP",
    "review_note": "VARCHAR(1000)",
    "review_idempotency_key": "VARCHAR(128)",
}


def ensure_literature_ingestion_schema(engine) -> None:
    from framework.models.ingestion import IngestionBatch, IngestionItem

    inspector = inspect(engine)
    if not inspector.has_table("kb_document"):
        return

    existing = {column["name"] for column in inspector.get_columns("kb_document")}
    with engine.begin() as connection:
        for name, ddl in DOCUMENT_COLUMNS.items():
            if name not in existing:
                connection.execute(text(
                    f"ALTER TABLE kb_document ADD COLUMN {name} {ddl}"
                ))

    IngestionBatch.__table__.create(bind=engine, checkfirst=True)
    IngestionItem.__table__.create(bind=engine, checkfirst=True)

    dialect = engine.dialect.name
    with engine.begin() as connection:
        if dialect in {"postgresql", "sqlite"}:
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_kb_document_owner_idempotency_idx "
                "ON kb_document (create_by, idempotency_key) "
                "WHERE idempotency_key IS NOT NULL"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_kb_document_review_status "
                "ON kb_document (review_status)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_kb_document_processing_stage "
                "ON kb_document (processing_stage)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_kb_document_doi "
                "ON kb_document (doi_normalized)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_kb_document_standard_number "
                "ON kb_document (standard_number_normalized)"
            ))


def main() -> None:
    from framework.api.app import create_app
    from framework.models.user import db

    app = create_app()
    with app.app_context():
        ensure_literature_ingestion_schema(db.engine)
    print("Literature ingestion schema is ready.")


if __name__ == "__main__":
    main()
