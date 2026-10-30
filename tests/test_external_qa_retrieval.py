"""Offline retrieval tests, explicitly authorized by the user in the prior turn."""
import unittest
from pathlib import Path
from framework.knowledge_graph.external_qa_retrieval import make_index_inputs, build_graph, rank, text_ranges
from framework.knowledge_graph.external_qa_evaluation import evaluate_qasper, rows

ROOT = Path(__file__).resolve().parents[1]/"artifacts/knowledge_platform/external-benchmark-v1"


class SourceBoundRetrievalTests(unittest.TestCase):
    def test_utf8_chunks_preserve_source_and_document_boundaries(self):
        text="Soil中国😊\n"*15
        intervals=list(text_ranges(text,16))
        self.assertEqual("".join(text[a:b] for a,b in intervals),text)
        self.assertTrue(all(len(text[a:b].encode())<=16 for a,b in intervals))
        chunks,units=make_index_inputs([{"id":name,"blocks":[{"id":"p","text":text}]} for name in ("a","b")],16)
        by_id={row["id"]:row for row in chunks}
        self.assertTrue(all({by_id[cid]["document_id"] for cid in unit["chunk_ids"]}=={unit["document_id"]} for unit in units))

    def fixture(self):
        chunks,units=make_index_inputs([{"id":"d","blocks":[{"id":"p","text":"Alice founded Example Labs."}]}])
        prediction={"unit_id":units[0]["id"],"origin":"model_graph_extractor","source_sha256":units[0]["text_sha256"],"state":"completed",
                    "entities":[{"title":"ALICE","type":"PERSON"},{"title":"EXAMPLE LABS","type":"ORGANIZATION"}],
                    "relationships":[{"source":"ALICE","target":"EXAMPLE LABS","description":"founded"}]}
        return chunks,units,prediction

    def test_reference_origin_and_wrong_source_are_rejected(self):
        _,units,prediction=self.fixture()
        with self.assertRaises(ValueError):build_graph([{**prediction,"origin":"reference"}],units)
        with self.assertRaises(ValueError):build_graph([{**prediction,"source_sha256":"bad"}],units)

    def test_real_graph_and_retrieval_budget(self):
        chunks,units,prediction=self.fixture();graph=build_graph([prediction],units)
        self.assertEqual(graph.number_of_edges(),1)
        selected,trace=rank(chunks,[[1.,0.]],[1.,0.],question="Who founded Example Labs?",graph=graph,units=units,arm="graphrag",byte_budget=4000)
        self.assertEqual(selected[0]["text"],chunks[0]["text"])
        self.assertEqual(trace["graph_contributing_chunks"],1)
        self.assertTrue(selected[0]["graph_edge_ids"])
        self.assertLessEqual(trace["source_utf8_bytes"],4000)

    def test_missing_graph_is_not_a_graph_arm(self):
        chunks,units,_=self.fixture()
        with self.assertRaises(ValueError):rank(chunks,[[1.,0.]],[1.,0.],question="Alice",graph=None,units=units,arm="graphrag")
        selected,_=rank(chunks,[[1.,0.]],[1.,0.],question="Alice",graph=None,units=units,arm="vector")
        self.assertEqual(len(selected),1)

    def test_partial_source_cannot_claim_full_evidence_recall(self):
        grouped={}
        for item in rows(ROOT/"adapters/qasper-evidence-v3/dev.jsonl"):grouped.setdefault(item["id"],[]).append(item)
        identifier=next(key for key,items in grouped.items() if any(item["matching_source_spans"] for item in items) and all(span["end"]-span["start"]>2 for item in items for span in item["matching_source_spans"]))
        ref=next(row for row in rows(ROOT/"references/qasper/dev.references.jsonl") if row["id"]==identifier)
        span=next(span for item in grouped[identifier] for span in item["matching_source_spans"])
        prediction={"question_id":identifier,"predicted_answer":"No","predicted_evidence":[],"retrieved":[{"document_id":ref["document_id"],"block_id":span["block_id"],"start":span["start"],"end":span["start"]+1}]}
        result=evaluate_qasper(ROOT,"calibration",[prediction],question_ids=[identifier],document_ids=[ref["document_id"]])
        self.assertEqual(result["supplementary"]["evidence_recall_at_5"],0.)
        self.assertEqual(result["supplementary"]["questions"],1)


if __name__=="__main__":unittest.main()
