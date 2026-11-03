"""R1.3: source kinds, permissions, effective version and condition separation.

Support, condition state and publication identity are reported separately.
A condition term absent from the authorized chunk is unknown, never a match.
"""
import copy
import unittest
from unittest.mock import Mock

from framework.knowledge_graph.research_retrieval import (
    PublishedCorpusSearch, evaluate_conditions, locate_surface)
from framework.knowledge_graph.research_service import ResearchError

SHA = "a"*64


def make_item(text, document_id=100, kind="academic_paper", sha=SHA, index=0, page=2, rank=1):
    return {"content": text, "retrieval_ranks": {"vector": rank},
            "metadata": {"document_id": document_id, "document_kind": kind,
                         "content_sha256": sha, "chunk_index": index, "page": page}}


def make_live(document_id=100, kind="academic_paper", sha=SHA, **changes):
    value = {"title": f"来源 {document_id}", "document_kind": kind, "content_sha256": sha,
             "version": f"v{document_id}", "visibility_scope": "public",
             "review_status": "approved", "completed": True, "source_bytes_valid": True}
    value.update(changes)
    return value


class ConditionEvaluationTests(unittest.TestCase):
    def test_absent_term_is_unknown_and_never_a_match(self):
        result = evaluate_conditions({"soil_type": "红壤"}, "生物炭提高水稻产量")
        self.assertEqual(result["fields"]["soil_type"]["status"], "unknown")
        self.assertEqual(result["matched"], [])
        self.assertEqual(result["unknown"], ["soil_type"])
        self.assertEqual(result["mismatch_detection"], "not_derivable_from_single_chunk_text")

    def test_surface_match_is_located_with_codepoint_offsets(self):
        text = "在  红壤 上施用石灰"
        hit = locate_surface(text, "红壤")
        self.assertEqual(text[hit["start"]:hit["end"]], "红壤")
        self.assertEqual(hit["quote"], "红壤")
        self.assertEqual(locate_surface("Long  term trial", "long term")["start"], 0)
        self.assertIsNone(locate_surface("生物炭", "石灰"))

    def test_no_filter_requested_is_reported_not_assumed(self):
        result = evaluate_conditions({"query": "生物炭"}, "生物炭提高产量")
        self.assertEqual(result["evaluation"], "not_requested")
        self.assertEqual(result["fields"], {})

    def test_multiple_fields_are_reported_individually(self):
        result = evaluate_conditions({"measure": "石灰", "indicator": "有机碳", "soil_type": "红壤"},
                                     "石灰提升土壤有机碳，供试土壤为红壤")
        self.assertEqual(result["matched"], ["measure", "indicator", "soil_type"])


class ScopeAndVersionTests(unittest.TestCase):
    def setUp(self):
        self.vector = Mock()
        self.sources = Mock()
        self.live = {100: make_live()}
        self.sources.lookup_many.side_effect = lambda ids, owner, **kw: copy.deepcopy(
            {i: self.live[i] for i in ids if i in self.live})
        self.items = [make_item("石灰提高pH")]
        self.vector.hybrid_search.return_value = {"results": self.items,
                                                  "retrieval": {"mode": "hybrid"}}
        self.search = PublishedCorpusSearch(self.vector, self.sources)

    def test_scope_declares_kinds_and_policies_scope_is_explicit(self):
        papers = self.search.search(1, {"query": "石灰"})
        self.assertEqual(papers["source_scope_kinds"], ["academic_paper"])
        self.assertEqual(self.vector.hybrid_search.call_args.kwargs["filters"]["$and"][1],
                         {"document_kind": {"$in": ["academic_paper"]}})
        self.assertEqual(self.search.search(1, {"query": "石灰", "source_scope": "policies"})["sources"], [])
        for kind, scope in (("policy", "policies"), ("method_guideline", "all_qualified")):
            self.live[100]["document_kind"] = kind
            self.items[0]["metadata"]["document_kind"] = kind
            result = self.search.search(1, {"query": "石灰", "source_scope": scope})
            self.assertEqual(len(result["sources"]), 1)
            self.assertEqual(result["source_scope_kinds"],
                             ["policy"] if scope == "policies" else
                             ["academic_paper", "standard", "policy", "method_guideline"])
            self.assertFalse(self.sources.lookup_many.call_args.kwargs["require_academic"])
            self.assertEqual(self.search.search(1, {"query": "石灰"})["sources"], [])
        with self.assertRaisesRegex(ResearchError, "source_scope"):
            self.search.search(1, {"query": "石灰", "source_scope": "books"})

    def test_publication_identity_carries_the_revalidated_version(self):
        source = self.search.search(1, {"query": "石灰", "soil_type": "红壤"})["sources"][0]
        self.assertEqual(source["publication"]["content_sha256"], SHA)
        self.assertEqual(source["publication"]["version"], "v100")
        self.assertEqual(source["publication"]["document_kind"], "academic_paper")
        self.assertEqual(source["publication"]["visibility_scope"], "public")
        self.assertEqual(source["publication"]["lifecycle_state"], "completed")
        self.assertTrue(source["publication"]["revalidated_before_return"])

    def test_support_is_never_asserted_and_surface_match_is_not_support(self):
        without = self.search.search(1, {"query": "石灰"})["sources"][0]
        with_filter = self.search.search(1, {"query": "石灰", "measure": "石灰"})["sources"][0]
        for source in (without, with_filter):
            self.assertFalse(source["support"]["support_verified"])
            self.assertFalse(source["support"]["direct_support_claimed"])
            self.assertFalse(source["support"]["condition_surface_match_is_support"])
            self.assertEqual(source["support"]["semantic_support"], "unreviewed")
        self.assertEqual(without["support"]["evaluation"], "not_performed")
        self.assertEqual(with_filter["support"]["evaluation"], "conditions_only_not_support")
        self.assertEqual(with_filter["conditions"]["fields"]["measure"]["status"], "matched")

    def test_withdrawn_private_or_stale_source_is_not_listed_anywhere(self):
        for change in ({"visibility_scope": "private"}, {"review_status": "withdrawn"},
                       {"completed": False}, {"source_bytes_valid": False}, {"content_sha256": "b"*64}):
            with self.subTest(change=change):
                prior = copy.deepcopy(self.live[100])
                self.live[100].update(change)
                result = self.search.search(1, {"query": "石灰"})
                self.assertEqual(result["sources"], [])
                self.assertEqual(result["documents"], [])
                self.assertEqual(result["state"], "partial")
                self.assertEqual(result["filtered_unverified_or_stale"], 1)
                self.live[100] = prior

    def test_changed_kind_never_passes_as_the_requested_kind(self):
        self.live[100]["document_kind"] = "policy"
        self.items[0]["metadata"]["document_kind"] = "policy"
        self.assertEqual(self.search.search(1, {"query": "石灰"})["sources"], [])
        self.assertEqual(len(self.search.search(1, {"query": "石灰", "source_scope": "policies"})["sources"]), 1)


