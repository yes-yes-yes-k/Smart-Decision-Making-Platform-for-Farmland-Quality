"""Bounded current-source verification for corpus retrieval, no app or models."""
import copy
import unittest
from unittest.mock import Mock

from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch
from framework.knowledge_graph.research_service import ResearchError


class CorpusSearchTests(unittest.TestCase):
    def setUp(self):
        self.vector = Mock()
        self.item = {"content": "石灰提高pH", "metadata": {"document_id": 100, "document_kind": "academic_paper", "content_sha256": "a"*64, "chunk_index": 0, "page": 2}}
        self.live = {100: {"title": "真实来源", "document_kind": "academic_paper", "content_sha256": "a"*64, "visibility_scope": "public", "review_status": "approved", "completed": True, "source_bytes_valid": True}}
        self.current = Mock()
        self.current.lookup_many.side_effect = lambda ids, owner, **kw: copy.deepcopy({i: self.live[i] for i in ids if i in self.live})
        self.vector.hybrid_search.return_value = {"results": [self.item], "retrieval": {"mode": "hybrid"}}
        self.search = PublishedCorpusSearch(self.vector, self.current)

    def test_global_unregistered_document_and_bounded_source_checks(self):
        result = self.search.search(1, {"query": "石灰", "limit": 20})
        self.assertEqual(result["sources"][0]["document_id"], 100)
        self.assertEqual(result["candidate_budget"], 60)
        self.assertEqual(self.current.lookup_many.call_count, 2)
        for call in self.current.lookup_many.call_args_list:
            self.assertEqual(call.args[0], [100])
            self.assertTrue(call.kwargs["require_academic"])
        self.assertFalse(result["generation_performed"])
        self.assertTrue(result["conditions_structurally_evaluated"])

    def test_invalid_or_withdrawn_or_changed_source_never_returns_text(self):
        for change in ({"visibility_scope": "private"}, {"review_status": "withdrawn"}, {"content_sha256": "b"*64}, {"completed": False}, {"source_bytes_valid": False}):
            with self.subTest(change=change):
                prior = copy.deepcopy(self.live)
                self.live[100].update(change)
                result = self.search.search(1, {"query": "石灰"})
                self.assertEqual(result["sources"], [])
                self.assertEqual(result["state"], "partial")
                self.live = prior

    def test_permissions_are_checked_again_before_return(self):
        self.current.lookup_many.side_effect = [self.live, {}]
        result = self.search.search(1, {"query": "石灰"})
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["state"], "partial")

    def test_verification_unavailable_is_fail_closed(self):
        self.current.lookup_many.side_effect = RuntimeError("secret connection")
        with self.assertRaisesRegex(ResearchError, "verification_unavailable"):
            self.search.search(1, {"query": "石灰"})

    def test_limits_filters_and_invalid_scopes(self):
        for request in ([], {"query": "x", "limit": True}, {"query": "x", "document_ids": []}, {"query": "x", "document_ids": [True]}, {"query": "x", "soil_type": []}, {"query": "x", "unknown": 1}):
            with self.subTest(request=request), self.assertRaises(ResearchError):
                self.search.search(1, request)
        self.search.search(1, {"query": "石灰", "document_ids": [100], "soil_type": "红壤"})
        self.assertEqual(self.vector.hybrid_search.call_args.kwargs["filters"]["$and"][1], {"document_id": {"$in": [100]}})

    def test_default_papers_explicit_standard_scope_and_current_kind_change(self):
        self.item["metadata"]["document_kind"] = self.live[100]["document_kind"] = "standard"
        self.assertEqual(self.search.search(1, {"query": "石灰"})["sources"], [])
        result = self.search.search(1, {"query": "石灰", "source_scope": "standards"})
        self.assertEqual(len(result["sources"]), 1)
        self.assertFalse(self.current.lookup_many.call_args.kwargs["require_academic"])
        self.live[100]["document_kind"] = "academic_paper"
        self.assertEqual(self.search.search(1, {"query": "石灰", "source_scope": "standards"})["sources"], [])

    def test_degradation_is_visible_and_empty_failure_not_reported_as_no_evidence(self):
        self.vector.hybrid_search.return_value["retrieval"] = {"mode": "degraded", "vector": {"state": "failed"}}
        result = self.search.search(1, {"query": "石灰"})
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["retrieval"]["vector"]["state"], "failed")
        self.assertEqual(result["retrieval_backend"], "degraded_or_single_path_with_current_source_checks")
        self.vector.hybrid_search.return_value["results"] = []
        with self.assertRaisesRegex(ResearchError, "retrieval_unavailable"):
            self.search.search(1, {"query": "石灰"})

    def test_limit_truncation_is_not_counted_as_stale(self):
        self.vector.hybrid_search.return_value["results"] = [self.item, dict(self.item)]
        result = self.search.search(1, {"query": "石灰", "limit": 1})
        self.assertEqual(result["filtered_unverified_or_stale"], 0)
        self.assertEqual(result["truncated_by_limit"], 1)
        self.assertEqual(result["state"], "completed")

    def test_chunk_lookup_uses_exact_reference_and_rechecks_source(self):
        self.vector.get_by_references.return_value = [self.item]
        result = self.search.read_chunk(1, 100, 0, "a"*64)
        self.assertEqual(result["page"], 2)
        self.assertEqual(self.vector.get_by_references.call_args.args[0], [{"document_id": 100, "chunk_index": 0}])
        self.current.lookup_many.side_effect = [self.live, {}]
        with self.assertRaisesRegex(ResearchError, "changed"):
            self.search.read_chunk(1, 100, 0, "a"*64)


if __name__ == "__main__":
    unittest.main()
