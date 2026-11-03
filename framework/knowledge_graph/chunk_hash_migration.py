"""Verified, resumable metadata-only migration of legacy public chunk hashes."""
from collections import defaultdict
import json
from pathlib import Path
import sqlite3

from .chunk_reader import VerifiedLegacyShadowReader
from .contracts import sha256_text, stable_digest
from framework.rag.kg_runtime import sha256_file


class HashMigrationError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class HashMigrationJournal:
    def __init__(self, path, *, scope):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("CREATE TABLE IF NOT EXISTS scope (identity TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS plans (document_id INTEGER PRIMARY KEY, payload TEXT NOT NULL, checksum TEXT NOT NULL, state TEXT NOT NULL)")
        self.connection.execute("BEGIN IMMEDIATE")
        existing = self.connection.execute("SELECT identity FROM scope").fetchone()
        if existing and existing[0] != scope:
            self.connection.close()
            raise HashMigrationError("journal_scope_mismatch")
        if not existing:
            self.connection.execute("INSERT INTO scope VALUES (?)", (scope,))
        self.connection.commit()

    def get(self, document_id):
        row = self.connection.execute("SELECT payload,checksum,state FROM plans WHERE document_id=?", (document_id,)).fetchone()
        if not row:
            return None
        payload = json.loads(row[0])
        if stable_digest(payload) != row[1]:
            raise HashMigrationError("journal_checksum_mismatch")
        return payload, row[2]

    def save(self, plan):
        self.connection.execute("INSERT INTO plans VALUES (?,?,?,?)",
            (plan["document_id"], json.dumps(plan, ensure_ascii=False), stable_digest(plan), "verified"))
        self.connection.commit()

    def state(self, document_id, value):
        self.connection.execute("UPDATE plans SET state=? WHERE document_id=?", (value, document_id))
        self.connection.commit()

    def pending_ids(self):
        return [row[0] for row in self.connection.execute(
            "SELECT document_id FROM plans WHERE state IN ('verified','prepared','rolling_back') ORDER BY document_id")]

    def close(self):
        self.connection.close()


class ChunkHashMigration:
    def __init__(self, client, journal, upload_root):
        self.client, self.journal, self.upload_root = client, journal, Path(upload_root)

    @staticmethod
    def validate_source(source):
        from types import SimpleNamespace
        from .jobs import document_is_graph_eligible
        if not document_is_graph_eligible(SimpleNamespace(**source)):
            raise HashMigrationError("source_not_eligible")

    def snapshot(self, document_id, expected_count):
        rows = []
        for item in self.client.list_collections():
            name = getattr(item, "name", str(item))
            collection = self.client.get_collection(name=name, embedding_function=None)
            data = collection.get(where={"$and": [{"document_id": int(document_id)}, {"visibility_scope": "public"}]},
                limit=expected_count+1-len(rows), include=["documents", "metadatas"])
            for key, text, meta in zip(data["ids"], data["documents"], data["metadatas"]):
                rows.append(dict(collection=name, id=key, text_sha256=sha256_text(text), metadata=meta))
            if len(rows) > expected_count:
                break
        return sorted(rows, key=lambda row: (row["collection"], row["id"]))

    def plan(self, source):
        self.validate_source(source)
        saved = self.journal.get(source["id"])
        if saved:
            plan, state = saved
            if plan["content_sha256"] != source["file_hash"] or plan["expected_count"] != source["chunk_count"]:
                raise HashMigrationError("source_changed_since_plan")
            return dict(document_id=source["id"], state=state, missing_chunks=len(plan["changes"]))
        rows = self.snapshot(source["id"], source["chunk_count"])
        if len(rows) != source["chunk_count"]:
            raise HashMigrationError("chunk_count_mismatch")
        if any(row["metadata"].get("content_sha256") not in {None, "", source["file_hash"]} for row in rows):
            raise HashMigrationError("existing_hash_conflict")
        changes = [dict(collection=row["collection"], id=row["id"]) for row in rows
                   if not row["metadata"].get("content_sha256")]
        if not changes:
            return dict(document_id=source["id"], state="already_bound", missing_chunks=0)
        verifier = VerifiedLegacyShadowReader(None, source=source, upload_root=self.upload_root, client=self.client)
        verifier.read_published_chunks(document_id=source["id"], content_sha256=source["file_hash"], expected_count=source["chunk_count"])
        if not verifier.legacy_verified or rows != self.snapshot(source["id"], source["chunk_count"]):
            raise HashMigrationError("chunks_changed_during_verification")
        original = Path(source["file_path"])
        if not original.is_absolute():
            original = self.upload_root / original
        plan = dict(document_id=source["id"], content_sha256=source["file_hash"], expected_count=source["chunk_count"],
                    source_file=str(original.resolve()), entries=rows, changes=changes, original_and_chunks_verified=True)
        self.journal.save(plan)
        return dict(document_id=source["id"], state="verified", missing_chunks=len(changes))

    def execute(self, source, *, rollback=False):
        """Caller MUST hold the source-document DB row lock for this operation."""
        self.validate_source(source)
        saved = self.journal.get(source["id"])
        if not saved:
            rows = self.snapshot(source["id"], source["chunk_count"])
            if not rollback and len(rows) == source["chunk_count"] and all(
                    row["metadata"].get("content_sha256") == source["file_hash"] for row in rows):
                return dict(document_id=source["id"], state="already_bound", updated_chunks=0)
            raise HashMigrationError("verified_plan_required")
        plan, state = saved
        if (plan["content_sha256"] != source["file_hash"] or plan["expected_count"] != source["chunk_count"]
                or not plan.get("original_and_chunks_verified")):
            raise HashMigrationError("source_changed_since_plan")
        if not Path(plan["source_file"]).is_file() or sha256_file(plan["source_file"]) != plan["content_sha256"]:
            raise HashMigrationError("source_file_hash_mismatch")
        before = self.snapshot(source["id"], source["chunk_count"])
        if len(before) != len(plan["entries"]):
            raise HashMigrationError("chunks_changed_since_plan")
        grouped = defaultdict(list)
        for expected, current in zip(plan["entries"], before):
            em, cm = dict(expected["metadata"]), dict(current["metadata"])
            prior, actual = em.pop("content_sha256", None), cm.pop("content_sha256", None)
            if (em != cm or any(expected[key] != current[key] for key in ("collection", "id", "text_sha256"))
                    or actual not in {prior, plan["content_sha256"]}):
                raise HashMigrationError("chunks_changed_since_plan")
            key = dict(collection=expected["collection"], id=expected["id"])
            if key in plan["changes"]:
                target = prior if rollback else plan["content_sha256"]
                if actual != target:
                    grouped[expected["collection"]].append((expected["id"], target))
        # Commit the recovery state BEFORE any Chroma mutation. A crash leaves
        # this same immutable plan available for idempotent forward/rollback.
        self.journal.state(source["id"], "rolling_back" if rollback else "prepared")
        for name, updates in grouped.items():
            self.client.get_collection(name=name, embedding_function=None).update(
                ids=[key for key, _ in updates], metadatas=[{"content_sha256": value} for _, value in updates])
        after = self.snapshot(source["id"], source["chunk_count"])
        expected_after = json.loads(json.dumps(plan["entries"]))
        if not rollback:
            for row in expected_after:
                row["metadata"]["content_sha256"] = plan["content_sha256"]
        if after != expected_after:
            raise HashMigrationError("post_write_verification_failed")
        result_state = "rolled_back" if rollback else "applied"
        self.journal.state(source["id"], result_state)
        return dict(document_id=source["id"], state=result_state, updated_chunks=sum(map(len, grouped.values())))
