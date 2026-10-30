import copy
import unittest

from framework.knowledge_graph.retrieval_diagnostics import pointer, signature, target_summary, valid_paper


class CandidateDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.target = {"document_id": 7, "content_sha256": "a", "chunk_index": 2}
        self.other = {"document_id": 9, "content_sha256": "b", "chunk_index": 0}

    def stages(self):
        return {name: [] for name in ("vector", "lexical", "fused_full", "fused_top60", "after_source_checks", "returned")}

    def test_final_cutoff_is_not_misdiagnosed_as_missing_recall(self):
        stages = self.stages()
        stages["vector"] = [self.target]
        for name in ("fused_full", "fused_top60", "after_source_checks"):
            stages[name] = [self.other]*20+[self.target]
        stages["returned"] = [self.other]*20
        result = target_summary(7, stages)
        self.assertEqual(result["loss_stage"], "final_top20_truncation")
        self.assertEqual(result["stages"]["vector"]["best_chunk_rank"], 1)
        self.assertEqual(result["stages"]["fused_full"]["best_chunk_rank"], 21)
        self.assertEqual(result["stages"]["fused_full"]["first_seen_paper_order"], 2)

    def test_fusion_top60_cutoff_is_distinct(self):
        stages = self.stages()
        stages["lexical"] = [self.target]
        stages["fused_full"] = [self.other]*60+[self.target]
        stages["fused_top60"] = [self.other]*60
        self.assertEqual(target_summary(7, stages)["loss_stage"], "fusion_top60_truncation")

    def test_window_miss_does_not_claim_corpus_absence(self):
        self.assertEqual(target_summary(7, self.stages())["loss_stage"], "absent_from_both_top60_not_proof_of_corpus_absence")

    def test_source_rejection_and_unavailable_authority_not_conflated(self):
        stages = self.stages()
        for name in ("vector", "fused_full", "fused_top60"):
            stages[name] = [self.target]
        self.assertEqual(target_summary(7, stages)["loss_stage"], "current_source_validation_filtered")
        self.assertEqual(target_summary(7, stages, source_checks_verified=False)["loss_stage"], "current_source_stage_unresolved")

    def test_returned_rank_and_both_leg_ranks_retained(self):
        stages = self.stages()
        for name in stages:
            stages[name] = [self.other, self.target]
        result = target_summary(7, stages)
        self.assertEqual(result["loss_stage"], "returned")
        self.assertEqual(result["stages"]["lexical"]["chunk_ranks"], [2])

    def test_identity_is_not_based_on_filename_or_snippet_only(self):
        one = {"content": "same", "metadata": self.target | {"source": "same.pdf", "page": 1}}
        two = {"content": "same", "metadata": self.target | {"source": "same.pdf", "page": 1, "content_sha256": "new"}}
        self.assertNotEqual(signature(pointer(one)), signature(pointer(two)))
        public = {"text": one["content"], **one["metadata"], "retrieval": {"rrf_score": .1}}
        self.assertEqual(signature(pointer(one)), signature(pointer(public)))

    def test_source_filter_reconstruction_requires_current_bytes_kind_and_hash(self):
        item = {"metadata": self.target | {"document_kind": "academic_paper"}}
        live = {"visibility_scope": "public", "review_status": "approved", "completed": True,
                "source_bytes_valid": True, "content_sha256": "a", "document_kind": "academic_paper"}
        self.assertTrue(valid_paper(item, live))
        for patch in ({"source_bytes_valid": False}, {"content_sha256": "new"}, {"document_kind": "standard"}, {"visibility_scope": "private"}):
            with self.subTest(patch=patch):
                self.assertFalse(valid_paper(item, live | patch))
        original = copy.deepcopy(item)
        valid_paper(item, live)
        self.assertEqual(item, original)


if __name__ == "__main__":
    unittest.main()
