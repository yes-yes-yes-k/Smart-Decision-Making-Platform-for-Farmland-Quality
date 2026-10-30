"""R2.1 span transfer: map frozen offsets onto the re-parsed chunks."""
import unittest

from framework.knowledge_graph.span_transfer import transfer_references, transfer_span

PAGE_TEXT = "长期施用生物炭显著提高土壤有机碳，年际差异明显。"
OTHER_PAGE = "同一句话也出现在另一页用于检验作用域。"


def chunks():
    return [
        {"chunk_index": 0, "page": 1, "content": "目录\n第一章 引言"},
        {"chunk_index": 1, "page": 7, "content": PAGE_TEXT},
        {"chunk_index": 2, "page": 8, "content": OTHER_PAGE},
    ]


class TransferTests(unittest.TestCase):
    def test_exact_match_prefers_quote(self):
        result = transfer_span("显著提高土壤有机碳", 7, chunks())
        self.assertEqual(result["method"], "exact")
        self.assertEqual(result["chunk_index"], 1)
        self.assertEqual(result["start"], PAGE_TEXT.index("显著提高土壤有机碳"))

    def test_whitespace_difference_uses_normalized(self):
        result = transfer_span("长期施用 生物炭 显著提高", 7, chunks())
        self.assertEqual(result["method"], "normalized")
        self.assertEqual(result["chunk_index"], 1)

    def test_punctuation_difference_uses_normalized(self):
        result = transfer_span("土壤有机碳,年际差异明显。", 7, chunks())
        self.assertEqual(result["method"], "normalized")
        self.assertEqual(result["chunk_index"], 1)

    def test_one_character_noise_uses_alignment(self):
        result = transfer_span("长期施用生物炭显著提高土壤有极碳，年际差异明显。", 7, chunks())
        self.assertIsNotNone(result)
        self.assertEqual(result["method"], "aligned")
        self.assertGreaterEqual(result["score"], 0.9)
        self.assertEqual(result["chunk_index"], 1)

    def test_wrong_page_is_not_silently_mapped(self):
        self.assertIsNone(transfer_span("同一句话也出现在另一页", 7, chunks()))

    def test_candidates_scope_wins_over_other_chunks_on_page(self):
        scoped = chunks() + [{"chunk_index": 9, "page": 7, "content": PAGE_TEXT}]
        result = transfer_span(PAGE_TEXT, 7, scoped, candidates=[9])
        self.assertEqual(result["chunk_index"], 9)

    def test_empty_quote_returns_none(self):
        self.assertIsNone(transfer_span("", 7, chunks()))


class BatchTests(unittest.TestCase):
    def references(self):
        return [
            {"document_id": 1, "chunk_index": 50, "start": 0, "end": 8,
             "quote": "显著提高土壤有机碳", "page_one_based": 7},
            {"document_id": 1, "chunk_index": 51, "start": 0, "end": 6,
             "quote": "不存在的句子", "page_one_based": 7},
        ]

    def test_summary_and_position_change(self):
        report = transfer_references(
            self.references(),
            {1: chunks()},
            {1: {50: {"page": 7, "candidate_new_chunk_indexes": [1]},
                 51: {"page": 7, "candidate_new_chunk_indexes": [1]}}})
        self.assertEqual(report["summary"]["total"], 2)
        self.assertEqual(report["summary"]["mapped"], 1)
        self.assertEqual(report["summary"]["unmapped"], 1)
        first = report["rows"][0]
        self.assertTrue(first["position_changed"])
        self.assertEqual(first["chunk_index"], 1)

    def test_missing_mapping_falls_back_to_reference_page(self):
        report = transfer_references(self.references()[:1], {1: chunks()}, {})
        self.assertTrue(report["rows"][0]["mapped"])


if __name__ == "__main__":
    unittest.main()
