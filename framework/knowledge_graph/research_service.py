"""Source-first retrieval and durable, cancellable evidence comparisons."""
import time
import uuid

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from .contracts import stable_digest
from .research_records import VERSION
from .research_store import jobs, tokens

GENERATOR = "literal-evidence-comparison-v1"


class ResearchError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


class ResearchService:
    """current_source is a trusted adapter, never supplied by the HTTP caller."""
    def __init__(self, store, current_source, *, graph_lookup=None, corpus_search=None, clock=time.time, lease_seconds=60,
                 max_pending_per_owner=20, max_pending_total=100):
        self.store, self.current_source, self.graph_lookup = store, current_source, graph_lookup
        self.corpus_search = corpus_search
        self.clock, self.lease_seconds = clock, lease_seconds
        if any(type(value) is not int or value < 1 for value in (max_pending_per_owner, max_pending_total)):
            raise ValueError("positive_comparison_queue_limits_required")
        self.max_pending_per_owner, self.max_pending_total = max_pending_per_owner, max_pending_total

    def normalize(self, data):
        if not isinstance(data, dict) or set(data)-{"query", "document_ids", "measure", "indicator", "soil_type", "conditions", "limit"}:
            raise ResearchError("invalid_comparison_request")
        query = data.get("query", "")
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            raise ResearchError("query_required_max_500_characters")
        identifiers = data["document_ids"] if "document_ids" in data else self.store.source_ids()
        if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 10 or any(type(item) is not int or item <= 0 for item in identifiers):
            raise ResearchError("explicit_scope_of_one_to_ten_pilot_documents_required")
        limit = data.get("limit", 20)
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ResearchError("limit_must_be_one_to_thirty")
        result = {"query": query.strip(), "document_ids": sorted(set(identifiers)), "limit": limit}
        for name in ("measure", "indicator", "soil_type", "conditions"):
            value = data.get(name)
            if value is not None and (not isinstance(value, str) or len(value) > 300):
                raise ResearchError("invalid_research_filter")
            result[name] = value.strip() if value and value.strip() else None
        return result

    def snapshot(self, owner_id, request):
        sources, problems = {}, []
        saved_sources = self.store.sources_many(request["document_ids"])
        batch_method = getattr(self.current_source, "lookup_many", None)
        batch, batch_failed = None, False
        if callable(batch_method):
            try:
                batch = batch_method(request["document_ids"], owner_id)
            except Exception:
                batch_failed = True
        for document_id in request["document_ids"]:
            saved = saved_sources.get(document_id)
            try:
                if batch_failed:
                    raise ValueError("source_batch_unavailable")
                live = batch.get(document_id) if batch is not None else self.current_source(document_id, owner_id)
            except Exception:
                live = None
                problems.append({"document_id": document_id, "reason": "source_verification_unavailable"})
                continue
            if not saved or not live or live.get("visibility_scope") != "public" or live.get("review_status") != "approved" or not live.get("completed", False):
                problems.append({"document_id": document_id, "reason": "source_not_currently_available"}); continue
            if live.get("content_sha256") != saved["content_sha256"] or live.get("source_bytes_valid") is not True:
                problems.append({"document_id": document_id, "reason": "source_version_changed_or_unverified"}); continue
            if live.get("chunk_count") is not None and live["chunk_count"] != saved["payload"]["chunk_count"]:
                problems.append({"document_id": document_id, "reason": "source_chunk_snapshot_changed"}); continue
            sources[document_id] = {"stored": saved, "live": {key: live.get(key) for key in ("content_sha256", "visibility_scope", "review_status", "completed", "source_bytes_valid", "version")}}
        candidates = self.store.current_records(list(sources)) if sources else []
        signature = stable_digest({"owner_id": owner_id, "generator": GENERATOR, "record_schema": VERSION,
            "sources": sources, "source_problems": problems, "candidates": [{"id": row["id"], "revision": row["revision"],
                 "state": row["review_status"], "payload_sha256": stable_digest(row["payload"])} for row in candidates]})
        return sources, candidates, problems, signature

    def search(self, owner_id, data):
        if self.corpus_search is not None:
            if not isinstance(data, dict):
                raise ResearchError("invalid_corpus_request")
            return self.corpus_search.search(owner_id, data)
        request = self.normalize(data)
        sources, _, problems, _ = self.snapshot(owner_id, request)
        hits = self.store.search(request["query"], list(sources), request["limit"])
        graph = {"state": "not_configured", "backend": None, "version": None, "contributing_hits": 0}
        if self.graph_lookup:
            try:
                result = self.graph_lookup(request["query"], list(sources))
                graph.update(state="available", backend=result["backend"], version=result["version"])
                seen = {(row["document_id"], row["chunk_index"]) for row in hits}
                for pointer in result.get("hits", [])[:30]:
                    if len(hits) >= request["limit"]:
                        break
                    document_id, index = pointer.get("document_id"), pointer.get("chunk_index")
                    if document_id not in sources or type(index) is not int or (document_id, index) in seen:
                        continue
                    source = sources[document_id]["stored"]
                    chunk = self.store.source_chunks(document_id, source["content_sha256"]).get(index)
                    if chunk:
                        hits.append({"document_id": document_id, "content_sha256": chunk.content_sha256, "chunk_index": index, "page": chunk.page, "content": chunk.content})
                        seen.add((document_id, index)); graph["contributing_hits"] += 1
                    if len(hits) >= request["limit"]:
                        break
            except Exception:
                graph["state"] = "unavailable"
        # Revalidate immediately before returning source text.
        current, _, changed, _ = self.snapshot(owner_id, request)
        hits = [row for row in hits if row["document_id"] in current and row["content_sha256"] == current[row["document_id"]]["stored"]["content_sha256"]][:request["limit"]]
        return {"state": "partial" if problems or changed else "completed", "sources": [{
            "document_id": row["document_id"], "title": current[row["document_id"]]["stored"]["payload"]["title"],
            "content_sha256": row["content_sha256"], "chunk_index": row["chunk_index"], "page": row["page"], "text": row["content"]} for row in hits],
            "graph": graph, "source_problems": changed or problems, "scope": "registered_M1_papers", "generation_performed": False}

    def read_chunk(self, owner_id, document_id, index, expected_sha):
        if self.store.source(document_id) is None and self.corpus_search is not None:
            return self.corpus_search.read_chunk(owner_id, document_id, index, expected_sha)
        request = {"document_ids": [document_id]}
        sources, _, _, _ = self.snapshot(owner_id, request)
        if document_id not in sources:
            raise ResearchError("source_not_currently_available", 409)
        digest = sources[document_id]["stored"]["content_sha256"]
        if expected_sha != digest:
            raise ResearchError("source_version_mismatch", 409)
        chunk = self.store.source_chunk(document_id, digest, index)
        if chunk is None:
            raise ResearchError("source_chunk_not_found", 404)
        current, _, _, _ = self.snapshot(owner_id, request)
        if document_id not in current:
            raise ResearchError("source_not_currently_available", 409)
        return {"document_id": document_id, "content_sha256": digest, "chunk_index": index,
                "page": chunk.page, "text": chunk.content}

    def submit(self, owner_id, data):
        request = self.normalize(data)
        sources, _, problems, signature = self.snapshot(owner_id, request)
        if not sources:
            raise ResearchError("no_current_authorized_source", 409)
        fingerprint = stable_digest({"request": request, "signature": signature, "owner_id": owner_id})
        now, identifier = self.clock(), str(uuid.uuid4())
        try:
            with self.store.engine.begin() as connection:
                # Serialize admission across processes, not just worker threads.
                # SQLite takes a write reservation even when this DML matches no
                # rows; PostgreSQL uses one transaction-scoped admission lock.
                if connection.dialect.name == "postgresql":
                    connection.execute(sa.text("SELECT pg_advisory_xact_lock(1835819826, 1)"))
                elif connection.dialect.name == "sqlite":
                    connection.execute(jobs.update().where(sa.false()).values(state=jobs.c.state))
                else:
                    raise ResearchError("comparison_queue_backend_not_supported", 503)
                existing = connection.execute(sa.select(jobs.c.id).where(jobs.c.owner_id == owner_id, jobs.c.fingerprint == fingerprint)).scalar()
                if not existing:
                    total, owned = connection.execute(sa.select(sa.func.count(), sa.func.coalesce(sa.func.sum(
                        sa.case((jobs.c.owner_id == owner_id, 1), else_=0)), 0)).select_from(jobs).where(jobs.c.state.in_(["queued", "running"]))).one()
                    if total >= self.max_pending_total or owned >= self.max_pending_per_owner:
                        raise ResearchError("comparison_queue_full_retry_after_processing", 429)
                    connection.execute(jobs.insert().values(id=identifier, owner_id=owner_id, fingerprint=fingerprint, request=request,
                        signature=signature, state="queued", attempts=0, created_at=now, updated_at=now))
            if existing:
                return self.get(owner_id, existing), True
        except IntegrityError:
            with self.store.engine.connect() as connection:
                identifier = connection.execute(sa.select(jobs.c.id).where(jobs.c.owner_id == owner_id, jobs.c.fingerprint == fingerprint)).scalar_one()
            return self.get(owner_id, identifier), True
        return self.get(owner_id, identifier), False

    def get(self, owner_id, identifier):
        row = self.store.job(identifier, owner_id)
        if not row:
            raise ResearchError("comparison_not_found", 404)
        if row["state"] == "completed":
            _, _, _, signature = self.snapshot(owner_id, row["request"])
            if signature != row["signature"]:
                with self.store.engine.begin() as connection:
                    connection.execute(jobs.update().where(jobs.c.id == identifier, jobs.c.state == "completed").values(state="invalidated", result=None,
                        error="source_permissions_version_or_candidates_changed", updated_at=self.clock()))
                row = self.store.job(identifier, owner_id)
        return {key: row[key] for key in ("id", "state", "attempts", "created_at", "updated_at", "error")} | {
            "result": row["result"] if row["state"] == "completed" else None}

    def cancel(self, owner_id, identifier):
        if not self.store.job(identifier, owner_id):
            raise ResearchError("comparison_not_found", 404)
        with self.store.engine.begin() as connection:
            connection.execute(jobs.update().where(jobs.c.id == identifier, jobs.c.owner_id == owner_id,
                jobs.c.state.in_(["queued", "running"])).values(state="cancelled", result=None, lease=None, lease_until=None, updated_at=self.clock()))
        return self.get(owner_id, identifier)

    def run_once(self, *, before_commit=None, timeout=30):
        now, lease = self.clock(), str(uuid.uuid4())
        eligible = sa.or_(jobs.c.state == "queued", sa.and_(jobs.c.state == "running", jobs.c.lease_until < now))
        with self.store.engine.begin() as connection:
            connection.execute(jobs.update().where(jobs.c.state == "running", jobs.c.lease_until < now, jobs.c.attempts >= 3).values(
                state="failed", result=None, lease=None, lease_until=None, error="comparison_recovery_attempts_exhausted", updated_at=now))
            row = connection.execute(sa.select(jobs).where(eligible, jobs.c.attempts < 3).order_by(jobs.c.created_at).limit(1)).mappings().first()
            if not row:
                return {"state": "idle"}
            claimed = connection.execute(jobs.update().where(jobs.c.id == row["id"], eligible, jobs.c.attempts < 3).values(
                state="running", lease=lease, lease_until=now+self.lease_seconds, attempts=jobs.c.attempts+1, updated_at=now))
            if claimed.rowcount != 1:
                return {"state": "lease_not_acquired"}
        state, output, error = "completed", None, None
        try:
            sources, candidates, problems, signature = self.snapshot(row["owner_id"], row["request"])
            if signature != row["signature"]:
                raise ResearchError("source_permissions_version_or_candidates_changed", 409)
            lines = []
            query_words = tokens(row["request"]["query"])
            for candidate in candidates:
                if self.clock()-now > timeout:
                    raise ResearchError("comparison_timeout", 408)
                record = candidate["payload"]
                text = " ".join(value["value"] or "" for value in record["fields"].values()).casefold()
                if not any(word in text for word in query_words):
                    continue
                matches, excluded = {}, False
                for field in ("measure", "indicator", "soil_type", "conditions"):
                    wanted = row["request"].get(field)
                    if not wanted:
                        continue
                    actual = record["fields"][field]["value"]
                    matches[field] = "unknown" if actual is None else "matched" if wanted.casefold() in actual.casefold() else "different"
                    excluded |= matches[field] == "different"
                if not excluded:
                    lines.append({"record_id": record["id"], "document_id": record["document_id"],
                        "title": sources[record["document_id"]]["stored"]["payload"]["title"],
                        "review_status": "pending", "condition_match": matches, "fields": record["fields"],
                        "original_language_preserved": True})
            limited = len(lines) > row["request"]["limit"]
            output = {"rows": lines[:row["request"]["limit"]], "source_problems": problems,
                "eligible_documents": len(sources), "documents_with_records": len({item["document_id"] for item in candidates}),
                "document_coverage": [{"document_id": did, "extraction": source["stored"]["payload"].get("extraction_summary"),
                    "pending_records": sum(candidate["document_id"] == did for candidate in candidates)} for did, source in sources.items()],
                "pending_records_available": len(candidates), "truncated_by_row_limit": limited,
                "coverage": "partial_task_selected_chunks_not_exhaustive_paper_extraction",
                "no_matching_records_means": "insufficient_retrieved_records_not_evidence_of_no_effect",
                "synthesis_performed": False, "published_claims_added": 0, "generator": GENERATOR}
            if before_commit:
                before_commit()
            if self.clock()-now > timeout:
                raise ResearchError("comparison_timeout", 408)
            _, _, _, final_signature = self.snapshot(row["owner_id"], row["request"])
            if final_signature != row["signature"]:
                raise ResearchError("source_permissions_version_or_candidates_changed", 409)
        except ResearchError as exc:
            state = "invalidated" if exc.status == 409 else "failed"
            error, output = exc.code, None
        except Exception:
            state, error, output = "failed", "comparison_execution_failed", None
        with self.store.engine.begin() as connection:
            applied = connection.execute(jobs.update().where(jobs.c.id == row["id"], jobs.c.state == "running", jobs.c.lease == lease,
                jobs.c.lease_until >= self.clock()).values(state=state, result=output, error=error, lease=None, lease_until=None, updated_at=self.clock()))
        return {"id": row["id"], "state": state if applied.rowcount == 1 else "lease_lost_or_cancelled"}
