"""Answerability reranking: order evidence by what it can answer."""
import copy
import unittest

from framework.knowledge_graph.answerability_rerank import rerank_values, score_chunk

QUERY = "长期施用生物炭对土壤有机碳有什么影响？"


def chunk(document_id, index, text, rank):
    return {"document_id": document_id, "chunk_index": index, "text": text,
            "retrieval": {"retrieval_ranks": {"vector": rank}}}


RESULT = ("连续施用 5 年生物炭后，土壤有机碳由 12.3 g/kg 提高到 18.6 g/kg，"
          "年际间差异显著，稻田处理增幅最大。")
TOC = "目录\n参考文献\n第一章 绪论\n第二章 材料与方法"
PLAIN = "本章介绍研究区域的概况与试验设计思路，未给出具体数值。"


class ScoreTests(unittest.TestCase):
    def test_result_chunk_beats_table_of_contents(self):
        good = score_chunk(QUERY, RESULT)
        bad = score_chunk(QUERY, TOC)
        self.assertGreater(good["score"], bad["score"])
        self.assertGreater(good["result_mentions"], 0)
        self.assertGreater(bad["noise_markers"], 0)

    def test_short_chunk_is_penalised(self):
        self.assertGreater(score_chunk(QUERY, "生物炭")["short_chunk_penalty"], 0)

    def test_concept_coverage_is_reported(self):
        signals = score_chunk(QUERY, RESULT)
        self.assertGreaterEqual(signals["concepts_covered"], 1)
        self.assertGreater(signals["concepts_total"], 0)


class RerankTests(unittest.TestCase):
    def values(self):
        return [chunk(1, 0, TOC, 1), chunk(1, 1, RESULT, 2), chunk(2, 0, PLAIN, 3)]

    def test_reorders_without_dropping_or_adding(self):
        original = self.values()
        ordered, trace = rerank_values(QUERY, original)
        self.assertEqual(len(ordered), len(original))
        self.assertEqual({(v["document_id"], v["chunk_index"]) for v in ordered},
                         {(v["document_id"], v["chunk_index"]) for v in original})
        self.assertEqual((ordered[0]["document_id"], ordered[0]["chunk_index"]), (1, 1))
        self.assertEqual(trace["candidates"], 3)

    def test_input_is_not_mutated(self):
        original = self.values()
        snapshot = copy.deepcopy(original)
        rerank_values(QUERY, original)
        self.assertEqual(original, snapshot)

    def test_ties_keep_original_order(self):
        first = chunk(1, 0, PLAIN, 1)
        second = chunk(2, 0, PLAIN, 2)
        ordered, _ = rerank_values(QUERY, [first, second])
        self.assertEqual([item["document_id"] for item in ordered], [1, 2])

    def test_trace_records_original_rank_and_signals(self):
        _, trace = rerank_values(QUERY, self.values())
        ranks = sorted(entry["original_rank"] for entry in trace["scores"])
        self.assertEqual(ranks, [1, 2, 3])
        self.assertTrue(all("concept_coverage" in entry for entry in trace["scores"]))


if __name__ == "__main__":
    unittest.main()


class _Store:
    def __init__(self, items, mode="hybrid"):
        self.items, self.mode = items, mode

    def hybrid_search(self, query, n_results=20, filters=None, **kwargs):
        return {"results": self.items[:n_results], "retrieval": {"mode": self.mode}}


class _Sources:
    def lookup_many(self, ids, owner_id, require_academic=False):
        return {document_id: {"title": f"doc {document_id}", "document_kind": "academic_paper",
                              "content_sha256": "a" * 64, "version": "v1", "visibility_scope": "public",
                              "review_status": "approved", "completed": True, "source_bytes_valid": True}
                for document_id in ids}


def item(document_id, index, text, rank):
    return {"content": text, "retrieval_ranks": {"vector": rank},
            "metadata": {"document_id": document_id, "document_kind": "academic_paper",
                         "content_sha256": "a" * 64, "chunk_index": index, "page": 1}}


class SearchIntegrationTests(unittest.TestCase):
    def test_search_applies_answerability_rerank_only_when_requested(self):
        from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch
        store = _Store([item(1, 0, TOC, 1), item(1, 1, RESULT, 2), item(2, 0, PLAIN, 3)])
        search = PublishedCorpusSearch(store, _Sources(), rerank="answerability")
        response = search.search(1, {"query": QUERY, "limit": 3})
        self.assertIn("rerank", response)
        self.assertEqual(response["sources"][0]["chunk_index"], 1)
        self.assertEqual(response["rerank"]["version"], "answerability-rerank-v1")

        plain = PublishedCorpusSearch(store, _Sources())
        self.assertNotIn("rerank", plain.search(1, {"query": QUERY, "limit": 3}))
