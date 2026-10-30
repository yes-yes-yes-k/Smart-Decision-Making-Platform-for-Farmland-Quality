from datetime import datetime, timedelta

from flask import Flask

from framework.knowledge_graph.jobs import (
    KnowledgeGraphOutboxDispatcher,
    SqlAlchemyGraphJobExecutor,
    enqueue_document_indexed,
    materialize_outbox_event,
)
from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphExtractionJob,
    KnowledgeGraphOutboxEvent,
)
from framework.models.user import db


def _app(tmp_path):
    app = Flask("knowledge-graph-job-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'kg-jobs.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    return app


def _document(document_id=1):
    return Document(
        id=document_id,
        doc_name="paper.pdf",
        file_path="paper.pdf",
        file_type="pdf",
        file_size=100,
        chunk_count=3,
        status=Document.STATUS_COMPLETED,
        category="other",
        visibility_scope="public",
        file_hash="a" * 64,
        document_kind="academic_paper",
        processing_stage="completed",
        review_status=Document.REVIEW_APPROVED,
        create_by=7,
    )


def _setup(tmp_path):
    app = _app(tmp_path)
    context = app.app_context()
    context.push()
    # Create only this feature's dependency graph.  Full metadata also
    # contains GeoAlchemy models whose SQLite DDL requires SpatiaLite.
    Document.__table__.create(bind=db.engine, checkfirst=True)
    KnowledgeGraphExtractionJob.__table__.create(bind=db.engine, checkfirst=True)
    KnowledgeGraphOutboxEvent.__table__.create(bind=db.engine, checkfirst=True)
    document = _document()
    db.session.add(document)
    db.session.commit()
    return app, context, document


def test_document_completion_outbox_and_dispatch_are_idempotent(tmp_path):
    _, context, document = _setup(tmp_path)
    try:
        event, created = enqueue_document_indexed(db.session, document)
        duplicate, duplicate_created = enqueue_document_indexed(db.session, document)
        db.session.commit()

        assert created is True
        assert duplicate_created is False
        assert duplicate.id == event.id
        counts = KnowledgeGraphOutboxDispatcher(db.session).dispatch()
        db.session.commit()
        assert counts == {"selected": 1, "created": 1, "reused": 0, "failed": 0}
        assert KnowledgeGraphExtractionJob.query.count() == 1

        job, replay_created = materialize_outbox_event(db.session, event)
        db.session.commit()
        assert replay_created is False
        assert job.id == KnowledgeGraphExtractionJob.query.one().id
        assert document.status == Document.STATUS_COMPLETED
    finally:
        db.session.remove()
        context.pop()


def test_outbox_rolls_back_with_document_transaction(tmp_path):
    _, context, document = _setup(tmp_path)
    try:
        document.title = "changed in uncommitted transaction"
        enqueue_document_indexed(db.session, document)
        db.session.rollback()

        assert KnowledgeGraphOutboxEvent.query.count() == 0
        assert db.session.get(Document, document.id).title is None
    finally:
        db.session.remove()
        context.pop()


def test_invalid_outbox_event_dead_letters_without_changing_document(tmp_path):
    _, context, document = _setup(tmp_path)
    try:
        event = KnowledgeGraphOutboxEvent(
            event_key="invalid-event",
            event_type="knowledge_document_indexed",
            aggregate_type="kb_document",
            aggregate_id=str(document.id),
            payload={"document_id": document.id},
            state="pending",
        )
        db.session.add(event)
        db.session.commit()

        counts = KnowledgeGraphOutboxDispatcher(db.session).dispatch()
        db.session.commit()

        assert counts["failed"] == 1
        assert event.state == "dead_letter"
        assert db.session.get(Document, document.id).status == Document.STATUS_COMPLETED
    finally:
        db.session.remove()
        context.pop()


def test_lease_expiry_reclaims_after_worker_crash_and_rejects_stale_owner(tmp_path):
    _, context, document = _setup(tmp_path)
    now = [datetime(2026, 10, 24, 1, 0, 0)]
    try:
        event, _ = enqueue_document_indexed(db.session, document)
        materialize_outbox_event(db.session, event, now=now[0])
        db.session.commit()
        executor = SqlAlchemyGraphJobExecutor(db.session, clock=lambda: now[0])

        first = executor.claim(worker_id="worker-a", limit=1, lease_seconds=30)
        db.session.commit()
        assert len(first) == 1
        job_id = first[0].id
        assert executor.claim(worker_id="worker-b", limit=1, lease_seconds=30) == ()

        now[0] += timedelta(seconds=31)
        reclaimed = executor.claim(worker_id="worker-b", limit=1, lease_seconds=30)
        db.session.commit()
        assert reclaimed[0].id == job_id
        assert reclaimed[0].attempt_count == 2
        assert executor.complete(
            worker_id="worker-a", job_id=str(job_id), result_digest="old",
        ) is False
        assert executor.renew(
            worker_id="worker-b", job_id=str(job_id), lease_seconds=60,
        ) is True
        assert executor.complete(
            worker_id="worker-b", job_id=str(job_id), result_digest="c" * 64,
        ) is True
        db.session.commit()
        assert db.session.get(KnowledgeGraphExtractionJob, job_id).state == "completed"
    finally:
        db.session.remove()
        context.pop()


def test_retry_uses_exponential_backoff_then_dead_letters_without_document_rollback(tmp_path):
    _, context, document = _setup(tmp_path)
    now = [datetime(2026, 10, 24, 2, 0, 0)]
    try:
        event, _ = enqueue_document_indexed(db.session, document)
        job, _ = materialize_outbox_event(db.session, event, now=now[0])
        job.max_attempts = 2
        db.session.commit()
        executor = SqlAlchemyGraphJobExecutor(db.session, clock=lambda: now[0])

        executor.claim(worker_id="worker", limit=1, lease_seconds=30)
        assert executor.fail(
            worker_id="worker", job_id=str(job.id),
            error_code="model_timeout", retryable=True,
        ) is True
        assert job.state == "retry"
        assert job.available_at == now[0] + timedelta(seconds=1)
        db.session.commit()

        now[0] += timedelta(seconds=1)
        executor.claim(worker_id="worker", limit=1, lease_seconds=30)
        executor.fail(
            worker_id="worker", job_id=str(job.id),
            error_code="model_timeout", retryable=True,
        )
        db.session.commit()

        assert job.state == "dead_letter"
        assert db.session.get(Document, document.id).status == Document.STATUS_COMPLETED
    finally:
        db.session.remove()
        context.pop()


def test_crash_on_final_attempt_is_reaped_to_dead_letter(tmp_path):
    _, context, document = _setup(tmp_path)
    now = [datetime(2026, 10, 24, 3, 0, 0)]
    try:
        event, _ = enqueue_document_indexed(db.session, document)
        job, _ = materialize_outbox_event(db.session, event, now=now[0])
        job.max_attempts = 1
        db.session.commit()
        executor = SqlAlchemyGraphJobExecutor(db.session, clock=lambda: now[0])

        claimed = executor.claim(worker_id="crashing-worker", limit=1, lease_seconds=5)
        db.session.commit()
        assert claimed[0].attempt_count == 1

        now[0] += timedelta(seconds=6)
        assert executor.claim(worker_id="replacement", limit=1, lease_seconds=5) == ()
        db.session.commit()

        assert job.state == "dead_letter"
        assert job.failure_code == "attempts_exhausted"
        assert job.lease_owner is None
    finally:
        db.session.remove()
        context.pop()
