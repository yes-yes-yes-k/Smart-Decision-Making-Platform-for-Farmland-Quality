"""Prepare reviewable extraction gates and a final-QA request lower bound."""
from pathlib import Path
import json
import math
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.prepare_kg_external_benchmarks import write_json
from framework.knowledge_graph.external_benchmark_budget import open_external_budget

ROOT=Path(__file__).resolve().parents[1]/"artifacts/knowledge_platform/external-benchmark-v1"


def main():
    score=json.loads((ROOT/"runs/redocred-calibration-v1/score.json").read_text(encoding="utf-8"))
    predicted=score["tp"]+score["fp"]
    rules={"schema":"external-extraction-threshold-proposal-v1","status":"proposed_not_confirmed",
           "scope":"native_given_entity_relation_benchmark_only","priority":"control_false_relations_with_recall_and_completion_floor",
           "thresholds":{"relation_precision_min":.95,"relation_recall_min":.60,"valid_completion_min":.98,"model_exclusion_max":0.},
           "uncertainty":"report_document_bootstrap_intervals_no_additional_CI_gate_without_confirmation",
           "per_type_support_diagnostic":{"facts":30,"document_groups":10,"insufficient_support_status":"inconclusive_not_removed_from_global_score"},
           "evidence_support":"not_measurable_from_native_revised_relation_labels_not_a_production_evidence_pass",
           "entity_extraction":"not_evaluated_given_entities_are_task_input","user_confirmation":None,
           "calibration_counterfactual":{"prediction_count":predicted,"max_FP_at_same_prediction_count":math.floor(.05*predicted),
               "actual_FP":score["fp"],"reference_relations":score["expected"],"max_FN":score["expected"]-math.ceil(.60*score["expected"]),
               "actual_FN":score["fn"],"documents":499,"max_failed_documents":499-math.ceil(.98*499),
               "actual_failed_documents":499-score["completed_documents"],"would_meet_proposed_gates":False},
           "final_acceptance_run":False,"thresholds_must_not_be_lowered_after_final_results":True}
    write_json(ROOT/"reports/extraction-threshold-proposal-v1.json",rules)
    q_count=sum(1 for _ in (ROOT/"normalized/qasper/test.questions.jsonl").open(encoding="utf-8"))
    m_count=sum(1 for _ in (ROOT/"normalized/multihop-v2/final.questions.jsonl").open(encoding="utf-8"))
    n=q_count+m_count
    budget=open_external_budget(ROOT).summary()
    plan={"status":"inconclusive_requires_explicit_final_scope_or_budget_decision",
          "native_QASPER_final_questions":q_count,"custom_grouped_MultiHop_final_questions":m_count,
          "two_arm_answer_requests_without_retries":2*n,"separate_reference_and_answer_judge_requests_per_arm":4*n,
          "lower_bound_requests_excluding_graph_embedding_and_retries":6*n,
          "even_sharing_reference_judgments_across_arms_lower_bound":5*n,
          "remaining_request_cap_now":budget["caps"]["requests"]-budget["requests"],
          "global_request_cap":5000,"global_token_cap":20000000,
          "final_corpus_graph_building_not_included":True,
          "no_automatic_scope_reduction":True,"no_automatic_total_cap_increase":True,
          "next_action":"Finish frozen nonfinal trial, then submit exact full-scope cost and an explicitly labeled deterministic subset alternative for user choice before final scoring."}
    write_json(ROOT/"reports/final-QA-budget-gap-v1.json",plan)
    print(json.dumps({"rules_status":rules["status"],"final_QA_min_requests":6*n,"global_request_cap":5000}))


if __name__=="__main__":main()
