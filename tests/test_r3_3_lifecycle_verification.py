"""R3.3 end-to-end verification: lease, idempotency, cancel, crash recovery.

These tests exercise the existing SqlAlchemyGraphJobExecutor and
ResearchService against the full kg_* schema (including the new
kg_study_candidate from R2.6a) to verify the lifecycle guarantees hold
with the new persistence layer.
"""
from __future__ import annotations

from datetime import timedelta

from flask import Flask

from framework.knowledge_graph.jobs import (
    SqlAlchemyGraphJobExecutor,
    enqueue_document_indexed,
    materialize_outbox_event,
    utcnow_naive,
)
from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphExtractionJob,
    KnowledgeGraphOutboxEvent,
)
from framework.models.user import User, db
from scripts.migrate_knowledge_graph_platform import ensure_knowledge_graph_platform_schema

SHA = "a" * 64


def _setup(tmp_path):
    app = Flask("r3-3-lifecycle-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'lifecycle.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    context = app.app_context()
    context.push()
    User.__table__.create(db.engine)
    Document.__table__.create(db.engine)
    ensure_knowledge_graph_platform_schema(db.engine)
    db.session.add(User(id=1, username="admin", password="x", role="admin"))
    db.session.add(Document(
        id=100, doc_name="paper.pdf", file_path="paper.pdf",
        file_type="pdf", chunk_count=3, status=Document.STATUS_COMPLETED,
        processing_stage="completed", review_status=Document.REVIEW_APPROVED,
        visibility_scope="public", document_kind="academic_paper",
        file_hash=SHA, create_by=1,
    ))
    db.session.commit()


def _enqueue_and_materialize(document_id=100):
    """Push an outbox event and materialize it into an extraction job."""
    doc = db.session.get(Document, document_id)
    event, created = enqueue_document_indexed(db.session, doc)
    db.session.commit()
    job, created = materialize_outbox_event(db.session, event)
    db.session.commit()
    return job


# --- Lease expiry → another worker reclaims ---


def test_lease_expiry_allows_reclaim_by_another_worker(tmp_path):
    _setup(tmp_path)
    job = _enqueue_and_materialize()
    executor = SqlAlchemyGraphJobExecutor(db.session)

    # Worker A claims the job.
    claimed = executor.claim(worker_id="worker-A", limit=1, lease_seconds=1)
    assert len(claimed) == 1 and claimed[0].id == job.id
    db.session.commit()

    # Simulate lease expiry: move the clock past the lease.
    job = db.session.get(KnowledgeGraphExtractionJob, job.id)
    job.lease_expires_at = utcnow_naive() - timedelta(seconds=1)
    db.session.commit()

    # Worker B reclaims the expired lease.
    reclaimed = executor.claim(worker_id="worker-B", limit=1, lease_seconds=60)
    assert len(reclaimed) == 1 and reclaimed[0].id == job.id
    assert reclaimed[0].lease_owner == "worker-B"
    assert reclaimed[0].attempt_count == 2  # A claimed first (1), B reclaims (2)
    db.session.commit()


# --- Cancel → job cannot be claimed again ---


def test_cancelled_job_not_claimable(tmp_path):
    _setup(tmp_path)
    job = _enqueue_and_materialize()
    executor = SqlAlchemyGraphJobExecutor(db.session)

    # Cancel the job by setting state directly (simulating ResearchService.cancel).
    job = db.session.get(KnowledgeGraphExtractionJob, job.id)
    job.state = "cancelled"
    db.session.commit()

    # No claimable job should be returned.
    claimed = executor.claim(worker_id="worker-X", limit=1, lease_seconds=60)
    assert len(claimed) == 0


# --- Crash recovery: lease expires → reclaim → complete ---


def test_crash_recovery_reclaim_and_complete(tmp_path):
    _setup(tmp_path)
    job = _enqueue_and_materialize()
    executor = SqlAlchemyGraphJobExecutor(db.session)

    # Worker A claims but "crashes" (no heartbeat, lease expires).
    claimed = executor.claim(worker_id="worker-A", limit=1, lease_seconds=1)
    assert len(claimed) == 1
    db.session.commit()

    # Simulate crash: lease expires.
    job = db.session.get(KnowledgeGraphExtractionJob, job.id)
    job.lease_expires_at = utcnow_naive() - timedelta(seconds=1)
    db.session.commit()

    # Worker B reclaims and completes.
    reclaimed = executor.claim(worker_id="worker-B", limit=1, lease_seconds=60)
    assert len(reclaimed) == 1
    job_id = str(reclaimed[0].id)
    db.session.commit()

    ok = executor.complete(worker_id="worker-B", job_id=job_id, result_digest="abc123")
    assert ok is True
    db.session.commit()

    job = db.session.get(KnowledgeGraphExtractionJob, int(job_id))
    assert job.state == "completed"
    assert job.result_digest == "abc123"


# --- Idempotency: same outbox event does not create duplicate jobs ---


def test_idempotent_enqueue_does_not_duplicate(tmp_path):
    _setup(tmp_path)
    doc = db.session.get(Document, 100)

    # Enqueue twice with the same document.
    event1, created1 = enqueue_document_indexed(db.session, doc)
    db.session.commit()
    event2, created2 = enqueue_document_indexed(db.session, doc)
    db.session.commit()

    # Second enqueue returns the existing event, not a new one.
    assert created1 is True
    assert created2 is False
    assert event1.id == event2.id

    # Materialize produces exactly one job.
    job1, j_created1 = materialize_outbox_event(db.session, event1)
    db.session.commit()
    assert db.session.query(KnowledgeGraphExtractionJob).count() == 1

    # Re-materialize the same event: no new job.
    event1.state = "pending"  # reset to allow re-dispatch
    db.session.commit()
    job2, j_created2 = materialize_outbox_event(db.session, event1)
    db.session.commit()
    assert j_created2 is False
    assert job1.id == job2.id
    assert db.session.query(KnowledgeGraphExtractionJob).count() == 1


# --- Source invalidation: version drift on completed job ---


def test_completed_job_signature_drift_detected(tmp_path):
    """When source version changes, read_candidates returns 'invalidated'."""
    from framework.knowledge_graph.candidate_reader import read_candidates
    from framework.knowledge_graph.candidate_store import write_bundle

    _setup(tmp_path)
    # Write a candidate bundle (same pattern as R2.6b tests).
    span = {
        "document_id": 100, "document_sha256": SHA, "parse_version": SHA,
        "chunk_set_version": SHA, "chunk_index": 0, "start": 0, "end": 4,
        "quote": "Cd在", "page": 1, "quote_sha256": SHA, "id": "span:test",
    }
    bundle = {
        "schema_version": "task-evidence-extraction-v2",
        "source": {"document_id": 100, "document_sha256": SHA,
                    "parse_version": SHA, "chunk_set_version": SHA},
        "provenance": {"origin": "test", "configuration_sha256": SHA},
        "studies": [{"local_id": "s1", "kind": "observational",
                      "context": [span], "attribution": None}],
        "entities": [{"local_id": "e1", "study_id": "s1", "entity_type": "measure",
                      "surface": "Cd在", "mention": span,
                      "normalization": {"status": "unresolved", "canonical_id": None, "canonical_name": None}}],
        "relations": [],
        "review_status": "pending", "published_claims_added": 0,
        "rule_validation": "passed", "semantic_support": "unreviewed",
        "identity": "test-identity",
    }
    write_bundle(bundle)

    # Normal read: version matches.
    result = read_candidates(100, live_source={
        "content_sha256": SHA, "visibility_scope": "public",
        "review_status": "approved", "document_kind": "academic_paper",
        "completed": True,
    })
    assert result["status"] == "ok"

    # Version drift: document re-parsed, hash changed.
    result = read_candidates(100, live_source={
        "content_sha256": "b" * 64, "visibility_scope": "public",
        "review_status": "approved", "document_kind": "academic_paper",
        "completed": True,
    })
    assert result["status"] == "invalidated"


# --- Max attempts exhaustion → dead letter ---


def test_max_attempts_exhaustion_moves_to_dead_letter(tmp_path):
    _setup(tmp_path)
    job = _enqueue_and_materialize()
    executor = SqlAlchemyGraphJobExecutor(db.session)

    # Exhaust all attempts.
    job.max_attempts = 2
    db.session.commit()
    for i in range(2):
        claimed = executor.claim(worker_id=f"worker-{i}", limit=1, lease_seconds=1)
        assert len(claimed) == 1
        db.session.commit()
        # Expire the lease.
        j = db.session.get(KnowledgeGraphExtractionJob, claimed[0].id)
        j.lease_expires_at = utcnow_naive() - timedelta(seconds=1)
        db.session.commit()

    # Third claim attempt: job should go to dead_letter (attempts exhausted).
    claimed = executor.claim(worker_id="worker-final", limit=1, lease_seconds=60)
    assert len(claimed) == 0  # not claimable
    job = db.session.get(KnowledgeGraphExtractionJob, job.id)
    assert job.state == "dead_letter"
