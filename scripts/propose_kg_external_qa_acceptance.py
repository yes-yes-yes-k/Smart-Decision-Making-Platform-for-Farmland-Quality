"""Submit QA gate recommendations; never confirm gates or run final data."""
import json
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_kg_external_qa_pilot_v2 import RUN, OUT, read
from scripts.prepare_kg_external_benchmarks import write_json
from framework.knowledge_graph.external_qa_evaluation import refusal


def main():
    from framework.knowledge_graph.external_benchmark_freeze import require_mutable
    require_mutable(OUT, OUT/"reports/qa-threshold-proposal-v1.json")
    pilot = json.loads((OUT/"reports/real-QA-pilot-v2.json").read_text(encoding="utf-8"))
    rules = {"valid_completion_min": .98, "answerable_completion_min": .80,
             "correct_refusal_min": .95, "asserted_answer_support_min": .95,
             "citing_answer_support_min": .95, "model_exclusion_max": 0.,
             "reference_evidence_recall_at_5_min": .80}
    report = {"status": "proposed_not_confirmed", "user_confirmation": None, "final_acceptance": False,
              "priority": "control_unsupported_answers_without_rewarding_refusal_of_answerable_questions",
              "rules": rules,
              "answer_quality_by_dataset": {"qasper_official_Answer_F1_min": .60, "multihop_supplementary_token_F1_min": .60},
              "rationale": "Business tolerance proposal, not a threshold fitted to pass this pilot. Native MultiHop any-token overlap is diagnostic, not an accuracy gate.",
              "reference_evidence_granularity": {"qasper": "exact_source_span", "multihop_rag": "exact_body_fact_span_diagnostic_alongside_native_document_retrieval"},
              "minimum_support_proposal": {"answerable_questions_per_dataset": 50, "unanswerable_questions_per_dataset": 30,
                  "asserted_and_citing_answers_per_rate": 30, "independent_document_or_support_groups": 30,
                  "if_insufficient": "inconclusive_even_if_observed_rate_is_100_percent"},
              "missing_or_invalid_predictions": "count_as_noncompletion_and_missed_answer_or_refusal",
              "unknown_or_failed_judgments": "not_supported_in_fixed_denominator_no_model_chosen_exclusions",
              "reference_problems": "freeze_and_report_no_posthoc_answer_or_question_exclusion",
              "uncertainty": "report_document_group_bootstrap_intervals; no unconfirmed_interval_gate",
              "same_model_judge_bias": True, "expert_certified": False, "pilot_impact": {}}
    for dataset, value in pilot["datasets"].items():
        arms = {}
        for arm, metrics in value["arms"].items():
            path = RUN/dataset/arm
            items = read(path/"score.items.jsonl")
            predictions = {row["question_id"]: row for row in read(path/"predictions.jsonl")}
            judgments = {row["question_id"]: row["judgment"] for row in read(path/"semantic-v1/judgments.jsonl")}
            answerable = [row for row in items if row["category"] == "answerable"]
            unanswerable = [row for row in items if row["category"] == "unanswerable"]
            asserted = metrics["asserted_answer_grounding"]["answers"]
            cited = metrics["citation_query_grounding"]["citing_answers"]
            supported_completion = sum(row["completed"] and not row["refused"] and judgments.get(row["question_id"], {}).get("answer_support") == "supported" for row in answerable)
            arms[arm] = {"questions": len(items), "answerable": len(answerable), "unanswerable": len(unanswerable),
                         "max_invalid_predictions": len(items)-math.ceil(.98*len(items)),
                         "max_answerable_noncompletion": len(answerable)-math.ceil(.80*len(answerable)),
                         "max_incorrect_refusals": len(unanswerable)-math.ceil(.95*len(unanswerable)),
                         "max_unsupported_assertions_at_current_count": asserted-math.ceil(.95*asserted),
                         "max_unsupported_citing_answers_at_current_count": cited-math.ceil(.95*cited),
                         "observed_answerable_completion": metrics["supplementary"]["answerable_completion_rate"],
                         "observed_supported_answerable_completion": supported_completion/len(answerable) if answerable else None,
                         "observed_answer_support": metrics["asserted_answer_grounding"]["support_rate_lower_bound"],
                         "observed_refusal_rate": metrics["supplementary"]["correct_refusal_rate"],
                         "native_answer_metric": metrics["native_answer_metric"], "native_answer_score": metrics["native_answer_score"],
                         "support_is_sufficient": False, "formal_result": "inconclusive"}
        report["pilot_impact"][dataset] = arms
    write_json(OUT/"reports/qa-threshold-proposal-v1.json", report)
    print(json.dumps({"status": report["status"], "final_acceptance": False}))


if __name__ == "__main__":
    main()
