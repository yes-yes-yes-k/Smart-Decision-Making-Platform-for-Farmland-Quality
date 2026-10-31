"""Additive relational migration for incremental graph governance tables."""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")


def ensure_knowledge_graph_platform_schema(engine) -> None:
    from framework.models.knowledge_graph import (
        KnowledgeGraphCandidateEvidence,
        KnowledgeGraphAuditExport,
        KnowledgeGraphBackfillRun,
        KnowledgeGraphClaimCandidate,
        KnowledgeGraphClaimEvidence,
        KnowledgeGraphEntityCandidate,
        KnowledgeGraphExtractionJob,
        KnowledgeGraphControl,
        KnowledgeGraphOutboxEvent,
        KnowledgeGraphRelationCandidate,
        KnowledgeGraphRelationRetirementCandidate,
        KnowledgeGraphRelease,
        KnowledgeGraphReleaseChange,
        KnowledgeGraphRollbackAudit,
        KnowledgeGraphReviewDecision,
        KnowledgeGraphStudyCandidate,
    )

    if not inspect(engine).has_table("kb_document"):
        return
    tables = (
        KnowledgeGraphExtractionJob,
        KnowledgeGraphStudyCandidate,
        KnowledgeGraphEntityCandidate,
        KnowledgeGraphRelationCandidate,
        KnowledgeGraphClaimCandidate,
        KnowledgeGraphCandidateEvidence,
        KnowledgeGraphClaimEvidence,
        KnowledgeGraphReviewDecision,
        KnowledgeGraphControl,
        KnowledgeGraphRollbackAudit,
        KnowledgeGraphAuditExport,
        KnowledgeGraphRelationRetirementCandidate,
        KnowledgeGraphBackfillRun,
        KnowledgeGraphRelease,
        KnowledgeGraphReleaseChange,
        KnowledgeGraphOutboxEvent,
    )
    for model in tables:
        model.__table__.create(bind=engine, checkfirst=True)

    inspector = inspect(engine)
    release_columns = {
        item["name"] for item in inspector.get_columns("kg_release")
    }
    if "sequence_no" not in release_columns:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE kg_release ADD COLUMN sequence_no INTEGER"
            ))
            connection.execute(text(
                "UPDATE kg_release SET sequence_no = id WHERE sequence_no IS NULL"
            ))
            if engine.dialect.name == "postgresql":
                connection.execute(text(
                    "ALTER TABLE kg_release ALTER COLUMN sequence_no SET NOT NULL"
                ))
            elif engine.dialect.name == "mysql":
                connection.execute(text(
                    "ALTER TABLE kg_release MODIFY sequence_no INTEGER NOT NULL"
                ))

    change_columns = {
        item["name"] for item in inspect(engine).get_columns("kg_release_change")
    }
    with engine.begin() as connection:
        if "valid_from_release" not in change_columns:
            connection.execute(text(
                "ALTER TABLE kg_release_change "
                "ADD COLUMN valid_from_release VARCHAR(128)"
            ))
            connection.execute(text(
                "UPDATE kg_release_change SET valid_from_release = release_id "
                "WHERE valid_from_release IS NULL"
            ))
            if engine.dialect.name == "postgresql":
                connection.execute(text(
                    "ALTER TABLE kg_release_change "
                    "ALTER COLUMN valid_from_release SET NOT NULL"
                ))
            elif engine.dialect.name == "mysql":
                connection.execute(text(
                    "ALTER TABLE kg_release_change MODIFY "
                    "valid_from_release VARCHAR(128) NOT NULL"
                ))
        if "valid_to_release" not in change_columns:
            connection.execute(text(
                "ALTER TABLE kg_release_change "
                "ADD COLUMN valid_to_release VARCHAR(128)"
            ))

    inspector = inspect(engine)
    review_columns = {
        item["name"] for item in inspector.get_columns("kg_review_decision")
    }
    if "idempotency_key" not in review_columns:
        if engine.dialect.name == "mysql":
            backfill = (
                "UPDATE kg_review_decision SET idempotency_key = "
                "CONCAT('legacy-review-', CAST(id AS CHAR)) "
                "WHERE idempotency_key IS NULL"
            )
        else:
            backfill = (
                "UPDATE kg_review_decision SET idempotency_key = "
                "'legacy-review-' || CAST(id AS VARCHAR) "
                "WHERE idempotency_key IS NULL"
            )
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE kg_review_decision ADD COLUMN idempotency_key VARCHAR(128)"
            ))
            connection.execute(text(backfill))
            if engine.dialect.name == "postgresql":
                connection.execute(text(
                    "ALTER TABLE kg_review_decision ALTER COLUMN idempotency_key SET NOT NULL"
                ))

    if engine.dialect.name == "mysql":
        index_names = {
            item["name"] for item in inspect(engine).get_indexes("kg_review_decision")
        }
        unique_names = {
            item["name"]
            for item in inspect(engine).get_unique_constraints("kg_review_decision")
        }
        if "uq_kg_review_idempotency" not in index_names | unique_names:
            with engine.begin() as connection:
                connection.execute(text(
                    "CREATE UNIQUE INDEX uq_kg_review_idempotency "
                    "ON kg_review_decision (idempotency_key)"
                ))
        release_indexes = {
            item["name"] for item in inspect(engine).get_indexes("kg_release")
        }
        release_unique = {
            item["name"] for item in inspect(engine).get_unique_constraints("kg_release")
        }
        if "uq_kg_release_sequence_no" not in release_indexes | release_unique:
            with engine.begin() as connection:
                connection.execute(text(
                    "CREATE UNIQUE INDEX uq_kg_release_sequence_no "
                    "ON kg_release (sequence_no)"
                ))

    if engine.dialect.name not in {"postgresql", "sqlite"}:
        return
    statements = (
        "CREATE INDEX IF NOT EXISTS idx_kg_job_claim "
        "ON kg_extraction_job (priority DESC, available_at, id) "
        "WHERE state IN ('pending', 'retry')",
        "CREATE INDEX IF NOT EXISTS idx_kg_job_lease_reclaim "
        "ON kg_extraction_job (lease_expires_at, id) WHERE state = 'running'",
        "CREATE INDEX IF NOT EXISTS idx_kg_entity_pending_review "
        "ON kg_entity_candidate (risk_level, id) WHERE review_status = 'pending'",
        "CREATE INDEX IF NOT EXISTS idx_kg_study_pending_review "
        "ON kg_study_candidate (study_kind, id) WHERE review_status = 'pending'",
        "CREATE INDEX IF NOT EXISTS idx_kg_relation_pending_review "
        "ON kg_relation_candidate (risk_level, relation_type, id) "
        "WHERE review_status = 'pending'",
        "CREATE INDEX IF NOT EXISTS idx_kg_claim_pending_review "
        "ON kg_claim_candidate (risk_level, claim_type, id) "
        "WHERE review_status = 'pending'",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_kg_review_idempotency "
        "ON kg_review_decision (idempotency_key)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_kg_release_sequence_no "
        "ON kg_release (sequence_no)",
        "CREATE INDEX IF NOT EXISTS idx_kg_evidence_active_document "
        "ON kg_candidate_evidence (document_id, content_sha256, id) "
        "WHERE is_active = TRUE",
        "CREATE INDEX IF NOT EXISTS idx_kg_outbox_claim "
        "ON kg_outbox_event (available_at, id) WHERE state IN ('pending', 'retry')",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def rollback_study_candidate_table(engine) -> None:
    """Drop the ``kg_study_candidate`` table added by R2.6a.

    Additive rollback: only the study-record table is removed. The remaining
    KG platform tables are left untouched so candidate/review/release state
    survives. Re-running :func:`ensure_knowledge_graph_platform_schema`
    recreates the table idempotently.
    """
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS kg_study_candidate CASCADE"))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Knowledge graph platform schema")
    parser.add_argument(
        "--rollback-study",
        action="store_true",
        help="drop only the kg_study_candidate table added by R2.6a",
    )
    args = parser.parse_args()

    from framework.api.app import create_app
    from framework.models.user import db

    app = create_app()
    with app.app_context():
        if args.rollback_study:
            rollback_study_candidate_table(db.engine)
            print("Rolled back kg_study_candidate table.")
        else:
            ensure_knowledge_graph_platform_schema(db.engine)
            print("Knowledge graph platform schema is ready.")


if __name__ == "__main__":
    main()
