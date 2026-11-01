"""Read-only current source/actor adapters, independent of application initialization."""
import hashlib
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.pool import NullPool
from .contracts import stable_digest


class PublishedResearchSources:
    def __init__(self, database_uri, upload_root):
        self.engine = sa.create_engine(database_uri, poolclass=NullPool, connect_args={"connect_timeout": 4,
            "options": "-c default_transaction_read_only=on -c statement_timeout=8000 -c lock_timeout=1000"})
        if self.engine.dialect.name != "postgresql":
            raise ValueError("M1_current_source_adapter_requires_readonly_postgresql")
        self.upload_root = Path(upload_root).resolve()
        self.metrics = {"metadata_queries": 0, "source_files_hashed": 0, "source_bytes_hashed": 0}

    def __call__(self, document_id, owner_id):
        return self.lookup_many([document_id], owner_id).get(document_id)

    def lookup_many(self, document_ids, owner_id, *, require_academic=True):
        if not document_ids:
            return {}
        document_ids = sorted(set(document_ids))
        if len(document_ids) > 200 or any(type(value) is not int or value <= 0 for value in document_ids):
            raise ValueError("current_source_batch_exceeds_200")
        with self.engine.connect() as connection:
            if connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
                raise ValueError("source_database_not_read_only")
            statement = sa.text("SELECT id,doc_name,title,file_hash,file_path,status,processing_stage,review_status,visibility_scope,document_kind,chunk_count FROM kb_document WHERE id IN :ids").bindparams(sa.bindparam("ids", expanding=True))
            rows = connection.execute(statement, {"ids": document_ids}).mappings().all()
            self.metrics["metadata_queries"] += 1
        return {row["id"]: self._validate_source(row, require_academic=require_academic) for row in rows}

    def _validate_source(self, row, *, require_academic):
        kind_allowed = row["document_kind"] == "academic_paper" if require_academic else row["document_kind"] in {"academic_paper", "standard", "policy", "method_guideline"}
        result = {"content_sha256": row["file_hash"], "review_status": row["review_status"], "visibility_scope": row["visibility_scope"],
                  "document_kind": row["document_kind"],
                  "title": row["title"] or row["doc_name"],
                  "completed": row["status"] == 1 and row["processing_stage"] == "completed" and kind_allowed and row["chunk_count"] > 0,
                  "chunk_count": row["chunk_count"], "version": stable_digest({"file_hash": row["file_hash"], "kind": row["document_kind"], "chunks": row["chunk_count"]}),
                  "source_bytes_valid": False}
        if not result["completed"] or result["review_status"] != "approved" or result["visibility_scope"] != "public":
            return result
        path = Path(row["file_path"])
        if not path.is_absolute():
            path = self.upload_root/path
        path = path.resolve()
        if self.upload_root not in path.parents:
            return result
        try:
            digest = hashlib.sha256()
            self.metrics["source_files_hashed"] += 1
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024*1024), b""):
                    digest.update(block)
                    self.metrics["source_bytes_hashed"] += len(block)
            result["source_bytes_valid"] = digest.hexdigest() == row["file_hash"]
        except OSError:
            pass
        return result

    def actor(self, identity):
        from framework.api.routes.literature_evidence import EvidenceActor
        try:
            identifier = int(identity)
        except (TypeError, ValueError):
            return None
        with self.engine.connect() as connection:
            row = connection.execute(sa.text("SELECT id,role,status FROM sys_user WHERE id=:id"), {"id": identifier}).mappings().first()
        return EvidenceActor(row["id"], row["role"], row["status"] == 1) if row else None

    def close(self):
        self.engine.dispose()
