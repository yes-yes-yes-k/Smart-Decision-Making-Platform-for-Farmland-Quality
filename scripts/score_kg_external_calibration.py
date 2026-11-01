"""Score the full frozen calibration denominator, including missing records."""
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.knowledge_graph.external_benchmark_budget import open_external_budget
from framework.knowledge_graph.external_benchmark_scoring import score_relations
from scripts.score_kg_external_relation_pilot import official_primary
from scripts.prepare_kg_external_benchmarks import write_json
from scripts.run_kg_external_calibration import OUT, RUN


def main():
    frozen_path = OUT / "reports/calibration-result-manifest-v1.json"
    if frozen_path.exists():
        import hashlib
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        for name, expected in frozen["files"].items():
            if hashlib.sha256((OUT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("frozen_calibration_result_changed:"+name)
        prior = json.loads((RUN / "score.json").read_text(encoding="utf-8"))
        print(json.dumps({"status": "frozen_calibration_read_only", "saved_documents": prior["saved_documents"],
                          "precision": prior["precision"], "recall": prior["recall"], "f1": prior["f1"]}))
        return
    jobs = [json.loads(line) for line in (RUN / "jobs.jsonl").read_text(encoding="utf-8").splitlines()]
    selected = {row["input"]["title"] for row in jobs}
    documents = [doc for doc in json.loads((OUT / "sources/redocred/data/dev_revised.json").read_text(encoding="utf-8")) if doc["title"] in selected]
    if len(documents) != 499 or len(selected) != 499:
        raise ValueError("full_calibration_denominator_changed")
    valid_ids = {row["input"]["id"]: row for row in jobs}
    predictions, completed, failures, seen = [], [], [], set()
    invalid_raw = 0
    for path in (RUN / "responses").glob("*.json"):
        result = json.loads(path.read_text(encoding="utf-8"))
        identifier = result["id"]
        if identifier not in valid_ids or identifier in seen:
            raise ValueError("unexpected_or_duplicate_calibration_result")
        seen.add(identifier)
        if result["input_request_sha256"] != valid_ids[identifier]["expected_request_sha256"]:
            raise ValueError("calibration_result_request_hash_mismatch")
        if result["state"] == "completed":
            completed.append(result["title"])
            predictions.extend(result["predictions"])
            for index in result.get("invalid_record_indices", []):
                row = result["candidate_relations"][index]
                predictions.append({**row, "title": result["title"]} if isinstance(row, dict) else {"title": result["title"]})
                invalid_raw += 1
        else:
            failures.append({"id": identifier, "error": result.get("error"), "finish_reason": result.get("finish_reason")})
    result = score_relations(documents, predictions, completed_titles=completed)
    if not invalid_raw:
        official = official_primary(documents, predictions)
        if any(abs(official[key]-result[key]) > 1e-12 for key in official):
            raise ValueError("calibration_official_primary_metric_disagreement")
    else:
        official = {"status": "not_equivalent_invalid_predictions_penalized_by_wrapper"}
    import numpy as np
    counts = np.array([[row["tp"], row["fp"], row["fn"]] for row in result["by_document"]])
    generator = np.random.default_rng(20261029)
    samples = generator.integers(0, len(counts), size=(2000, len(counts)))
    totals = counts[samples].sum(axis=1)
    totals[:, 1] += result["fp"] - counts[:, 1].sum()
    p = np.divide(totals[:, 0], totals[:, 0]+totals[:, 1], out=np.zeros(2000), where=totals[:, 0]+totals[:, 1]>0)
    r = np.divide(totals[:, 0], totals[:, 0]+totals[:, 2], out=np.zeros(2000), where=totals[:, 0]+totals[:, 2]>0)
    f = np.divide(2*p*r, p+r, out=np.zeros(2000), where=p+r>0)
    expected_types = Counter(rel["r"] for doc in documents for rel in doc["labels"])
    state_path = RUN / "run-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"state": "not_started"}
    result.update(status="inconclusive", scope="complete_499_document_effective_calibration_not_final_acceptance",
                  official_dev_documents=500, source_overlap_inactive_documents=1,
                  saved_documents=len(seen), pending_documents=499-len(seen), failures=failures,
                  execution_state=state["state"], scores_provisional=len(seen)!=499 or state["state"]=="running",
                  publisher_primary=official, native_relation_support=dict(sorted(expected_types.items())),
                  document_bootstrap_95_interval={key: np.quantile(value, [.025, .975]).tolist() for key, value in [("precision", p), ("recall", r), ("f1", f)]},
                  bootstrap={"resamples": 2000, "seed": 20261029, "unit": "document"},
                  budget=open_external_budget(OUT).summary(), final_acceptance=False,
                  task="given_entity_relation_native_ontology_custom_prompt")
    write_json(RUN / "score.json", result)
    print(json.dumps({key: result[key] for key in ["execution_state", "saved_documents", "pending_documents", "completion_rate", "precision", "recall", "f1", "budget"]}))


if __name__ == "__main__":
    main()
