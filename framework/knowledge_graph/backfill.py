"""Resumable, idempotent historical graph-extraction backfill."""
from __future__ import annotations

from framework.models.document import Document
from framework.models.knowledge_graph import KnowledgeGraphBackfillRun

from .contracts import stable_digest
from .extraction_config import backend_config_digest
from .jobs import (
    DEFAULT_BACKEND_NAME,
    DEFAULT_EXTRACTOR_VERSION,
    document_is_graph_eligible,
    enqueue_document_indexed,
)
from .schema import load_graph_schema


class HistoricalGraphBackfill:
    def __init__(self, session):
        self.session = session

    def dry_run(self, *, after_document_id: int = 0, limit: int = 1000) -> dict:
        rows = Document.query.filter(Document.id > int(after_document_id)).order_by(
            Document.id,
        ).limit(max(1, min(int(limit), 100_000))).all()
        eligible = [row.id for row in rows if document_is_graph_eligible(row)]
        return {
            "dry_run": True, "scanned": len(rows), "eligible": len(eligible),
            "eligible_document_ids": eligible,
            "checkpoint_document_id": rows[-1].id if rows else after_document_id,
        }

    def run_batch(
        self, *, run_key: str, created_by: int, batch_size: int = 100,
        schema_version: str | None = None,
        backend_name: str = DEFAULT_BACKEND_NAME,
        extractor_version: str = DEFAULT_EXTRACTOR_VERSION,
    ) -> tuple[KnowledgeGraphBackfillRun, dict]:
        key = str(run_key or "").strip()
        if not key or len(key) > 128:
            raise ValueError("run_key is required and limited to 128 characters")
        size = max(1, min(int(batch_size), 1000))
        schema_version = schema_version or load_graph_schema().schema_version
        config = {
            "batch_size": size, "schema_version": schema_version,
            "backend_name": backend_name, "extractor_version": extractor_version,
            "backend_config_digest": backend_config_digest(backend_name, extractor_version, schema_version),
        }
        config_digest = stable_digest(config)
        run = KnowledgeGraphBackfillRun.query.filter_by(run_key=key).one_or_none()
        if run is None:
            run = KnowledgeGraphBackfillRun(
                run_key=key, schema_version=schema_version,
                backend_name=backend_name, extractor_version=extractor_version,
                config_snapshot={**config, "digest": config_digest},
                created_by=created_by,
            )
            self.session.add(run)
            self.session.flush()
        elif (run.config_snapshot or {}).get("digest") != config_digest:
            raise ValueError("run_key already exists with different configuration")
        if run.state == "completed":
            return run, {"selected": 0, "created": 0, "reused": 0, "skipped": 0}

        rows = Document.query.filter(
            Document.id > run.checkpoint_document_id,
        ).order_by(Document.id).limit(size).all()
        counts = {"selected": len(rows), "created": 0, "reused": 0, "skipped": 0}
        for document in rows:
            if not document_is_graph_eligible(document):
                counts["skipped"] += 1
            else:
                run.eligible_count += 1
                _, created = enqueue_document_indexed(
                    self.session, document, schema_version=schema_version,
                    backend_name=backend_name,
                    extractor_version=extractor_version,
                    backend_config_digest=backend_config_digest(
                        backend_name, extractor_version, schema_version,
                    ),
                )
                counts["created" if created else "reused"] += 1
            run.checkpoint_document_id = document.id
        run.created_count += counts["created"]
        run.reused_count += counts["reused"]
        run.skipped_count += counts["skipped"]
        if len(rows) < size:
            run.state = "completed"
        self.session.flush()
        return run, counts