class ConditionFilterTests(unittest.TestCase):
    def setUp(self):
        self.vector = Mock()
        self.sources = Mock()
        self.live = {100: make_live(100), 200: make_live(200)}
        self.sources.lookup_many.side_effect = lambda ids, owner, **kw: copy.deepcopy(
            {i: self.live[i] for i in ids if i in self.live})
        self.items = [make_item("红壤施用石灰提升有机碳", 100, rank=1),
                      make_item("黄壤施用石灰提升有机碳", 200, rank=2)]
        self.vector.hybrid_search.return_value = {"results": self.items, "retrieval": {"mode": "hybrid"}}
        self.search = PublishedCorpusSearch(self.vector, self.sources)

    def test_unknown_is_annotated_and_kept_unless_strict(self):
        result = self.search.search(1, {"query": "石灰", "soil_type": "红壤"})
        self.assertEqual([source["document_id"] for source in result["sources"]], [100, 200])
        self.assertEqual(result["condition_filter"]["matched_candidates"], 1)
        self.assertEqual(result["condition_filter"]["unknown_candidates"], 1)
        self.assertEqual(result["condition_filter"]["excluded_unknown"], 0)
        self.assertFalse(result["condition_filter"]["strict"])
        self.assertTrue(result["condition_filter"]["unknown_not_treated_as_match"])
        self.assertEqual(result["condition_filter"]["policy"], "explicit_surface_text_match")

    def test_strict_requires_a_declared_filter_and_excludes_unknown(self):
        with self.assertRaisesRegex(ResearchError, "invalid_research_filter"):
            self.search.search(1, {"query": "石灰", "require_condition_match": True})
        with self.assertRaisesRegex(ResearchError, "invalid_research_filter"):
            self.search.search(1, {"query": "石灰", "soil_type": "红壤", "require_condition_match": "yes"})
        result = self.search.search(1, {"query": "石灰", "soil_type": "红壤", "require_condition_match": True})
        self.assertEqual([source["document_id"] for source in result["sources"]], [100])
        self.assertEqual(result["condition_filter"]["strict"], True)
        self.assertEqual(result["condition_filter"]["excluded_unknown"], 1)
        self.assertEqual(result["condition_filter"]["matched_candidates"], 1)
        self.assertEqual(result["filtered_unverified_or_stale"], 0)

    def test_documents_report_publication_conditions_and_unevaluated_support(self):
        documents = self.search.search(1, {"query": "石灰", "soil_type": "红壤"})["documents"]
        self.assertEqual(len(documents), 2)
        for document in documents:
            self.assertFalse(document["support_verified"])
            self.assertEqual(document["publication"]["content_sha256"], SHA)
            self.assertEqual(set(document["condition_summary"]), {"soil_type"})
        self.assertEqual(documents[0]["condition_summary"]["soil_type"]["matched"], 1)

    def test_condition_fields_reject_non_string_and_overlong_values(self):
        for request in ({"query": "石灰", "measure": 5}, {"query": "石灰", "indicator": "x"*301}):
            with self.subTest(request=request), self.assertRaisesRegex(ResearchError, "invalid_research_filter"):
                self.search.search(1, request)

    def test_condition_filter_does_not_change_publication_or_allow_other_fields(self):
        with self.assertRaisesRegex(ResearchError, "invalid_comparison_request"):
            self.search.search(1, {"query": "石灰", "crop": "水稻"})


if __name__ == "__main__":
    unittest.main()
