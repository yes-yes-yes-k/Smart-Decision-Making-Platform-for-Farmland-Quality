"""Explicitly migrated research read model; no graph publication tables."""
from datetime import datetime, timezone
import json
import re
import uuid

import sqlalchemy as sa

from .contracts import SourceChunk, stable_digest
from .research_records import validate_record

SCHEMA = "literature-evidence-store-v1"
metadata = sa.MetaData()
migration = sa.Table("literature_migration", metadata, sa.Column("version", sa.String(80), primary_key=True))
sources = sa.Table("literature_source", metadata,
    sa.Column("document_id", sa.Integer, primary_key=True), sa.Column("content_sha256", sa.String(64), nullable=False),
    sa.Column("revision", sa.Integer, nullable=False), sa.Column("payload", sa.JSON, nullable=False))
chunks = sa.Table("literature_chunk", metadata,
    sa.Column("id", sa.String(64), primary_key=True), sa.Column("document_id", sa.Integer, sa.ForeignKey("literature_source.document_id"), nullable=False),
    sa.Column("content_sha256", sa.String(64), nullable=False), sa.Column("chunk_index", sa.Integer, nullable=False),
    sa.Column("page", sa.Integer, nullable=False), sa.Column("content", sa.Text, nullable=False), sa.Column("search_text", sa.Text, nullable=False),
    sa.UniqueConstraint("document_id", "content_sha256", "chunk_index"))
records = sa.Table("literature_record", metadata,
    sa.Column("id", sa.String(90), primary_key=True), sa.Column("document_id", sa.Integer, sa.ForeignKey("literature_source.document_id"), nullable=False),
    sa.Column("content_sha256", sa.String(64), nullable=False), sa.Column("revision", sa.Integer, nullable=False),
    sa.Column("review_status", sa.String(20), nullable=False), sa.Column("payload", sa.JSON, nullable=False))
jobs = sa.Table("literature_comparison", metadata,
    sa.Column("id", sa.String(40), primary_key=True), sa.Column("owner_id", sa.Integer, nullable=False),
    sa.Column("fingerprint", sa.String(64), nullable=False), sa.Column("request", sa.JSON, nullable=False),
    sa.Column("signature", sa.String(64), nullable=False), sa.Column("state", sa.String(25), nullable=False),
    sa.Column("lease", sa.String(40)), sa.Column("lease_until", sa.Float), sa.Column("attempts", sa.Integer, nullable=False),
    sa.Column("result", sa.JSON), sa.Column("error", sa.String(80)), sa.Column("created_at", sa.Float, nullable=False),
    sa.Column("updated_at", sa.Float, nullable=False), sa.UniqueConstraint("owner_id", "fingerprint"))
sa.Index("idx_literature_comparison_owner_fingerprint", jobs.c.owner_id, jobs.c.fingerprint, jobs.c.state)
sa.Index("idx_literature_record_source_state", records.c.document_id, records.c.content_sha256, records.c.review_status)


def tokens(text):
    words = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.casefold())
    result = []
    for word in words:
        if re.fullmatch(r"[\u3400-\u9fff]+", word):
            result.extend(word[i:i+2] for i in range(max(1, len(word)-1)))
        else:
            result.append(word)
    return list(dict.fromkeys(result))


def migrate(engine, *, apply=False):
    """Caller explicitly selects a database; preview never creates tables."""
    if engine.dialect.name not in {"sqlite", "postgresql"}:
        raise ValueError("research_store_dialect_unsupported")
    existing = set(sa.inspect(engine).get_table_names())
    missing = sorted(set(metadata.tables)-existing)
    if apply:
        if migration.name in existing:
            with engine.connect() as connection:
                if connection.execute(sa.select(migration.c.version)).scalars().all() != [SCHEMA]:
                    raise ValueError("research_schema_version_mismatch")
        metadata.create_all(engine)
        with engine.begin() as connection:
            current = connection.execute(sa.select(migration.c.version)).scalars().all()
            if current and current != [SCHEMA]:
                raise ValueError("research_schema_version_mismatch")
            if not current:
                connection.execute(migration.insert().values(version=SCHEMA))
            if engine.dialect.name == "sqlite":
                connection.exec_driver_sql("CREATE VIRTUAL TABLE IF NOT EXISTS literature_chunk_fts USING fts5(chunk_id UNINDEXED,search_text)")
            elif engine.dialect.name == "postgresql":
                connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_literature_chunk_search ON literature_chunk USING gin(to_tsvector('simple',search_text))")
            else:
                raise ValueError("research_store_dialect_unsupported")
    return {"schema": SCHEMA, "missing_tables": missing, "applied": apply}


