import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from framework.knowledge_graph.acceptance_budget import BudgetStop
from framework.knowledge_graph.contracts import stable_digest
from framework.knowledge_graph.retrieval_budget import RetrievalEmbeddingBudget


def manifest(count=1):
    items = []
    for i in range(count):
        payload = {"model": "BAAI/bge-m3", "input": ["query-"+str(i)]}
        items.append({"case_id": "Q"+str(i), "payload": payload, "reserved_tokens_per_attempt": 600,
                      "maximum_attempts": 2, "payload_sha256": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()})
    return {"requests": items, "proposed_caps": {"tokens": 20000, "attempts": 18, "concurrency": 2}}


class RetrievalBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"budget.sqlite3"

    def test_unknown_usage_is_charged_and_changed_payload_cannot_consume(self):
        packet = manifest()
        budget = RetrievalEmbeddingBudget(self.path, packet)
        with self.assertRaises(BudgetStop):
            budget.reserve_query("Q0", {"input": ["different"]})
        self.assertEqual(budget.summary()["requests"], 0)
        attempt = budget.reserve_query("Q0", packet["requests"][0]["payload"])
        budget.finish(attempt, error="Timeout")
        self.assertEqual(budget.summary()["tokens_charged_or_reserved"], 600)

    def test_amendment_keeps_old_attempts_and_requires_explicit_identity(self):
        packet = manifest()
        budget = RetrievalEmbeddingBudget(self.path, packet)
        for _ in range(2):
            attempt = budget.reserve_query("Q0", packet["requests"][0]["payload"])
            budget.finish(attempt, error="ProxyError")
        updated = copy.deepcopy(packet)
        updated["requests"][0]["maximum_attempts"] = 3
        updated["proposed_caps"]["attempts"] = 27
        with self.assertRaises(BudgetStop):
            RetrievalEmbeddingBudget(self.path, updated)
        amendment = {"previous_manifest_identity": stable_digest(packet), "new_manifest_identity": stable_digest(updated),
                     "caps": updated["proposed_caps"], "user_confirmation": "explicit amendment"}
        revised = RetrievalEmbeddingBudget(self.path, updated, amendment=amendment)
        self.assertEqual(revised.summary()["requests"], 2)
        self.assertEqual(revised.summary()["tokens_charged_or_reserved"], 1200)
        self.assertEqual(revised.remaining_attempts("Q0"), 1)
        revised.reserve_query("Q0", packet["requests"][0]["payload"])
        with self.assertRaises(BudgetStop):
            revised.reserve_query("Q0", packet["requests"][0]["payload"])

    def test_global_concurrency_and_token_cap_checked_before_call(self):
        packet = manifest(3)
        budget = RetrievalEmbeddingBudget(self.path, packet)
        for item in packet["requests"][:2]:
            budget.reserve_query(item["case_id"], item["payload"])
        with self.assertRaisesRegex(BudgetStop, "concurrency"):
            budget.reserve_query("Q2", packet["requests"][2]["payload"])
        other = manifest()
        other["proposed_caps"]["tokens"] = 500
        limited = RetrievalEmbeddingBudget(Path(self.temp.name)/"limited.sqlite3", other)
        with self.assertRaises(BudgetStop):
            limited.reserve_query("Q0", other["requests"][0]["payload"])
        self.assertEqual(limited.summary()["requests"], 0)

    def test_proxy_configuration_error_stops_queued_jobs_without_retry(self):
        from scripts import embed_retrieval_quality_queries as runner
        target = Path(self.temp.name)/"run"
        target.mkdir()
        packet = manifest(9)
        p = target/"embedding-request-manifest.json"
        p.write_text(json.dumps(packet), encoding="utf-8")
        auth = {"state": "authorized", "manifest_sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "caps": packet["proposed_caps"]}
        (target/"budget-authorization.json").write_text(json.dumps(auth), encoding="utf-8")
        with patch.object(runner, "OUT", target), patch("sys.argv", ["embed"]), \
             patch.dict("os.environ", {"SILICONFLOW_KEY": "offline-test", "SILICONFLOW_API_BASE": "https://api.siliconflow.cn/v1"}), \
             patch.object(runner.requests, "post", side_effect=requests.exceptions.ProxyError("offline injected")) as post:
            with self.assertRaises(SystemExit):
                runner.main()
        report = json.loads((target/"embedding-run.json").read_text(encoding="utf-8"))
        self.assertLessEqual(post.call_count, 2)
        self.assertEqual(report["budget"]["requests"], post.call_count)
        self.assertEqual(report["budget"]["inflight"], 0)
        self.assertGreater(report["budget"]["tokens_charged_or_reserved"], 0)


if __name__ == "__main__":
    unittest.main()
