"""Transactional outbox and database-leased extraction job primitives."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable, Sequence

from sqlalchemy import and_, or_

from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphExtractionJob,
    KnowledgeGraphOutboxEvent,
)

from .contracts import stable_digest
from .extraction_config import backend_config_digest as extraction_digest
from .schema import load_graph_schema


SUPPORTED_DOCUMENT_KINDS = {
    "academic_paper", "standard", "policy", "method_guideline",
}
DEFAULT_BACKEND_NAME = "microsoft-graphrag"
DEFAULT_EXTRACTOR_VERSION = "3.3.0"


class OutboxPayloadError(ValueError):
    pass


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def document_is_graph_eligible(document: Document) -> bool:
    return bool(
        getattr(document, "id", None)
        and getattr(document, "status", None) == Document.STATUS_COMPLETED
        and getattr(document, "processing_stage", None) == "completed"
        and getattr(document, "review_status", None) == Document.REVIEW_APPROVED
        and getattr(document, "visibility_scope", None) == "public"
        and getattr(document, "document_kind", None) in SUPPORTED_DOCUMENT_KINDS
        and getattr(document, "file_hash", None)
        and int(getattr(document, "chunk_count", 0) or 0) > 0
    )


def enqueue_document_indexed(
    session,
    document: Document,
    *,
    schema_version: str | None = None,
    backend_name: str = DEFAULT_BACKEND_NAME,
    extractor_version: str = DEFAULT_EXTRACTOR_VERSION,
    backend_config_digest: str | None = None,
) -> tuple[KnowledgeGraphOutboxEvent | None, bool]:
    """Add an outbox row to the caller's transaction; never dispatch work."""
    if not document_is_graph_eligible(document):
        return None, False
    schema_version = schema_version or load_graph_schema().schema_version
    backend_config_digest = backend_config_digest or extraction_digest(
        backend_name, extractor_version, schema_version,
    )
    payload = {
        "document_id": int(document.id),
        "content_sha256": str(document.file_hash),
        "schema_version": schema_version,
        "backend_name": backend_name,
        "extractor_version": extractor_version,
        "backend_config_digest": backend_config_digest,
    }
    event_key = f"knowledge-document-indexed:{stable_digest(payload)}"
    existing = session.query(KnowledgeGraphOutboxEvent).filter_by(
        event_key=event_key,
    ).one_or_none()
    if existing is not None:
        return existing, False
    event = KnowledgeGraphOutboxEvent(
        event_key=event_key,
        event_type="knowledge_document_indexed",
        aggregate_type="kb_document",
        aggregate_id=str(document.id),
        payload=payload,
        state="pending",
        available_at=utcnow_naive(),
    )
    session.add(event)
    return event, True


def _job_identity(payload: dict) -> dict:
    required = (
        "document_id", "content_sha256", "schema_version", "backend_name",
        "extractor_version", "backend_config_digest",
    )
    missing = [name for name in required if payload.get(name) in (None, "")]
    if missing:
        raise OutboxPayloadError(f"outbox payload missing: {', '.join(missing)}")
    return {
        "document_id": int(payload["document_id"]),
        "content_sha256": str(payload["content_sha256"]),
        "schema_version": str(payload["schema_version"]),
        "backend_name": str(payload["backend_name"]),
        "extractor_version": str(payload["extractor_version"]),
        "backend_config_digest": str(payload["backend_config_digest"]),
    }


def materialize_outbox_event(
    session,
    event: KnowledgeGraphOutboxEvent,
    *,
    now: datetime | None = None,
) -> tuple[KnowledgeGraphExtractionJob, bool]:
    """Idempotently turn one delivery into one extraction job."""
    if event.event_type != "knowledge_document_indexed":
        raise OutboxPayloadError(f"unsupported outbox event: {event.event_type}")
    identity = _job_identity(dict(event.payload or {}))
    lookup = {name: identity[name] for name in (
        "document_id", "content_sha256", "schema_version", "backend_name",
        "extractor_version",
    )}
    existing = session.query(KnowledgeGraphExtractionJob).filter_by(**lookup).one_or_none()
    created = existing is None
    job = existing or KnowledgeGraphExtractionJob(**identity)
    if created:
        job.available_at = now or utcnow_naive()
        session.add(job)
    event.state = "published"
    event.published_at = now or utcnow_naive()
    event.lease_owner = None
    event.lease_expires_at = None
    event.last_error_code = None
    event.last_error_message = None
    session.flush()
    return job, created


class KnowledgeGraphOutboxDispatcher:
    def __init__(self, session, *, clock: Callable[[], datetime] = utcnow_naive):
        self.session = session
        self.clock = clock

    def dispatch(self, *, limit: int = 100, document_id: int | None = None) -> dict[str, int]:
        if not 1 <= limit <= 1000:
            raise ValueError("outbox dispatch limit must be between 1 and 1000")
        now = self.clock()
        query = (
            self.session.query(KnowledgeGraphOutboxEvent)
            .filter(
                KnowledgeGraphOutboxEvent.event_type == "knowledge_document_indexed",
                True if document_id is None else KnowledgeGraphOutboxEvent.payload["document_id"].as_integer() == document_id,
                KnowledgeGraphOutboxEvent.state.in_(("pending", "retry")),
                KnowledgeGraphOutboxEvent.available_at <= now,
            )
            .order_by(KnowledgeGraphOutboxEvent.available_at, KnowledgeGraphOutboxEvent.id)
            .limit(limit)
        )
        if self.session.get_bind().dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        events = query.all()
        counts = {"selected": len(events), "created": 0, "reused": 0, "failed": 0}
        for event in events:
            try:
                _, created = materialize_outbox_event(self.session, event, now=now)
            except OutboxPayloadError as exc:
                event.state = "dead_letter"
                event.attempt_count += 1
                event.last_error_code = "invalid_payload"
                event.last_error_message = str(exc)[:1000]
                counts["failed"] += 1
            else:
                counts["created" if created else "reused"] += 1
        self.session.flush()
        return counts


