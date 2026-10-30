"""Export real native reference/prediction differences without changing labels."""
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.knowledge_graph.external_benchmark_data import dump_jsonl
from scripts.prepare_kg_external_benchmarks import write_json
from scripts.score_kg_external_relation_pilot import pilot_gold
from scripts.run_kg_external_relation_pilot import OUT


def main():
    run = OUT / "runs/redocred-pilot-v2-utf8"
    score = json.loads((run / "score.json").read_text(encoding="utf-8"))
    gold = pilot_gold()
    paths = list((run / "responses").glob("*.json"))
    paths.extend(OUT / row["path"] for row in json.loads((run / "reused-responses.json").read_text(encoding="utf-8")))
    results = {row["title"]: row for row in [json.loads(path.read_text(encoding="utf-8")) for path in paths]}
    items, support, tp, fp, fn = [], Counter(), Counter(), Counter(), Counter()
    errors_by_document = []
    for doc in gold:
        result = results[doc["title"]]
        expected = {(rel["r"], rel["h"], rel["t"]) for rel in doc["labels"]}
        actual = {(rel["r"], rel["h_idx"], rel["t_idx"]) for rel in result.get("predictions", [])} if result["state"] == "completed" else set()
        support.update(key[0] for key in expected)
        tp.update(key[0] for key in expected & actual)
        fp.update(key[0] for key in actual - expected)
        fn.update(key[0] for key in expected - actual)
        errors_by_document.append({"title": doc["title"], "state": result["state"],
                                   "finish_reason": result.get("finish_reason"), "expected": len(expected),
                                   "predicted": len(actual), "tp": len(expected & actual),
                                   "fp": len(actual - expected), "fn": len(expected - actual)})
        for category, keys in [("false_positive", actual - expected), ("false_negative", expected - actual)]:
            for rel, head, tail in sorted(keys):
                items.append({"title": doc["title"], "category": category, "r": rel, "h_idx": head, "t_idx": tail,
                              "source_native_mentions": doc["vertexSet"][head],
                              "target_native_mentions": doc["vertexSet"][tail],
                              "prediction_state": result["state"],
                              "adjudication": "not_manually_reclassified_native_label_difference"})
    dump_jsonl(OUT / "references/diagnostics/redocred-pilot-v2-errors.jsonl", items)
    summary = {"scope": score["scope"], "status": "inconclusive",
               "counts": {"tp": sum(tp.values()), "fp": sum(fp.values()), "fn": sum(fn.values())},
               "per_relation": {rel: {"support": support[rel], "tp": tp[rel], "fp": fp[rel], "fn": fn[rel]}
                                for rel in sorted(support.keys() | fp.keys())},
               "per_document": errors_by_document,
               "known_pipeline_errors": {"v1_unsent_GBK_failures": 4, "recovered_once_after_local_fix": 4,
                                         "v2_truncated_model_response_not_retried": 1},
               "reference_changes": 0, "model_tuning_during_pilot": False,
               "item_details": "references/diagnostics/redocred-pilot-v2-errors.jsonl"}
    write_json(OUT / "reports/redocred-pilot-errors-v1.json", summary)
    print(json.dumps(summary["counts"]))


if __name__ == "__main__":
    main()
