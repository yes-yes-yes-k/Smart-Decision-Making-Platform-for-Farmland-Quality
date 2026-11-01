"""Independent unittest entry; never invokes the application/conftest startup."""
from pathlib import Path
import tempfile
import unittest

from framework.vector_store.lexical_index import LexicalIndex
from framework.vector_store.bm25_store import BM25Store


class LexicalOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"lexical.sqlite3"
        self.index = LexicalIndex(self.path, "papers")

    def populate(self):
        self.index.begin_rebuild()
        self.index.upsert([("a", "土壤交换性氢与石灰", {"document_id": 1, "owner_id": 1, "visibility_scope": "public"}),
                           ("b", "有效钾是作物重要养分指标", {"document_id": 2, "owner_id": 2, "visibility_scope": "private"})])
        self.index.finish_rebuild(2)

    def test_persistent_restart_does_not_retokenize(self):
        self.populate()
        restored = LexicalIndex(self.path, "papers")
        self.assertEqual(restored.health()["rows"], 2)
        self.assertEqual(restored.search("交换性氢")[0]["id"], "a")
        self.assertEqual(restored.metrics["tokenized_rows"], 0)

    def test_metadata_only_sync_never_retokenizes(self):
        self.populate(); before = self.index.metrics["tokenized_rows"]
        op = self.index.begin_operation({"ids": ["a"]})
        self.assertEqual(self.index.search("石灰"), [])
        self.index.reconcile(op, {"ids": ["a"]}, [[("a", "土壤交换性氢与石灰", {"document_id": 1, "owner_id": 1, "visibility_scope": "private"})]], 2)
        self.assertEqual(self.index.metrics["tokenized_rows"], before)
        self.assertEqual(self.index.search("石灰", filters={"visibility_scope": "public"}), [])

    def test_only_changed_document_is_tokenized_and_replay_is_idempotent(self):
        self.populate(); before = self.index.metrics["tokenized_rows"]
        values = [("a", "石灰提高土壤pH", {"document_id": 1})]
        for _ in range(2):
            op = self.index.begin_operation({"where": {"document_id": 1}})
            self.index.reconcile(op, {"where": {"document_id": 1}}, [values], 2)
        self.assertEqual(self.index.metrics["tokenized_rows"]-before, 1)
        self.assertEqual(self.index.health()["rows"], 2)
        self.assertEqual(self.index.search("交换性氢"), [])
        self.assertEqual(self.index.search("PH")[0]["id"], "a")

    def test_failed_sync_rolls_back_and_pending_scope_survives_restart(self):
        self.populate()
        op = self.index.begin_operation({"ids": ["a"]})
        def interrupted():
            yield [("a", "石灰修复土壤", {"document_id": 1})]
            raise RuntimeError("simulated_process_loss")
        with self.assertRaises(RuntimeError): self.index.reconcile(op, {"ids": ["a"]}, interrupted(), 2)
        restored = LexicalIndex(self.path, "papers")
        self.assertEqual(restored.health()["pending_operations"], 1)
        self.assertEqual(restored.search("石灰"), [])
        restored.reconcile(op, {"ids": ["a"]}, [[("a", "石灰修复土壤", {"document_id": 1})]], 2)
        self.assertEqual(restored.health()["pending_operations"], 0)
        self.assertEqual(restored.health()["rows"], 2)

    def test_deletion_is_transactional_and_does_not_touch_other_owner(self):
        self.index.begin_rebuild()
        self.index.upsert([("a", "石灰", {"document_id": 1, "owner_id": 1}), ("b", "石灰", {"document_id": 1, "owner_id": 2})])
        self.index.finish_rebuild(2)
        selector = {"where": {"$and": [{"document_id": 1}, {"owner_id": 1}]}}
        op = self.index.begin_operation(selector)
        self.index.reconcile(op, selector, [], 1)
        self.assertEqual([row["id"] for row in self.index.search("石灰")], ["b"])

    def test_nested_filters_apply_before_result_limit(self):
        self.populate()
        where = {"$and": [{"visibility_scope": "public"}, {"owner_id": {"$in": [1]}}]}
        self.assertEqual(self.index.search("石灰 有效钾", 1, where)[0]["id"], "a")
        self.assertEqual(self.index.search("石灰", filters={"owner_id": 2}), [])

    def test_null_membership_and_unsupported_predicates(self):
        self.populate()
        self.assertEqual(len(self.index.search("石灰 有效钾", filters={"missing": {"$in": [None]}})), 2)
        self.assertEqual(len(self.index.search("石灰 有效钾", filters={"missing": {"$nin": [1]}})), 2)
        with self.assertRaises(ValueError): self.index.search("石灰", filters={"owner_id": {"$regex": ".*"}})

    def test_query_never_tokenizes_documents(self):
        self.populate()
        before = self.index.metrics["tokenized_rows"]
        for _ in range(4): self.index.search("土壤")
        self.assertEqual(before, self.index.metrics["tokenized_rows"])
        self.assertLessEqual(self.index.metrics["returned_rows"], 80)

    def test_incomplete_bootstrap_does_not_serve_partial_index(self):
        self.index.begin_rebuild(); self.index.upsert([("a", "石灰", {})])
        with self.assertRaises(ValueError): self.index.finish_rebuild(2)
        self.assertEqual(self.index.search("石灰"), [])
        restored = LexicalIndex(self.path, "papers")
        self.assertEqual(restored.health()["base_state"], "building")

    def test_namespaces_are_isolated(self):
        self.populate(); other = LexicalIndex(self.path, "other")
        other.begin_rebuild(); other.finish_rebuild(0)
        self.assertEqual(other.search("石灰"), [])
        self.assertEqual(other.clear(), 0)
        self.assertEqual(self.index.health()["rows"], 2)

    def test_public_BM25_interface(self):
        store = BM25Store()
        self.assertEqual(store.add_documents(["有效钾", "交换性氢"], [{"source": "a"}, {"source": "b"}]), 2)
        self.assertEqual(store.search("有效钾")[0]["metadata"]["source"], "a")
        self.assertEqual(store.delete_by_source("a"), 1)
        self.assertEqual(store.search("有效钾"), [])
        self.assertEqual(store.clear(), 1)


if __name__ == "__main__":
    unittest.main()
