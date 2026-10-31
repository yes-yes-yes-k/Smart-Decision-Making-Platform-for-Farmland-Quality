from flask import Flask
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from framework.models.knowledge_graph import KnowledgeGraphExtractionJob
from framework.models.user import db
from scripts.migrate_knowledge_graph_platform import ensure_knowledge_graph_platform_schema


def _app(tmp_path):
    app = Flask("knowledge-graph-platform-migration-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'kg-platform.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    return app


def test_additive_knowledge_graph_migration_creates_governance_tables_and_indexes(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        with db.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE kb_document (id INTEGER PRIMARY KEY, "
                "doc_name VARCHAR(255) NOT NULL, file_path VARCHAR(500) NOT NULL, "
                "file_type VARCHAR(20) NOT NULL, create_by INTEGER NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO kb_document (id, doc_name, file_path, file_type, create_by) "
                "VALUES (1, 'paper.pdf', 'paper.pdf', 'pdf', 7)"
            ))

        ensure_knowledge_graph_platform_schema(db.engine)
        inspector = inspect(db.engine)
        expected = {
            "kg_extraction_job",
            "kg_study_candidate",
            "kg_entity_candidate",
            "kg_relation_candidate",
            "kg_claim_candidate",
            "kg_candidate_evidence",
            "kg_claim_evidence",
            "kg_review_decision",
            "kg_control",
            "kg_rollback_audit",
            "kg_audit_export",
            "kg_relation_retirement_candidate",
            "kg_backfill_run",
            "kg_release",
            "kg_release_change",
            "kg_outbox_event",
        }
        assert all(inspector.has_table(name) for name in expected)
        assert "idx_kg_job_claim" in {
            item["name"] for item in inspector.get_indexes("kg_extraction_job")
        }
        assert "idx_kg_outbox_claim" in {
            item["name"] for item in inspector.get_indexes("kg_outbox_event")
        }
        assert "idx_kg_claim_pending_review" in {
            item["name"] for item in inspector.get_indexes("kg_claim_candidate")
        }
        assert "idempotency_key" in {
            item["name"] for item in inspector.get_columns("kg_review_decision")
        }
        assert {"sequence_no"} <= {
            item["name"] for item in inspector.get_columns("kg_release")
        }
        assert {"valid_from_release", "valid_to_release"} <= {
            item["name"] for item in inspector.get_columns("kg_release_change")
        }
        assert "uq_kg_review_idempotency" in {
            item["name"] for item in inspector.get_indexes("kg_review_decision")
        } | {
            item["name"]
            for item in inspector.get_unique_constraints("kg_review_decision")
        }


def test_extraction_job_has_database_enforced_full_idempotency_key(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        with db.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE kb_document (id INTEGER PRIMARY KEY, "
                "doc_name VARCHAR(255) NOT NULL, file_path VARCHAR(500) NOT NULL, "
                "file_type VARCHAR(20) NOT NULL, create_by INTEGER NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO kb_document (id, doc_name, file_path, file_type, create_by) "
                "VALUES (1, 'paper.pdf', 'paper.pdf', 'pdf', 7)"
            ))
        ensure_knowledge_graph_platform_schema(db.engine)
        values = {
            "document_id": 1,
            "content_sha256": "a" * 64,
            "schema_version": "schema-v1",
            "backend_name": "microsoft-graphrag",
            "extractor_version": "3.3.0",
            "backend_config_digest": "b" * 64,
        }
        db.session.add(KnowledgeGraphExtractionJob(**values))
        db.session.commit()
        db.session.add(KnowledgeGraphExtractionJob(**values))

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
