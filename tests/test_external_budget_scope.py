"""Budget isolation and hard-stop checks; all SQLite data is temporary."""
import json
import gc
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from framework.knowledge_graph import external_benchmark_budget as module
from framework.knowledge_graph.acceptance_budget import BudgetStop


class ExternalBudgetScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.root = self.project / "artifacts/knowledge_platform/external-benchmark-v1"
        self.root.mkdir(parents=True)
        self.policy = {"scope": "external-benchmark-v1", "ledger": "execution/budget.sqlite3",
                       "caps": {"total_tokens": 20_000_000, "requests": 5000, "concurrency": 2}}
        self.save_policy()
        mocked_file = str(self.project / "framework/knowledge_graph/external_benchmark_budget.py")
        self.fixture_module = patch.object(module, "__file__", mocked_file)
        self.fixture_module.start()
        self.addCleanup(self.fixture_module.stop)
        # Existing sqlite3 transaction contexts do not close connections;
        # collect their cycles before Windows removes the temporary database.
        self.addCleanup(gc.collect)

    def save_policy(self):
        (self.root / "budget-authorization.json").write_text(json.dumps(self.policy), encoding="utf-8")

    def test_unknown_usage_is_charged_and_reopen_keeps_history(self):
        budget = module.open_external_budget(self.root)
        attempt = budget.reserve("calibration", "q", {"max_tokens": 100})
        budget.finish(attempt)
        after = module.open_external_budget(self.root).summary()
        self.assertEqual(after["requests"], 1)
        self.assertGreater(after["tokens_charged_or_reserved"], 100)
        self.assertEqual(after["inflight"], 0)

    def test_cap_and_concurrency_reject_before_new_record(self):
        budget = module.open_external_budget(self.root)
        with self.assertRaises(BudgetStop):
            budget.reserve("calibration", "oversized", {"max_tokens": 20_000_000})
        self.assertEqual(budget.summary()["requests"], 0)
        budget.reserve("calibration", "a", {"max_tokens": 1})
        budget.reserve("calibration", "b", {"max_tokens": 1})
        with self.assertRaises(BudgetStop):
            budget.reserve("calibration", "c", {"max_tokens": 1})
        self.assertEqual(budget.summary()["requests"], 2)

    def test_legacy_path_and_alternate_root_cannot_reset_scope(self):
        self.policy["ledger"] = "../legacy-budget.sqlite3"
        self.save_policy()
        with self.assertRaises(ValueError):
            module.open_external_budget(self.root)
        with self.assertRaises(ValueError):
            module.open_external_budget(self.project / "other")

    def test_changed_authorization_cannot_rebind_existing_ledger(self):
        budget = module.open_external_budget(self.root)
        attempt = budget.reserve("calibration", "q", {"max_tokens": 1})
        budget.finish(attempt)
        self.policy["new_comment"] = "different authorization"
        self.save_policy()
        with self.assertRaises(ValueError):
            module.open_external_budget(self.root)
        self.assertEqual(budget.summary()["requests"], 1)


if __name__ == "__main__":
    unittest.main()
