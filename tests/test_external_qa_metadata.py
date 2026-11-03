"""Offline source adaptation checks, covered by existing user authorization."""
import unittest

from framework.knowledge_graph.external_qa_metadata import metadata_block, make_index_inputs
from framework.knowledge_graph.external_qa_retrieval import make_index_inputs as original_inputs
from framework.knowledge_graph.external_qa_evaluation import source_retrieval


class NativeMetadataTests(unittest.TestCase):
    def test_native_fields_only_and_no_inferred_answers(self):
        doc = {"native_article": {"title": "Article", "published_at": "2023-01-02", "source": "Publisher",
                                  "author": "Writer", "body": "Text", "answer": "SECRET"}}
        block = metadata_block(doc, "multihop_rag")
        self.assertIn("2023-01-02", block["text"])
        self.assertIn("Writer", block["text"])
        self.assertNotIn("SECRET", block["text"])
        self.assertNotIn("Text", block["text"])
        self.assertNotIn("published_at", metadata_block({"title": "Paper"}, "qasper")["text"])

    def test_original_body_units_and_spans_are_identical(self):
        doc = {"id": "d", "title": "Title", "blocks": [{"id": "body", "text": "Soil中文 " * 25}]}
        chunks, units = original_inputs([doc], 40)
        metadata = metadata_block(doc, "qasper")
        new_chunks, new_units = make_index_inputs([{**doc, "blocks": [*doc["blocks"], metadata]}], 40)
        self.assertEqual([r for r in new_chunks if r["block_id"] != "source_metadata"], chunks)
        mapping = {row["id"]: row for row in new_units}
        self.assertTrue(all(mapping[row["id"]] == row for row in units))
        body_ids = {row["id"] for row in chunks}
        self.assertTrue(all(not (set(row["chunk_ids"]) & body_ids) or set(row["chunk_ids"]) <= body_ids for row in new_units))

    def test_source_metadata_must_match_original_not_invented_date(self):
        block = metadata_block({"native_article": {"published_at": "2023-01-02"}}, "multihop_rag")
        blocks = {("d", "source_metadata"): block}
        pointer = {"document_id": "d", "block_id": "source_metadata", "text": block["text"]}
        valid, errors = source_retrieval({"retrieved": [pointer]}, blocks)
        self.assertEqual(len(valid), 1)
        self.assertFalse(errors)
        valid, errors = source_retrieval({"retrieved": [{**pointer, "text": block["text"].replace("2023", "2024")}]}, blocks)
        self.assertFalse(valid)
        self.assertTrue(errors)

    def test_document_metadata_hit_is_not_supporting_fact_hit(self):
        from scripts.audit_kg_external_qa_evidence import fact_coverage
        docs = [{"id": "d", "native_article": {"url": "u", "body": "Alice founded Labs."}}]
        evidence = [{"url": "u", "fact": "Alice founded Labs."}]
        metadata = [{"rank": 1, "document_id": "d", "block_id": "source_metadata", "start": 0, "end": 50}]
        self.assertEqual(fact_coverage(evidence, metadata, docs)["hits"], 0)
        fragments = [{"rank": i+1, "document_id": "d", "block_id": "body", "start": a, "end": b}
                     for i, (a,b) in enumerate([(0, 8), (8, 19)])]
        self.assertEqual(fact_coverage(evidence, fragments, docs)["hits"], 1)
        self.assertEqual(fact_coverage(evidence, fragments[:1], docs)["hits"], 0)

    def test_frozen_results_cannot_be_overwritten_by_rescoring(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json
        from framework.knowledge_graph.external_benchmark_freeze import require_mutable
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"reports").mkdir()
            (root/"reports/qa-pilot-result-manifest-v1.json").write_text(json.dumps({"files": {"runs/v1/score.json": "hash"}}))
            with self.assertRaises(ValueError):
                require_mutable(root, root/"runs/v1/score.json")
            with self.assertRaises(ValueError):
                require_mutable(root, root/"runs/v1")
            require_mutable(root, root/"runs/v2/score.json")


if __name__ == "__main__":
    unittest.main()
