"""Behavioral retrieval checks without production DB, embeddings or app startup."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from framework.vector_store.lexical_index import LexicalIndex
from framework.vector_store.retrieval_policy import lexical_concept_groups, interleave_unique, rank_documents
from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch


class RetrievalPolicyTests(unittest.TestCase):
    def test_bilingual_concepts_retrieve_english_with_filters_and_no_title(self):
        with tempfile.TemporaryDirectory() as directory:
            index = LexicalIndex(Path(directory)/"index.sqlite3", "papers")
            index.upsert([(str(i), text, {"document_id": i, "visibility_scope": visibility})
                          for i, text, visibility in [(1, "Biochar increased soil organic carbon", "public"),
                                                     (2, "Biochar organic carbon", "private"),
                                                     (3, "Manure increased yield", "public")]])
            index.mark_ready()
            result = index.search("生物炭对土壤有机碳的影响", 10, {"visibility_scope": "public"},
                                  concept_groups=lexical_concept_groups("生物炭对土壤有机碳的影响"))
            self.assertEqual([item["metadata"]["document_id"] for item in result], [1])
            self.assertEqual(lexical_concept_groups("unrelated limelight"), [])
            self.assertEqual(lexical_concept_groups("classical method"), [])

    def test_joint_concept_leg_preserves_each_measure_and_each_requested_indicator(self):
        with tempfile.TemporaryDirectory() as directory:
            index = LexicalIndex(Path(directory)/"index.sqlite3", "papers")
            index.upsert([("a", "milk vetch rice straw lime cadmium yield", {}),
                          ("b", "rice straw lime cadmium", {}),
                          ("c", "milk vetch rice straw lime yield", {})])
            index.mark_ready()
            results = index.search("紫云英稻草石灰对镉和产量", 10,
                                   concept_groups=lexical_concept_groups("紫云英稻草石灰对镉和产量"))
            self.assertEqual({item["id"] for item in results}, {"a"})

    def test_interleaving_preserves_both_legs_and_does_not_merge_versions(self):
        def item(i, version="v1"):
            return {"metadata": {"document_id": i, "content_sha256": version, "chunk_index": 0}}
        result = interleave_unique([item(1), item(2)], [item(1), item(1, "v2")], 3)
        self.assertEqual([(v["metadata"]["document_id"], v["metadata"]["content_sha256"]) for v in result],
                         [(1, "v1"), (2, "v1"), (1, "v2")])

    def test_expansion_retains_recognized_duration_crop_and_acidity(self):
        with tempfile.TemporaryDirectory() as directory:
            index = LexicalIndex(Path(directory)/"index.sqlite3", "papers")
            index.upsert([("a", "Long-term biochar organic carbon", {}),
                          ("b", "Biochar organic carbon", {}),
                          ("c", "Lime acidic paddy cadmium", {}),
                          ("d", "Lime wheat cadmium", {})])
            index.mark_ready()
            for query, expected in [("长期生物炭对有机碳", "a"), ("酸性稻田施石灰对镉", "c")]:
                result = index.search(query, 10, concept_groups=lexical_concept_groups(query))
                self.assertEqual([item["id"] for item in result], [expected])

    def test_document_votes_do_not_increase_with_duplicate_chunks_and_keep_evidence(self):
        def item(did, index, vector):
            return {"document_id": did, "content_sha256": "v1", "title": str(did), "chunk_index": index,
                    "retrieval": {"retrieval_ranks": {"vector": vector}}}
        one = item(1, 0, 1)
        two = item(2, 0, 2)
        original = rank_documents([one, two])
        expanded = rank_documents([one, item(1, 1, 3), item(1, 2, 4), two])
        self.assertEqual([v["retrieval"] for v in original], [v["retrieval"] for v in expanded])
        self.assertEqual(len(expanded[0]["evidence_candidates"]), 3)
        self.assertFalse(expanded[0]["support_verified"])

    def test_document_list_survives_evidence_limit_but_not_source_revocation(self):
        chunks = [{"content": "text", "metadata": {"document_id": did, "content_sha256": "v1",
                   "chunk_index": index, "document_kind": "academic_paper"},
                   "retrieval_ranks": {"vector": rank}} for rank, (did, index) in enumerate([(1, 0), (1, 1), (2, 0)], 1)]
        vector = Mock()
        vector.hybrid_search.return_value = {"results": chunks, "retrieval": {"mode": "hybrid"}}
        live = {did: {"title": str(did), "content_sha256": "v1", "visibility_scope": "public",
                     "review_status": "approved", "completed": True, "source_bytes_valid": True,
                     "document_kind": "academic_paper"} for did in (1, 2)}
        current = Mock()
        current.lookup_many.side_effect = lambda *args, **kw: copy.deepcopy(live)
        search = PublishedCorpusSearch(vector, current)
        result = search.search(1, {"query": "粪肥", "limit": 2})
        self.assertEqual([item["document_id"] for item in result["sources"]], [1, 1])
        self.assertEqual([item["document_id"] for item in result["documents"]], [1, 2])
        current.lookup_many.side_effect = [copy.deepcopy(live), {1: live[1]}]
        result = search.search(1, {"query": "粪肥", "limit": 2})
        self.assertEqual([item["document_id"] for item in result["documents"]], [1])
        self.assertEqual(result["filtered_unverified_or_stale"], 1)


if __name__ == "__main__":
    unittest.main()
