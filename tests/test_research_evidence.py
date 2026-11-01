"""Isolated unittest entry: never imports root pytest's app startup hooks."""
import copy
from pathlib import Path
import tempfile
import unittest

import sqlalchemy as sa

from framework.knowledge_graph.contracts import SourceChunk
from framework.knowledge_graph.research_records import FIELDS, compile_record
from framework.knowledge_graph.research_store import ResearchStore, migrate, rollback_empty, records, jobs
from framework.knowledge_graph.research_service import ResearchService, ResearchError


class ResearchEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = sa.create_engine("sqlite:///"+str(Path(self.temp.name)/"research.db"))
        self.store = ResearchStore(self.engine)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.engine.dispose)
        self.chunk = SourceChunk(1, "a"*64, 0, "在红壤中施用石灰，培养90天后土壤pH显著升高；另有处理无显著变化。", 2)
        self.document = {"document_id": 1, "content_sha256": "a"*64, "title": "土壤论文", "document_kind": "academic_paper",
                         "visibility_scope": "public", "review_status": "approved", "verification": {"state": "verified"},
                         "chunks": [self.chunk.__dict__] if hasattr(self.chunk, "__dict__") else [{"document_id": 1, "content_sha256": "a"*64,
                             "chunk_index": 0, "content": self.chunk.content, "page": 2}]}
        self.live = {1: {"content_sha256": "a"*64, "visibility_scope": "public", "review_status": "approved", "completed": True, "source_bytes_valid": True}}
        self.service = ResearchService(self.store, lambda did, actor: copy.deepcopy(self.live.get(did)))

    def initialize(self):
        migrate(self.engine, apply=True)
        self.store.import_source(self.document)

    def record(self, **changes):
        selected = {name: None for name in FIELDS}
        for name, quote in {"measure": "石灰", "indicator": "pH", "result": "土壤pH显著升高", "soil_type": "红壤", "duration": "90天", **changes}.items():
            selected[name] = None if quote is None else {"chunk_index": 0, "quote": quote}
        return compile_record(1, "a"*64, selected, {0: self.chunk}, provenance={"origin": "test_source", "configuration_sha256": "test"})

    def completed_job(self):
        self.initialize(); self.store.add_record(self.record())
        job, _ = self.service.submit(1, {"query": "石灰 pH"})
        self.assertEqual(self.service.run_once()["state"], "completed")
        return job["id"]

    def test_constructor_and_preview_do_not_create_tables(self):
        self.assertEqual(sa.inspect(self.engine).get_table_names(), [])
        with self.assertRaisesRegex(ValueError, "explicit_migration"):
            self.store.require_schema()
        self.assertFalse(migrate(self.engine)["applied"])
        self.assertEqual(sa.inspect(self.engine).get_table_names(), [])

    def test_empty_migration_can_rollback_and_preserves_unrelated_table(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE unrelated (id INTEGER)")
        migrate(self.engine, apply=True); rollback_empty(self.engine)
        self.assertEqual(sa.inspect(self.engine).get_table_names(), ["unrelated"])

    def test_nonempty_rollback_is_rejected(self):
        self.initialize()
        with self.assertRaisesRegex(ValueError, "nonempty"):
            rollback_empty(self.engine)

    def test_fields_are_exact_and_unknown_is_not_inferred(self):
        record = self.record()
        self.assertIsNone(record["fields"]["dose"]["value"])
        self.assertEqual(record["fields"]["result"]["evidence"]["page"], 2)
        with self.assertRaises(ValueError): self.record(dose="5吨/公顷")
        with self.assertRaises(ValueError): compile_record(2, "a"*64, {name: None if name not in {"measure", "indicator", "result"} else {"chunk_index": 0, "quote": "石灰"} for name in FIELDS}, {0: self.chunk}, provenance={"origin": "test", "configuration_sha256": "test"})

    def test_record_tampering_or_promotion_is_rejected(self):
        self.initialize(); record = self.record(); record["review_status"] = "approved"
        with self.assertRaises(ValueError): self.store.add_record(record)
        record = self.record(); record["fields"]["result"]["evidence"]["span_start"] = 0
        with self.assertRaises(ValueError): self.store.add_record(record)

    def test_import_and_record_are_idempotent(self):
        self.initialize()
        self.assertFalse(self.store.import_source(self.document)["changed"])
        self.assertTrue(self.store.add_record(self.record()))
        self.assertFalse(self.store.add_record(self.record()))

    def test_source_search_works_without_graph_or_model(self):
        self.initialize()
        result = self.service.search(1, {"query": "石灰"})
        self.assertEqual(result["sources"][0]["page"], 2)
        self.assertEqual(result["graph"]["state"], "not_configured")
        self.assertFalse(result["generation_performed"])

    def test_graph_failure_does_not_break_sources(self):
        self.initialize()
        self.service.graph_lookup = lambda *_: (_ for _ in ()).throw(RuntimeError("private backend details"))
        result = self.service.search(1, {"query": "石灰"})
        self.assertTrue(result["sources"])
        self.assertEqual(result["graph"]["state"], "unavailable")
        self.assertNotIn("private", str(result))

    def test_source_permission_changed_while_searching_filters_text(self):
        self.initialize(); count = [0]
        def check(did, actor):
            count[0] += 1
            return self.live[did] | {"visibility_scope": "public" if count[0] == 1 else "private"}
        self.service.current_source = check
        self.assertFalse(self.service.search(1, {"query": "石灰"})["sources"])

    def test_unknown_requested_conditions_are_not_matched(self):
        self.initialize(); self.store.add_record(self.record(soil_type=None))
        job, _ = self.service.submit(1, {"query": "石灰", "soil_type": "红壤"})
        self.service.run_once()
        result = self.service.get(1, job["id"])["result"]
        self.assertEqual(result["rows"][0]["condition_match"]["soil_type"], "unknown")
        self.assertFalse(result["synthesis_performed"])
        self.assertEqual(result["published_claims_added"], 0)

    def test_source_revocation_invalidates_completed_cache(self):
        identifier = self.completed_job(); self.live[1]["visibility_scope"] = "private"
        result = self.service.get(1, identifier)
        self.assertEqual(result["state"], "invalidated"); self.assertIsNone(result["result"])

    def test_source_bytes_change_invalidates_cache(self):
        identifier = self.completed_job(); self.live[1]["source_bytes_valid"] = False
        self.assertEqual(self.service.get(1, identifier)["state"], "invalidated")

    def test_rejected_candidate_invalidates_cache(self):
        identifier = self.completed_job(); self.store.reject_record(self.record()["id"])
        self.assertEqual(self.service.get(1, identifier)["state"], "invalidated")

    def test_cancel_during_execution_cannot_be_resurrected(self):
        self.initialize(); self.store.add_record(self.record())
        job, _ = self.service.submit(1, {"query": "石灰"})
        self.assertEqual(self.service.run_once(before_commit=lambda: self.service.cancel(1, job["id"]))["state"], "lease_lost_or_cancelled")
        self.assertEqual(self.service.get(1, job["id"])["state"], "cancelled")

    def test_owner_isolation_and_duplicate_submit(self):
        self.initialize(); first, _ = self.service.submit(1, {"query": "石灰"})
        again, cached = self.service.submit(1, {"query": "石灰"})
        self.assertEqual(first["id"], again["id"]); self.assertTrue(cached)
        with self.assertRaises(ResearchError): self.service.get(2, first["id"])
        with self.assertRaises(ResearchError): self.service.cancel(2, first["id"])

    def test_source_failure_is_not_a_negative_fact(self):
        self.initialize(); self.service.current_source = lambda *_: None
        result = self.service.search(1, {"query": "石灰"})
        self.assertEqual(result["state"], "partial"); self.assertFalse(result["sources"])
        with self.assertRaises(ResearchError): self.service.submit(1, {"query": "石灰"})

    def test_expired_running_job_is_recovered_and_attempt_limit_is_terminal(self):
        self.initialize(); job, _ = self.service.submit(1, {"query": "石灰"})
        with self.engine.begin() as connection:
            connection.execute(jobs.update().where(jobs.c.id == job["id"]).values(state="running", lease="dead", lease_until=0, attempts=1))
        self.assertEqual(self.service.run_once()["state"], "completed")
        with self.engine.begin() as connection:
            connection.execute(jobs.update().where(jobs.c.id == job["id"]).values(state="running", lease="dead", lease_until=0, attempts=3))
        self.service.run_once()
        self.assertEqual(self.service.get(1, job["id"])["state"], "failed")

    def test_source_changes_before_worker_commit_prevent_result(self):
        self.initialize(); self.store.add_record(self.record())
        job, _ = self.service.submit(1, {"query": "石灰"})
        def withdraw(): self.live[1]["completed"] = False
        self.assertEqual(self.service.run_once(before_commit=withdraw)["state"], "invalidated")
        self.assertIsNone(self.service.get(1, job["id"])["result"])

    def test_timeout_and_invalid_limits_are_explicit(self):
        self.initialize(); job, _ = self.service.submit(1, {"query": "石灰"})
        self.assertEqual(self.service.run_once(timeout=-1)["state"], "failed")
        self.assertEqual(self.service.get(1, job["id"])["error"], "comparison_timeout")
        for payload in [{"query": "石灰", "limit": True}, {"query": "石灰", "document_ids": [True]}, {"query": "石灰", "unknown": "x"}]:
            with self.assertRaises(ResearchError): self.service.normalize(payload)

    def test_different_findings_in_one_paper_are_not_merged(self):
        self.initialize()
        first = self.record()
        second = self.record(result="无显著变化", negation="无显著变化")
        self.store.add_record(first); self.store.add_record(second)
        self.assertNotEqual(first["id"], second["id"])
        job, _ = self.service.submit(1, {"query": "石灰"})
        self.service.run_once()
        result = self.service.get(1, job["id"])["result"]
        self.assertEqual(len(result["rows"]), 2)
        self.assertFalse(result["synthesis_performed"])

    def test_content_version_changes_invalidate_old_records(self):
        identifier = self.completed_job()
        self.live[1]["content_sha256"] = "b"*64
        self.assertEqual(self.service.get(1, identifier)["state"], "invalidated")

    def test_same_hash_different_chunk_text_cannot_replace_snapshot(self):
        self.initialize(); changed = copy.deepcopy(self.document)
        changed["chunks"][0]["content"] = "另一段未核验文本"
        with self.assertRaisesRegex(ValueError, "snapshot_changed"):
            self.store.import_source(changed)

    def test_new_service_instance_resumes_persisted_queue(self):
        self.initialize(); self.store.add_record(self.record())
        job, _ = self.service.submit(1, {"query": "石灰"})
        self.engine.dispose()
        restored_engine = sa.create_engine("sqlite:///"+str(Path(self.temp.name)/"research.db"))
        self.addCleanup(restored_engine.dispose)
        restored = ResearchService(ResearchStore(restored_engine), lambda did, actor: self.live.get(did))
        self.assertEqual(restored.run_once()["state"], "completed")
        self.assertEqual(restored.get(1, job["id"])["result"]["rows"][0]["review_status"], "pending")

    def test_live_chunk_snapshot_change_blocks_stale_source(self):
        self.initialize(); self.live[1]["chunk_count"] = 2
        result = self.service.search(1, {"query": "石灰"})
        self.assertFalse(result["sources"])
        self.assertEqual(result["source_problems"][0]["reason"], "source_chunk_snapshot_changed")


class ResearchApiTests(unittest.TestCase):
    initialize = ResearchEvidenceTests.initialize
    record = ResearchEvidenceTests.record

    def setUp(self):
        ResearchEvidenceTests.setUp(self)
        from framework.api.routes.literature_evidence import EvidenceActor, create_evidence_app
        from flask_jwt_extended import create_access_token
        self.app = create_evidence_app(self.service, lambda identity: EvidenceActor(int(identity), "admin" if identity == "1" else "user"),
                                       jwt_secret="M1-isolated-unit-secret-at-least-thirty-two-bytes")
        self.client = self.app.test_client()
        with self.app.app_context():
            self.auth = {"Authorization": "Bearer "+create_access_token(identity="1")}
            self.other = {"Authorization": "Bearer "+create_access_token(identity="2")}

    def test_authenticated_product_routes_and_owner_isolation(self):
        self.initialize(); self.store.add_record(self.record())
        prefix = "/api/v1/literature-evidence"
        self.assertEqual(self.client.post(prefix+"/search", json={"query": "石灰"}).status_code, 401)
        result = self.client.post(prefix+"/search", json={"query": "石灰"}, headers=self.auth)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json["sources"])
        submitted = self.client.post(prefix+"/comparisons", json={"query": "石灰"}, headers=self.auth)
        self.assertEqual(submitted.status_code, 202)
        identifier = submitted.json["id"]
        self.assertEqual(self.client.get(prefix+"/comparisons/"+identifier, headers=self.other).status_code, 404)
        self.service.run_once()
        completed = self.client.get(prefix+"/comparisons/"+identifier, headers=self.auth)
        self.assertEqual(completed.json["state"], "completed")
        self.assertEqual(completed.json["result"]["rows"][0]["review_status"], "pending")
        self.live[1]["visibility_scope"] = "private"
        self.assertIsNone(self.client.get(prefix+"/comparisons/"+identifier, headers=self.auth).json["result"])

    def test_missing_schema_returns_503_without_migration(self):
        result = self.client.post("/api/v1/literature-evidence/search", json={"query": "石灰"}, headers=self.auth)
        self.assertEqual(result.status_code, 503)
        self.assertEqual(sa.inspect(self.engine).get_table_names(), [])

    def test_cancel_is_an_explicit_http_operation(self):
        self.initialize()
        prefix = "/api/v1/literature-evidence"
        job = self.client.post(prefix+"/comparisons", json={"query": "石灰"}, headers=self.auth).json
        result = self.client.delete(prefix+"/comparisons/"+job["id"], headers=self.auth)
        self.assertEqual(result.json["state"], "cancelled")
        self.assertEqual(self.service.run_once()["state"], "idle")

    def test_only_reviewer_can_reject_pending_record(self):
        self.initialize(); record = self.record(); self.store.add_record(record)
        url = "/api/v1/literature-evidence/records/"+record["id"]+"/reject"
        self.assertEqual(self.client.post(url, headers=self.other).status_code, 403)
        self.assertEqual(self.client.post(url, headers=self.auth).status_code, 200)

    def test_source_context_requires_current_version_and_permission(self):
        self.initialize()
        url = "/api/v1/literature-evidence/sources/1/chunks/0?content_sha256="
        self.assertEqual(self.client.get(url+"wrong", headers=self.auth).status_code, 409)
        self.assertEqual(self.client.get(url+"a"*64, headers=self.auth).json["text"], self.chunk.content)
        self.live[1]["visibility_scope"] = "private"
        self.assertEqual(self.client.get(url+"a"*64, headers=self.auth).status_code, 409)

    def test_disabled_identity_cannot_access_saved_results(self):
        from framework.api.routes.literature_evidence import EvidenceActor
        self.initialize()
        self.app.extensions["literature_evidence_actor_resolver"] = lambda identity: EvidenceActor(1, "admin", False)
        self.assertEqual(self.client.get("/api/v1/literature-evidence/sources", headers=self.auth).status_code, 403)

    def test_opt_in_configuration_does_not_create_missing_database(self):
        from framework.api.routes.literature_evidence import configure_evidence_service
        missing = Path(self.temp.name)/"not-prepared.db"
        self.app.config["LITERATURE_EVIDENCE_DATABASE_URI"] = "sqlite:///"+str(missing)
        configure_evidence_service(self.app)
        self.assertFalse(missing.exists())
        self.assertEqual(self.client.get("/api/v1/literature-evidence/sources", headers=self.auth).status_code, 503)


if __name__ == "__main__":
    unittest.main()
