from datetime import datetime, timedelta

from flask import Flask

from framework.knowledge_graph.observability import snapshot_graph_governance_metrics
from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphEntityCandidate, KnowledgeGraphExtractionJob,
    KnowledgeGraphRelationCandidate,
)
from framework.models.user import db
from scripts.migrate_knowledge_graph_platform import ensure_knowledge_graph_platform_schema


def test_governance_metrics_expose_backlog_failures_leases_quality_and_alerts(tmp_path):
    app = Flask("kg-observability-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'metrics.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        Document.__table__.create(db.engine)
        ensure_knowledge_graph_platform_schema(db.engine)
        document = Document(
            id=1, doc_name="x", file_path="x", file_type="pdf", create_by=1,
        )
        db.session.add(document)
        now = datetime(2026, 10, 24, 12, 0, 0)
        job = KnowledgeGraphExtractionJob(
            document_id=1, content_sha256="a" * 64, schema_version="s",
            backend_name="b", extractor_version="1", backend_config_digest="c" * 64,
            state="running", lease_expires_at=now - timedelta(seconds=1),
        )
        db.session.add(job)
        db.session.flush()
        source = KnowledgeGraphEntityCandidate(
            job_id=job.id, candidate_key="s", entity_type="measure", mention="m",
            canonical_entity_id="measure:m", canonical_name="m",
            resolution_status="resolved", review_status="approved", confidence=1,
        )
        target = KnowledgeGraphEntityCandidate(
            job_id=job.id, candidate_key="t", entity_type="obstacle", mention="o",
            canonical_entity_id="obstacle:o", canonical_name="o",
            resolution_status="resolved", review_status="approved", confidence=1,
        )
        db.session.add_all([source, target])
        db.session.flush()
        db.session.add(KnowledgeGraphRelationCandidate(
            job_id=job.id, candidate_key="r", relation_type="addresses",
            source_candidate_id=source.id, target_candidate_id=target.id,
            canonical_source_id="measure:m", canonical_target_id="obstacle:o",
            risk_level="new_fact", validation_status="validated",
            review_status="approved", confidence=1,
        ))
        db.session.commit()
        metrics = snapshot_graph_governance_metrics(db.session, now=now)
        assert metrics["jobs"]["expired_leases"] == 1
        assert metrics["graph_quality"]["approved_relations_without_active_evidence"] == 1
        assert "expired_leases_present" in metrics["alerts"]
        assert "evidence_free_relations_present" in metrics["alerts"]
        assert "failure_message" not in str(metrics)
