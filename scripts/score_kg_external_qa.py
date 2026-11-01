"""Score QA predictions and independent support judgments; never infer a pass."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.knowledge_graph.external_qa_evaluation import evaluate_qasper, evaluate_multihop, rows, qa_intervals
from scripts.prepare_kg_external_benchmarks import write_json

ROOT = Path(__file__).resolve().parents[1] / "artifacts/knowledge_platform/external-benchmark-v1"


def load_predictions(path):
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        value = json.loads(text)
        if not isinstance(value, list):
            raise ValueError("predictions_must_be_list_or_JSONL")
        return value
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def run(dataset, partition, path, output, mode, judgments=None, selection=None):
    from framework.knowledge_graph.external_benchmark_freeze import require_mutable
    require_mutable(ROOT, output, output.with_name(output.stem+".items.jsonl"))
    if partition == "final":
        raise ValueError("final_QA_scoring_requires_future_confirmed_threshold_workflow")
    if mode == "live_backend_predictions":
        config = path.parent / "run-config.json"
        if not config.exists():
            raise ValueError("live_QA_predictions_require_run_config")
        source = json.loads(config.read_text(encoding="utf-8"))
        if source.get("prediction_mode") != "live_backend_predictions":
            raise ValueError("live_QA_prediction_provenance_marker_required")
        required = {"model", "backend", "corpus_sha256", "retrieval_budget", "generation_parameters"}
        if not required.issubset(source):
            raise ValueError("live_QA_run_config_incomplete")
    predictions = load_predictions(path)
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    support = rows(judgments) if judgments else []
    evaluator = evaluate_qasper if dataset == "qasper" else evaluate_multihop
    selected = None
    if selection:
        selected = json.loads(selection.read_text(encoding="utf-8"))["datasets"][dataset]
        if selected["partition"] != partition:
            raise ValueError("selection_partition_mismatch")
        if mode == "live_backend_predictions" and source.get("selection_sha256") != hashlib.sha256(selection.read_bytes()).hexdigest():
            raise ValueError("selection_not_frozen_in_generation_run")
    result = evaluator(ROOT, partition, predictions, judgments=support, prediction_hash=fingerprint,
                       question_ids=selected["question_ids"] if selected else None,
                       document_ids=selected["document_ids"] if selected else None)
    result.update(prediction_mode=mode, prediction_sha256=fingerprint, final_acceptance=False,
                  expert_certified=False, training_data_blind_test_certified=False,
                  prediction_path=str(path.resolve()), semantic_judgment_path=str(judgments.resolve()) if judgments else None)
    items = result.pop("items")
    result["document_group_bootstrap_95_intervals"] = qa_intervals(items)
    from framework.knowledge_graph.external_benchmark_data import dump_jsonl
    dump_jsonl(output.with_name(output.stem+".items.jsonl"), items)
    result["items_path"] = str(output.with_name(output.stem+".items.jsonl"))
    write_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=("qasper", "multihop_rag"))
    parser.add_argument("--partition", default="calibration", choices=("development", "calibration", "final"))
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("live_backend_predictions", "reference_replay", "integration_fixture"))
    parser.add_argument("--semantic-judgments", type=Path)
    parser.add_argument("--selection", type=Path)
    args = parser.parse_args()
    value = run(args.dataset, args.partition, args.predictions, args.output, args.mode, args.semantic_judgments, args.selection)
    print(json.dumps({"status": value["status"], "dataset": value["dataset"], "mode": value["prediction_mode"],
                      "supplementary": value["supplementary"], "semantic_support": value["semantic_support"]}))
