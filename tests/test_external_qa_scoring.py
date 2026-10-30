"""Offline QA scoring checks using fixed native calibration references."""
import json
from pathlib import Path
import tempfile
import unittest

from framework.knowledge_graph.external_qa_evaluation import (
    evaluate_qasper, evaluate_multihop, rows, refusal, source_retrieval, judge_scores,
)
from framework.knowledge_graph.external_qasper_scoring import load_official
from framework.knowledge_graph.external_benchmark_data import digest
from scripts.score_kg_external_qa import run

ROOT = Path(__file__).resolve().parents[1] / "artifacts/knowledge_platform/external-benchmark-v1"


class NativeQAScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qrefs = rows(ROOT / "references/qasper/dev.references.jsonl")
        papers = {}
        for ref in cls.qrefs:
            papers.setdefault(ref["document_id"], {"qas": []})["qas"].append({"question_id": ref["id"], "answers": ref["native_answers"]})
        options = load_official(ROOT).get_answers_and_evidence(papers, text_evidence_only=False)
        cls.qfixture = [{"question_id": identifier, "predicted_answer": choices[0]["answer"],
                         "predicted_evidence": choices[0]["evidence"]} for identifier, choices in options.items()]
        cls.mrefs = rows(ROOT / "references/multihop-v2/calibration.references.jsonl")
        cls.mfixture = []
        for ref in cls.mrefs:
            urls = sorted({e["url"] for e in ref["native_evidence_list"]})
            cls.mfixture.append({"question_id": ref["id"], "predicted_answer": ref["answer"],
                                 "predicted_evidence": [e["fact"] for e in ref["native_evidence_list"]],
                                 "retrieved": [{"document_id": "multihopdoc:"+digest(url), "block_id": "body"} for url in urls]})

    def test_qasper_native_replay_has_official_perfect_primary(self):
        result = evaluate_qasper(ROOT, "calibration", self.qfixture)
        self.assertEqual(result["official"]["Answer F1"], 1.)
        self.assertEqual(result["official"]["Evidence F1"], 1.)
        self.assertEqual(result["supplementary"]["questions"], 1005)
        self.assertEqual(result["semantic_support"]["status"], "inconclusive")

    def test_qasper_missing_fails_answerable_and_refusal(self):
        result = evaluate_qasper(ROOT, "calibration", [])
        self.assertEqual(result["official"]["Missing predictions"], 1005)
        self.assertEqual(result["official"]["Answer F1"], 0.)
        self.assertEqual(result["supplementary"]["answerable_completion_rate"], 0.)
        self.assertEqual(result["supplementary"]["correct_refusal_rate"], 0.)

    def test_multihop_native_replay_and_retrieval(self):
        result = evaluate_multihop(ROOT, "calibration", self.mfixture)
        self.assertEqual(result["official_formula_on_fixed_partition"]["any_token_overlap"], 1.)
        self.assertEqual(result["supplementary_exact_match"], 1.)
        self.assertEqual(result["supplementary"]["evidence_recall_at_5"], 1.)
        self.assertEqual(result["supplementary"]["correct_refusal_rate"], 1.)
        self.assertEqual(result["official_formula_on_fixed_partition"]["retrieval_questions"], 75)

    def test_multihop_missing_keeps_all132_questions(self):
        result = evaluate_multihop(ROOT, "calibration", [])
        self.assertEqual(result["questions"], 132)
        self.assertEqual(result["official_formula_on_fixed_partition"]["any_token_overlap"], 0.)
        self.assertEqual(result["supplementary"]["answerable_completion_rate"], 0.)
        self.assertEqual(result["supplementary"]["correct_refusal_rate"], 0.)

    def test_duplicate_cannot_replace_wrong_first_answer(self):
        for fn, fixture, field in [(evaluate_qasper, self.qfixture, "qasper"), (evaluate_multihop, self.mfixture, "multi")]:
            wrong = {"question_id": fixture[0]["question_id"], "predicted_answer": "__wrong__", "predicted_evidence": []}
            single = fn(ROOT, "calibration", [wrong])
            duplicate = fn(ROOT, "calibration", [wrong, fixture[0], {"question_id": "__wrong_source__", "predicted_answer": "anything"}])
            a = single["official"]["Answer F1"] if field == "qasper" else single["official_formula_on_fixed_partition"]["any_token_overlap"]
            b = duplicate["official"]["Answer F1"] if field == "qasper" else duplicate["official_formula_on_fixed_partition"]["any_token_overlap"]
            self.assertEqual(a, b)
            self.assertTrue(duplicate["invalid_records"])
            self.assertTrue(duplicate["duplicate_predictions"])

    def test_invalid_rank_and_text_cannot_promote_evidence(self):
        blocks = {("d", "b"): {"text": "actual evidence"}}
        source, invalid = source_retrieval({"retrieved": [{"document_id": "bad", "block_id": "b"}]*5 + [{"document_id": "d", "block_id": "b"}]}, blocks)
        self.assertEqual(source[0]["rank"], 6)
        self.assertEqual(len(invalid), 5)
        source, invalid = source_retrieval({"retrieved": [{"document_id": "d", "block_id": "b", "text": "fabricated evidence"}]}, blocks)
        self.assertFalse(source)
        self.assertTrue(invalid)

    def test_negative_answer_is_not_abstention(self):
        self.assertFalse(refusal("No"))
        self.assertFalse(refusal("The evidence explicitly denies the claim."))
        self.assertTrue(refusal("Unanswerable"))
        self.assertTrue(refusal("Insufficient information."))

    def test_semantic_judgments_require_independent_requests_and_matching_prediction(self):
        row = {"question_id": "q", "prediction_sha256": "hash", "phase": "independent_qa_semantic_judge", "state": "completed",
               "request_ids": ["ref-request", "answer-request"], "judgment": {"reference_support": "supported", "answer_support": "supported", "citation_support": "supported"}}
        good = judge_scores([row], {"q", "missing"}, "hash")
        self.assertEqual(good["judged"], 1)
        self.assertEqual(good["answer_supported_rate_lower_bound"], .5)
        self.assertEqual(good["status"], "inconclusive")
        self.assertEqual(judge_scores([row], {"q"}, "wrong_hash")["judged"], 0)
        self.assertEqual(judge_scores([{**row, "request_ids": ["same", "same"]}], {"q"}, "hash")["judged"], 0)

    def test_final_scoring_blocked_before_confirmed_thresholds(self):
        with self.assertRaises(ValueError):
            run("qasper", "final", Path("missing.jsonl"), Path("unused.json"), "integration_fixture")

    def test_semantic_reference_replay_cannot_trigger_model_calls(self):
        from scripts.judge_kg_external_qa import prepare
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "run-config.json").write_text(json.dumps({"prediction_mode": "reference_replay"}), encoding="utf-8")
            predictions = folder / "predictions.jsonl"
            predictions.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                prepare("qasper", "calibration", predictions, folder / "judgments")

    def test_scoring_entry_point_preserves_fixture_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            predictions = folder / "predictions.jsonl"
            predictions.write_text("\n".join(json.dumps(row) for row in self.mfixture), encoding="utf-8")
            result = run("multihop_rag", "calibration", predictions, folder / "score.json", "reference_replay")
            self.assertEqual(result["prediction_mode"], "reference_replay")
            self.assertFalse(result["final_acceptance"])
            self.assertEqual(result["status"], "inconclusive")
            self.assertTrue((folder / "score.items.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