def rollback_empty(engine):
    """Rollback only empty research tables; never drop unrelated tables."""
    with engine.connect() as connection:
        for table in (sources, chunks, records, jobs):
            if connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one():
                raise ValueError("nonempty_research_rollback_requires_export_and_separate_plan")
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE IF EXISTS literature_chunk_fts")
    metadata.drop_all(engine)


class ResearchStore:
    def __init__(self, engine):
        self.engine = engine

    def require_schema(self):
        tables = sa.inspect(self.engine).get_table_names()
        if not set(metadata.tables) <= set(tables):
            raise ValueError("research_explicit_migration_required")
        with self.engine.connect() as connection:
            if connection.execute(sa.select(migration.c.version)).scalars().all() != [SCHEMA]:
                raise ValueError("research_schema_version_mismatch")

    def source(self, document_id):
        with self.engine.connect() as connection:
            row = connection.execute(sa.select(sources).where(sources.c.document_id == document_id)).mappings().first()
            return dict(row) if row else None

    def source_ids(self):
        with self.engine.connect() as connection:
            return connection.execute(sa.select(sources.c.document_id).order_by(sources.c.document_id)).scalars().all()

    def sources_many(self, document_ids):
        with self.engine.connect() as connection:
            return {row["document_id"]: dict(row) for row in connection.execute(
                sa.select(sources).where(sources.c.document_id.in_(document_ids))).mappings()}

    def import_source(self, document):
        self.require_schema()
        if document["verification"]["state"] != "verified" or document["review_status"] != "approved" or document["visibility_scope"] != "public":
            raise ValueError("unverified_or_unpublished_research_source")
        document_id, digest = document["document_id"], document["content_sha256"]
        if type(document_id) is not int or document_id <= 0:
            raise ValueError("invalid_research_document_id")
        validated = [SourceChunk(**item) for item in document["chunks"]]
        if not validated or any(item.document_id != document_id or item.content_sha256 != digest or item.page is None for item in validated):
            raise ValueError("source_chunk_binding_invalid")
        if [item.chunk_index for item in validated] != list(range(len(validated))):
            raise ValueError("source_chunk_sequence_invalid")
        public = {key: document[key] for key in ("document_id", "title", "content_sha256", "document_kind", "visibility_scope", "review_status")}
        public["chunks_sha256"] = stable_digest(document["chunks"])
        public["chunk_count"] = len(validated)
        public["extraction_summary"] = document.get("extraction_summary", {"state": "not_processed", "coverage": "unknown"})
        with self.engine.begin() as connection:
            old = connection.execute(sa.select(sources).where(sources.c.document_id == document_id)).mappings().first()
            if old and old["payload"] == public:
                return {"changed": False}
            if old and old["content_sha256"] == digest and old["payload"].get("chunks_sha256") != public["chunks_sha256"]:
                raise ValueError("same_file_hash_chunk_snapshot_changed_requires_explicit_reparse_migration")
            revision = old["revision"]+1 if old else 1
            if old:
                connection.execute(sources.update().where(sources.c.document_id == document_id).values(content_sha256=digest, revision=revision, payload=public))
            else:
                connection.execute(sources.insert().values(document_id=document_id, content_sha256=digest, revision=revision, payload=public))
            for item in validated:
                identity = stable_digest({"document_id": document_id, "hash": digest, "index": item.chunk_index})
                existing = connection.execute(sa.select(chunks.c.id).where(chunks.c.id == identity)).first()
                if existing:
                    continue
                search = " ".join(tokens(item.content))
                connection.execute(chunks.insert().values(id=identity, document_id=document_id, content_sha256=digest,
                    chunk_index=item.chunk_index, page=item.page, content=item.content, search_text=search))
                if self.engine.dialect.name == "sqlite":
                    connection.execute(sa.text("INSERT INTO literature_chunk_fts(chunk_id,search_text) VALUES(:id,:text)"), {"id": identity, "text": search})
        return {"changed": True}

    def source_chunks(self, document_id, digest):
        with self.engine.connect() as connection:
            values = connection.execute(sa.select(chunks).where(chunks.c.document_id == document_id, chunks.c.content_sha256 == digest).order_by(chunks.c.chunk_index)).mappings()
            return {row["chunk_index"]: SourceChunk(document_id, digest, row["chunk_index"], row["content"], row["page"]) for row in values}

    def source_chunk(self, document_id, digest, index):
        with self.engine.connect() as connection:
            row = connection.execute(sa.select(chunks).where(chunks.c.document_id == document_id, chunks.c.content_sha256 == digest,
                chunks.c.chunk_index == index)).mappings().first()
            return SourceChunk(document_id, digest, index, row["content"], row["page"]) if row else None

    def add_record(self, record):
        self.require_schema()
        source = self.source(record["document_id"])
        if not source or source["content_sha256"] != record["content_sha256"]:
            raise ValueError("record_source_not_current")
        validate_record(record, self.source_chunks(record["document_id"], record["content_sha256"]))
        with self.engine.begin() as connection:
            old = connection.execute(sa.select(records).where(records.c.id == record["id"])).mappings().first()
            if old:
                if old["payload"] != record:
                    raise ValueError("research_record_identity_collision")
                return False
            connection.execute(records.insert().values(id=record["id"], document_id=record["document_id"], content_sha256=record["content_sha256"],
                revision=1, review_status="pending", payload=record))
        return True

    def reject_record(self, record_id):
        with self.engine.begin() as connection:
            connection.execute(records.update().where(records.c.id == record_id, records.c.review_status == "pending").values(review_status="rejected", revision=records.c.revision+1))

    def current_records(self, document_ids):
        with self.engine.connect() as connection:
            query = sa.select(records).join(sources, sa.and_(sources.c.document_id == records.c.document_id, sources.c.content_sha256 == records.c.content_sha256)).where(records.c.document_id.in_(document_ids), records.c.review_status == "pending").order_by(records.c.id)
            return [dict(row) for row in connection.execute(query).mappings()]

    def search(self, query, document_ids, limit=20):
        words = tokens(query)[:40]
        if not words or not document_ids:
            return []
        with self.engine.connect() as connection:
            if self.engine.dialect.name == "sqlite":
                # Tokens are alphanumeric/CJK only; syntax remains data parameters.
                match = " OR ".join('"'+word+'"' for word in words)
                statement = sa.text("SELECT c.* FROM literature_chunk_fts f JOIN literature_chunk c ON c.id=f.chunk_id JOIN literature_source s ON s.document_id=c.document_id AND s.content_sha256=c.content_sha256 WHERE literature_chunk_fts MATCH :query AND c.document_id IN :documents ORDER BY bm25(literature_chunk_fts),c.id LIMIT :limit").bindparams(sa.bindparam("documents", expanding=True))
                return [dict(row) for row in connection.execute(statement, {"query": match, "documents": document_ids, "limit": limit}).mappings()]
            match = sa.func.to_tsvector("simple", chunks.c.search_text).op("@@")(sa.func.to_tsquery("simple", " | ".join(words)))
            query = sa.select(chunks).join(sources, sa.and_(sources.c.document_id == chunks.c.document_id, sources.c.content_sha256 == chunks.c.content_sha256)).where(chunks.c.document_id.in_(document_ids), match).order_by(chunks.c.id).limit(limit)
            return [dict(row) for row in connection.execute(query).mappings()]

    def job(self, identifier, owner_id):
        with self.engine.connect() as connection:
            row = connection.execute(sa.select(jobs).where(jobs.c.id == identifier, jobs.c.owner_id == owner_id)).mappings().first()
            return dict(row) if row else None
