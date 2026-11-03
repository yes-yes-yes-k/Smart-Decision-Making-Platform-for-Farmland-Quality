"""Isolated PostgreSQL benchmark for 100k leased graph extraction jobs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import hashlib
from time import perf_counter
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import sessionmaker

from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphExtractionJob, KnowledgeGraphOutboxEvent,
)

from .contracts import stable_digest
from .jobs import KnowledgeGraphOutboxDispatcher, SqlAlchemyGraphJobExecutor
from .schema import load_graph_schema


class JobBenchmarkError(RuntimeError):
    pass


def _safe_namespace(namespace: str) -> str:
    value = str(namespace or "").strip().lower()
    if not value.startswith("synthetic-") or not all(
        character.isalnum() or character in "-_" for character in value
    ):
        raise JobBenchmarkError("namespace must start with synthetic- and use safe characters")
    return value


def _assert_isolated_database(
    engine, *, require_postgresql: bool, require_empty: bool = True,
) -> str:
    dialect = engine.dialect.name
    database = str(engine.url.database or "")
    if require_postgresql and dialect != "postgresql":
        raise JobBenchmarkError("production job benchmark requires PostgreSQL")
    if "benchmark" not in database.casefold():
        raise JobBenchmarkError("refusing job benchmark outside a database named for benchmark use")
    if require_empty:
        with engine.connect() as connection:
            for table in (KnowledgeGraphExtractionJob, KnowledgeGraphOutboxEvent):
                count = connection.execute(select(func.count()).select_from(table)).scalar_one()
                if count:
                    raise JobBenchmarkError(
                        f"isolated benchmark table is not empty: {table.__tablename__}"
                    )
    return dialect


def _batched(total: int, batch_size: int):
    for start in range(0, total, batch_size):
        yield start, min(total, start + batch_size)


def _dispatch_all(session_factory, total: int, batch_size: int) -> dict[str, int]:
    totals = {"selected": 0, "created": 0, "reused": 0, "failed": 0}
    with session_factory() as session:
        while totals["selected"] < total:
            counts = KnowledgeGraphOutboxDispatcher(session).dispatch(limit=batch_size)
            session.commit()
            for key in totals:
                totals[key] += counts[key]
            if counts["selected"] == 0:
                break
    return totals


def _worker(session_factory, worker_id: str, batch_size: int) -> int:
    completed = 0
    with session_factory() as session:
        executor = SqlAlchemyGraphJobExecutor(session)
        while True:
            jobs = executor.claim(
                worker_id=worker_id, limit=batch_size, lease_seconds=300,
            )
            session.commit()
            if not jobs:
                break
            for job in jobs:
                digest = stable_digest({
                    "benchmark": True, "job_id": job.id,
                    "document_id": job.document_id,
                })
                if not executor.complete(
                    worker_id=worker_id, job_id=str(job.id), result_digest=digest,
                ):
                    raise JobBenchmarkError("worker lost a live lease before completion")
                completed += 1
            session.commit()
    return completed


def run_job_conservation_benchmark(
    engine,
    *,
    namespace: str,
    job_count: int = 100_000,
    worker_concurrency: int = 4,
    batch_size: int = 1_000,
    require_postgresql: bool = True,
) -> dict[str, Any]:
    namespace = _safe_namespace(namespace)
    if job_count <= 0 or worker_concurrency <= 0 or not 1 <= batch_size <= 1_000:
        raise JobBenchmarkError("positive job count/concurrency and batch_size <= 1000 required")
    dialect = _assert_isolated_database(engine, require_postgresql=require_postgresql)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    schema_version = load_graph_schema().schema_version
    backend = "deterministic-capacity-worker"
    extractor_version = "1.0.0"
    backend_config_digest = stable_digest({
        "namespace": namespace, "backend": backend,
        "extractor_version": extractor_version,
    })
    started_at = datetime.now(UTC)
    started = perf_counter()

    with engine.begin() as connection:
        for start, stop in _batched(job_count, batch_size):
            connection.execute(Document.__table__.insert(), [
                {
                    "doc_name": f"{namespace}-{index}.pdf",
                    "file_path": f"{namespace}/{index}.pdf",
                    "file_type": "pdf", "file_size": 1, "chunk_count": 1,
                    "status": Document.STATUS_COMPLETED, "category": "other",
                    "visibility_scope": "public",
                    "file_hash": hashlib.sha256(f"{namespace}:{index}".encode()).hexdigest(),
                    "idempotency_key": f"{namespace}:document:{index}",
                    "document_kind": "academic_paper",
                    "processing_stage": "completed",
                    "review_status": Document.REVIEW_APPROVED,
                    "create_by": 0,
                }
                for index in range(start, stop)
            ])
    with engine.connect() as connection:
        document_rows = connection.execute(
            select(Document.id, Document.file_hash)
            .where(Document.idempotency_key.like(f"{namespace}:document:%"))
            .order_by(Document.id)
        ).all()
    if len(document_rows) != job_count:
        raise JobBenchmarkError("synthetic document seed count mismatch")

    with engine.begin() as connection:
        for start, stop in _batched(job_count, batch_size):
            connection.execute(KnowledgeGraphOutboxEvent.__table__.insert(), [
                {
                    "event_key": f"{namespace}:event:{index}",
                    "event_type": "knowledge_document_indexed",
                    "aggregate_type": "kb_document",
                    "aggregate_id": str(document_rows[index].id),
                    "payload": {
                        "document_id": document_rows[index].id,
                        "content_sha256": document_rows[index].file_hash,
                        "schema_version": schema_version,
                        "backend_name": backend,
                        "extractor_version": extractor_version,
                        "backend_config_digest": backend_config_digest,
                    },
                    "state": "pending", "attempt_count": 0,
                }
                for index in range(start, stop)
            ])

    initial_delivery = _dispatch_all(session_factory, job_count, batch_size)
    if initial_delivery != {
        "selected": job_count, "created": job_count, "reused": 0, "failed": 0,
    }:
        raise JobBenchmarkError(f"initial delivery count mismatch: {initial_delivery}")

    with engine.begin() as connection:
        connection.execute(
            update(KnowledgeGraphOutboxEvent)
            .where(KnowledgeGraphOutboxEvent.event_key.like(f"{namespace}:event:%"))
            .values(state="pending", published_at=None)
        )
    duplicate_delivery = _dispatch_all(session_factory, job_count, batch_size)
    if duplicate_delivery != {
        "selected": job_count, "created": 0, "reused": job_count, "failed": 0,
    }:
        raise JobBenchmarkError(f"duplicate delivery count mismatch: {duplicate_delivery}")

    crash_batch = min(batch_size, job_count)
    with session_factory() as session:
        crashed = SqlAlchemyGraphJobExecutor(session).claim(
            worker_id=f"{namespace}-crashed", limit=crash_batch, lease_seconds=300,
        )
        session.commit()
        crashed_ids = [job.id for job in crashed]
    with engine.begin() as connection:
        connection.execute(
            update(KnowledgeGraphExtractionJob)
            .where(KnowledgeGraphExtractionJob.id.in_(crashed_ids))
            .values(
                lease_expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
            )
        )

    with ThreadPoolExecutor(max_workers=worker_concurrency) as pool:
        completed_by_workers = sum(pool.map(
            lambda index: _worker(
                session_factory, f"{namespace}-worker-{index}", batch_size,
            ),
            range(worker_concurrency),
        ))

    with session_factory() as session:
        state_counts = dict(session.execute(
            select(KnowledgeGraphExtractionJob.state, func.count())
            .group_by(KnowledgeGraphExtractionJob.state)
        ).all())
        unique_jobs = session.scalar(select(func.count()).select_from(KnowledgeGraphExtractionJob))
        duplicate_groups = session.execute(
            select(func.count())
            .select_from(KnowledgeGraphExtractionJob)
            .group_by(
                KnowledgeGraphExtractionJob.document_id,
                KnowledgeGraphExtractionJob.content_sha256,
                KnowledgeGraphExtractionJob.schema_version,
                KnowledgeGraphExtractionJob.backend_name,
                KnowledgeGraphExtractionJob.extractor_version,
            )
            .having(func.count() > 1)
        ).all()
        restarted = session.scalar(
            select(func.count()).select_from(KnowledgeGraphExtractionJob)
            .where(KnowledgeGraphExtractionJob.attempt_count >= 2)
        )
    succeeded = int(state_counts.get("completed", 0))
    dead_letter = int(state_counts.get("dead_letter", 0))
    failed = sum(
        int(count) for state, count in state_counts.items()
        if state not in {"completed", "dead_letter"}
    )
    elapsed = perf_counter() - started
    production_eligible = (
        dialect == "postgresql" and job_count >= 100_000
        and worker_concurrency >= 2 and succeeded + dead_letter == unique_jobs
        and not duplicate_groups and restarted >= crash_batch
    )
    return {
        "schema": "knowledge-platform-job-conservation-v1",
        "status": "completed",
        "namespace": namespace,
        "database_backend": dialect,
        "production_eligible": production_eligible,
        "unique_jobs": int(unique_jobs),
        "succeeded": succeeded,
        "failed": failed,
        "dead_letter": dead_letter,
        "duplicate_business_effects": len(duplicate_groups),
        "duplicate_delivery_tested": True,
        "worker_restart_tested": restarted >= crash_batch,
        "reclaimed_after_restart": int(restarted),
        "completed_by_workers": completed_by_workers,
        "worker_concurrency": worker_concurrency,
        "initial_delivery": initial_delivery,
        "duplicate_delivery": duplicate_delivery,
        "elapsed_seconds": elapsed,
        "jobs_per_second": job_count / elapsed if elapsed else None,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }


def cleanup_job_benchmark(engine, *, namespace: str) -> dict[str, int]:
    namespace = _safe_namespace(namespace)
    _assert_isolated_database(
        engine, require_postgresql=False, require_empty=False,
    )
    with engine.begin() as connection:
        document_ids = select(Document.id).where(
            Document.idempotency_key.like(f"{namespace}:document:%")
        )
        jobs = connection.execute(
            delete(KnowledgeGraphExtractionJob)
            .where(KnowledgeGraphExtractionJob.document_id.in_(document_ids))
        ).rowcount
        events = connection.execute(
            delete(KnowledgeGraphOutboxEvent)
            .where(KnowledgeGraphOutboxEvent.event_key.like(f"{namespace}:event:%"))
        ).rowcount
        documents = connection.execute(
            delete(Document)
            .where(Document.idempotency_key.like(f"{namespace}:document:%"))
        ).rowcount
    return {"jobs": jobs, "events": events, "documents": documents}
