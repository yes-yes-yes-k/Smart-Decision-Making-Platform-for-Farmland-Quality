"""Finalize completed calibration evidence; does not run final acceptance."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.knowledge_graph.external_benchmark_data import dump_jsonl
from scripts.prepare_kg_external_benchmarks import write_json
from scripts.run_kg_external_calibration import OUT, RUN, prepare
from scripts.score_kg_external_calibration import main as rescore


def main():
    manifest = OUT / "reports/calibration-result-manifest-v1.json"
    if manifest.exists():
        frozen = json.loads(manifest.read_text(encoding="utf-8"))
        for name, expected in frozen["files"].items():
            if hashlib.sha256((OUT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("frozen_calibration_result_changed:"+name)
        print(json.dumps({"status": "already_frozen_unchanged", "documents": frozen["documents"], "files_verified": len(frozen["files"])}))
        return
    jobs, config = prepare()  # Recheck all frozen request/source dependencies.
    state = json.loads((RUN / "run-state.json").read_text(encoding="utf-8"))
    if state["state"] != "completed" or state.get("saved") != 499:
        raise ValueError("calibration_batch_not_complete")
    rescore()
    score = json.loads((RUN / "score.json").read_text(encoding="utf-8"))
    if score["pending_documents"] or score["budget"]["inflight"]:
        raise ValueError("pending_results_or_inflight_requests")
    ids = {job["input"]["title"]: job["input"]["id"] for job in jobs}
    results = {}
    for path in (RUN / "responses").glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        results[row["title"]] = row
    gold = [doc for doc in json.loads((OUT / "sources/redocred/data/dev_revised.json").read_text(encoding="utf-8")) if doc["title"] in ids]
    errors, expected_count, tp, fp, fn = [], Counter(), Counter(), Counter(), Counter()
    failure_kinds, diagnostic_kinds = Counter(), Counter()
    for doc in gold:
        output = results[doc["title"]]
        expected = {(row["r"], row["h"], row["t"]) for row in doc["labels"]}
        actual = {(row["r"], row["h_idx"], row["t_idx"]) for row in output.get("predictions", [])} if output["state"] == "completed" else set()
        expected_count.update(key[0] for key in expected)
        tp.update(key[0] for key in actual & expected)
        fp.update(key[0] for key in actual - expected)
        fn.update(key[0] for key in expected - actual)
        if output["state"] != "completed":
            failure_kinds[output.get("error", "unknown")] += 1
        for category, keys in [("false_positive", actual - expected), ("false_negative", expected - actual)]:
            for relation, head, tail in sorted(keys):
                if category == "false_positive":
                    reason = "self_pair" if head == tail else "direction_differs_from_reference" if (relation, tail, head) in expected else "predicate_differs_from_reference" if any(h==head and t==tail for _,h,t in expected) else "not_in_native_reference"
                else:
                    reason = "failed_response" if output["state"] != "completed" else "reverse_direction_predicted" if (relation, tail, head) in actual else "other_predicate_predicted" if any(h==head and t==tail for _,h,t in actual) else "omitted_from_valid_response"
                diagnostic_kinds[category+":"+reason] += 1
                errors.append({"id": ids[doc["title"]], "title": doc["title"], "category": category,
                               "diagnostic": reason, "r": relation, "h_idx": head, "t_idx": tail,
                               "source_native_mentions": doc["vertexSet"][head], "target_native_mentions": doc["vertexSet"][tail],
                               "meaning": "difference_from_native_reference_not_independent_source_adjudication"})
    if sum(tp.values()) != score["tp"] or sum(fn.values()) != score["fn"]:
        raise ValueError("calibration_error_counts_disagree")
    dump_jsonl(OUT / "references/diagnostics/redocred-calibration-v1-errors.jsonl", errors)
    summary = {"status": "inconclusive", "scope": score["scope"], "saved_documents": 499,
               "valid_completed_documents": score["completed_documents"], "failed_documents": len(score["failures"]),
               "failure_kinds": dict(failure_kinds), "counts": {"tp": score["tp"], "fp": score["fp"], "fn": score["fn"]},
               "diagnostic_counts": dict(diagnostic_kinds), "invalid_record_count": len(score["invalid_predictions"]),
               "per_relation": {key: {"support": expected_count[key], "tp": tp[key], "fp": fp[key], "fn": fn[key]}
                                for key in sorted(expected_count.keys() | fp.keys())},
               "item_details": "references/diagnostics/redocred-calibration-v1-errors.jsonl", "model_tuning_during_calibration": False,
               "final_acceptance": False, "thresholds_confirmed": False}
    write_json(OUT / "reports/calibration-errors-v1.json", summary)
    frozen = {}
    for path in list((RUN / "responses").glob("*.json")) + [RUN/"jobs.jsonl", RUN/"run-config.json", RUN/"request-estimates.json", RUN/"run-state.json", RUN/"score.json", OUT/"reports/calibration-errors-v1.json", OUT/"reports/calibration-budget-v1.json", OUT/"references/diagnostics/redocred-calibration-v1-errors.jsonl"]:
        frozen[str(path.relative_to(OUT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    sources = list(config["implementation_and_input_hashes"])
    sources += ["scripts/score_kg_external_calibration.py", "scripts/score_kg_external_relation_pilot.py",
                "framework/knowledge_graph/external_benchmark_scoring.py", "scripts/finalize_kg_external_calibration.py"]
    repo = OUT.parents[2]
    sources += [str((OUT / name).relative_to(repo)) for name in ["sources/redocred/data/dev_revised.json",
                "sources/redocred/evaluation.py", "sources/redocred/snapshot.json", "sources/redocred/LICENSE", "sources/redocred/README.md"]]
    for name in sources:
        path = repo / name
        target = RUN / "frozen-code-and-config" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        blob = path.read_bytes()
        if target.exists() and target.read_bytes() != blob:
            raise ValueError("frozen_dependency_copy_changed")
        target.write_bytes(blob)
        frozen[str(target.relative_to(OUT))] = hashlib.sha256(blob).hexdigest()
    write_json(OUT / "reports/calibration-result-manifest-v1.json", {"status": "calibration_complete_not_acceptance",
               "created_at": datetime.now(timezone.utc).isoformat(), "documents": 499, "files": frozen,
               "budget_checkpoint": score["budget"], "thresholds_confirmed": False})
    print(json.dumps({"saved": 499, "completed": score["completed_documents"], "failures": len(score["failures"]),
                      "precision": score["precision"], "recall": score["recall"], "f1": score["f1"], "budget": score["budget"]}))


if __name__ == "__main__":
    main()
