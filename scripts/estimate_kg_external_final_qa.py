"""Source-only final-scope cost forecast; no labels, indexing or API calls."""
import json
import math
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
from scripts.prepare_kg_external_qa_pilot_v2 import OUT, read
from scripts.run_kg_external_qa_pilot_v2 import graph_options, EMBED
from framework.knowledge_graph.external_qa_metadata import make_index_inputs, metadata_block
from framework.knowledge_graph.external_benchmark_budget import open_external_budget
from scripts.prepare_kg_external_benchmarks import write_json


def reserve(options):
    return len(json.dumps(options, ensure_ascii=False).encode())+options["max_tokens"]+1024


def main():
    budget = open_external_budget(OUT).summary()
    report = {"status": "inconclusive_scope_or_cap_decision_required", "model_calls": 0,
              "final_predictions_or_graph_generated": False, "final_reference_answers_read": False,
              "configuration_basis": "same_source_and_request_parameters_as_nonfinal_QA_v2",
              "automatic_scope_reduction": False, "datasets": {}, "budget_now": budget}
    for dataset in ("qasper", "multihop_rag"):
        if dataset == "qasper":
            docs = [{**doc, "blocks": [*doc["blocks"], metadata_block(doc, dataset)]}
                    for doc in read(OUT/"normalized/qasper-v2/test.corpus.jsonl")]
            questions = read(OUT/"normalized/qasper/test.questions.jsonl")
        else:
            docs = [{"id": doc["id"], "blocks": [{"id": "body", "text": doc["native_article"]["body"]}, metadata_block(doc, dataset)]}
                    for doc in read(OUT/"normalized/multihop-v2/final.corpus.jsonl")]
            questions = read(OUT/"normalized/multihop-v2/final.questions.jsonl")
        chunks, units = make_index_inputs(docs)
        graph = sum(reserve(graph_options(unit["text"])) for unit in units)
        texts = [chunk["text"] for chunk in chunks]+[question["question"] for question in questions]
        embedding = sum(reserve({"model": EMBED, "input": texts[i:i+8], "encoding_format": "float", "max_tokens": 0}) for i in range(0, len(texts), 8))
        answer_requests, judge_requests = 2*len(questions), 4*len(questions)
        report["datasets"][dataset] = {"documents": len(docs), "questions": len(questions), "source_chunks": len(chunks),
             "graph_requests": len(units), "embedding_requests": math.ceil(len(texts)/8), "answer_requests": answer_requests,
             "independent_judge_requests": judge_requests,
             "first_attempt_requests_without_retries": len(units)+math.ceil(len(texts)/8)+answer_requests+judge_requests,
             "graph_exact_first_attempt_reservation": graph, "embedding_exact_first_attempt_reservation": embedding,
             "answer_conservative_allowance": answer_requests*32000, "semantic_conservative_allowance": judge_requests*64000}
    jobs = sum(value["first_attempt_requests_without_retries"] for value in report["datasets"].values())
    tokens = sum(sum(value[key] for key in ("graph_exact_first_attempt_reservation", "embedding_exact_first_attempt_reservation", "answer_conservative_allowance", "semantic_conservative_allowance")) for value in report["datasets"].values())
    report.update(first_attempt_requests=jobs, requests_with_historical_consumption=jobs+budget["requests"],
                  first_attempt_reservation_and_allowances=tokens, reservations_with_current_consumption=tokens+budget["tokens_charged_or_reserved"],
                  within_existing_request_cap=jobs+budget["requests"] <= 5000,
                  within_existing_token_reservation_cap=tokens+budget["tokens_charged_or_reserved"] <= 20_000_000,
                  allowances_not_billed_usage=True, transient_retry_contingency_not_included=True,
                  next_action="User must confirm numeric gates and final scope/caps. A subset needs its own deterministic pre-prediction selection and cost freeze; not a full-native score.")
    write_json(OUT/"reports/final-QA-full-scope-budget-v2.json", report)
    print(json.dumps({"requests": jobs, "first_attempt_reservation_and_allowances": tokens, "no_model_calls": True}))


if __name__ == "__main__":
    main()