class SqlAlchemyGraphJobExecutor:
    """Lease-based, multi-worker-safe job executor for PostgreSQL/SQLite tests."""

    def __init__(self, session, *, clock: Callable[[], datetime] = utcnow_naive):
        self.session = session
        self.clock = clock

    def claim(
        self, *, worker_id: str, limit: int, lease_seconds: int, document_id: int | None = None,
    ) -> Sequence[KnowledgeGraphExtractionJob]:
        if not worker_id or not 1 <= limit <= 1000 or lease_seconds <= 0:
            raise ValueError("valid worker_id, limit and lease_seconds are required")
        now = self.clock()
        claimable = or_(
            and_(
                KnowledgeGraphExtractionJob.state.in_(("pending", "retry")),
                KnowledgeGraphExtractionJob.available_at <= now,
            ),
            and_(
                KnowledgeGraphExtractionJob.state == "running",
                KnowledgeGraphExtractionJob.lease_expires_at <= now,
            ),
        )
        scope = () if document_id is None else (KnowledgeGraphExtractionJob.document_id == document_id,)
        exhausted_query = self.session.query(KnowledgeGraphExtractionJob).filter(
            claimable, *scope,
            KnowledgeGraphExtractionJob.attempt_count
            >= KnowledgeGraphExtractionJob.max_attempts,
        )
        if self.session.get_bind().dialect.name == "postgresql":
            exhausted_query = exhausted_query.with_for_update(skip_locked=True)
        for exhausted in exhausted_query.all():
            exhausted.state = "dead_letter"
            exhausted.failure_code = exhausted.failure_code or "attempts_exhausted"
            exhausted.retryable = False
            exhausted.finished_at = now
            self._clear_lease(exhausted)
        query = (
            self.session.query(KnowledgeGraphExtractionJob)
            .filter(
                claimable, *scope,
                KnowledgeGraphExtractionJob.attempt_count
                < KnowledgeGraphExtractionJob.max_attempts,
            )
            .order_by(
                KnowledgeGraphExtractionJob.priority.desc(),
                KnowledgeGraphExtractionJob.available_at,
                KnowledgeGraphExtractionJob.id,
            )
            .limit(limit)
        )
        if self.session.get_bind().dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        jobs = query.all()
        for job in jobs:
            job.state = "running"
            job.lease_owner = worker_id
            job.lease_expires_at = now + timedelta(seconds=lease_seconds)
            job.heartbeat_at = now
            job.attempt_count += 1
            job.started_at = job.started_at or now
            job.failure_code = None
            job.failure_message = None
        self.session.flush()
        return tuple(jobs)

    def renew(self, *, worker_id: str, job_id: str, lease_seconds: int) -> bool:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = self.clock()
        job = self.session.get(KnowledgeGraphExtractionJob, int(job_id))
        if not self._owns_live_lease(job, worker_id, now):
            return False
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        self.session.flush()
        return True

    def complete(self, *, worker_id: str, job_id: str, result_digest: str) -> bool:
        if not result_digest:
            raise ValueError("result_digest is required")
        now = self.clock()
        job = self.session.get(KnowledgeGraphExtractionJob, int(job_id))
        if not self._owns_live_lease(job, worker_id, now):
            return False
        job.state = "completed"
        job.result_digest = result_digest
        job.finished_at = now
        job.retryable = False
        self._clear_lease(job)
        self.session.flush()
        return True

    def fail(
        self,
        *,
        worker_id: str,
        job_id: str,
        error_code: str,
        retryable: bool,
    ) -> bool:
        if not error_code:
            raise ValueError("error_code is required")
        now = self.clock()
        job = self.session.get(KnowledgeGraphExtractionJob, int(job_id))
        if not self._owns_live_lease(job, worker_id, now):
            return False
        job.failure_code = error_code
        job.failure_message = None
        job.retryable = bool(retryable)
        if retryable and job.attempt_count < job.max_attempts:
            backoff_seconds = min(2 ** max(job.attempt_count - 1, 0), 3600)
            job.state = "retry"
            job.available_at = now + timedelta(seconds=backoff_seconds)
        else:
            job.state = "dead_letter"
            job.finished_at = now
        self._clear_lease(job)
        self.session.flush()
        return True

    @staticmethod
    def _owns_live_lease(job, worker_id: str, now: datetime) -> bool:
        return bool(
            job is not None
            and job.state == "running"
            and job.lease_owner == worker_id
            and job.lease_expires_at is not None
            and job.lease_expires_at > now
        )

    @staticmethod
    def _clear_lease(job) -> None:
        job.lease_owner = None
        job.lease_expires_at = None
        job.heartbeat_at = None
