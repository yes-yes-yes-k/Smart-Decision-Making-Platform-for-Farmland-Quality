"""Score native pilot records and compare primary metrics to publisher code."""
import ast
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.knowledge_graph.external_benchmark_scoring import score_relations
from scripts.prepare_kg_external_benchmarks import write_json
from scripts.run_kg_external_relation_pilot import OUT, RUN


def official_primary(documents, predictions):
    source = OUT / "sources/redocred/evaluation.py"
    snapshot = json.loads((OUT / "sources/redocred/snapshot.json").read_text(encoding="utf-8"))
    expected = next(row["sha256"] for row in snapshot["files"] if row["path"].replace("\\", "/").endswith("/evaluation.py"))
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise ValueError("publisher_scorer_hash_changed")
    # Execute only the reviewed, unchanged native function definitions, omitting
    # unrelated global model helpers and their absent meta/rel2id dependency.
    parsed = ast.parse(source.read_text(encoding="utf-8"))
    functions = [node for node in parsed.body if isinstance(node, ast.FunctionDef)
                 and node.name in {"gen_train_facts", "official_evaluate"}]
    if len(functions) != 2:
        raise ValueError("publisher_scorer_interface_changed")
    namespace = {"os": os, "json": json}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
    with tempfile.TemporaryDirectory(prefix="native_relation_scoring_") as temp:
        root = Path(temp)
        (root / "native.json").write_text(json.dumps(documents), encoding="utf-8")
        # Native evaluator always reads these for its auxiliary IgnF1 metrics.
        # Those metrics are deliberately NOT returned/certified here; empty
        # caches have no dependency path into primary P/R/F1 computation.
        (root / "train.json").write_text("[]", encoding="utf-8")
        (root / "train_distant.json").write_text("[]", encoding="utf-8")
        result = namespace["official_evaluate"]([dict(row) for row in predictions], str(root), "train.json", "native.json")
    return {"precision": result[4], "recall": result[5], "f1": result[0]}


def pilot_gold():
    config = json.loads((RUN / "run-config.json").read_text(encoding="utf-8"))
    selected = set(config["job_hashes"])
    inputs = [json.loads(line) for line in (OUT / "normalized/redocred/train.inputs.jsonl").read_text(encoding="utf-8").splitlines()]
    titles = {row["title"] for row in inputs if row["id"] in selected}
    documents = json.loads((OUT / "sources/redocred/data/train_revised.json").read_text(encoding="utf-8"))
    return [doc for doc in documents if doc["title"] in titles]


def scorer_audit(documents):
    native_gold = [{"title": doc["title"], "h_idx": rel["h"], "t_idx": rel["t"], "r": rel["r"]}
                   for doc in documents for rel in doc["labels"]]
    scenarios = {"reference_round_trip_not_backend": native_gold, "missing_predictions": [],
                 "repeated_prediction": native_gold + native_gold[:1],
                 "wrong_direction": [{**row, "h_idx": row["t_idx"], "t_idx": row["h_idx"]} for row in native_gold]}
    parity = {}
    for name, predictions in scenarios.items():
        ours = score_relations(documents, predictions)
        official = official_primary(documents, predictions)
        agrees = all(abs(ours[key] - official[key]) <= 1e-12 for key in official)
        parity[name] = {"agrees": agrees, "adapter": {key: ours[key] for key in official}, "publisher": official}
        if not agrees:
            raise ValueError("primary_scorer_disagreement:" + name)
    good = score_relations(documents, native_gold)
    wrong_source = [{"title": "__wrong_source__", "h_idx": 0, "t_idx": 1, "r": "P17"}]
    invalid = score_relations(documents, native_gold + wrong_source + [{"title": documents[0]["title"], "h_idx": -1, "t_idx": 0, "r": "P17"}])
    if invalid["precision"] >= good["precision"] or invalid["fn"] != good["fn"]:
        raise ValueError("invalid_prediction_penalty_failed")
    audit = {"status": "pass", "scope": "primary_relation_P_R_F1_only_not_backend_quality",
             "source": "pinned_Re_DocRED_official_evaluate_unchanged_function_AST",
             "auxiliary_ignore_train_metrics": "not_certified_unused_inputs_empty_only_for_primary_parity",
             "cases": parity, "invalid_record_penalty": "pass", "task_exclusions": 0,
             "real_native_development_documents": len(documents), "final_labels_used": False}
    write_json(OUT / "reports/relation-scorer-audit-v1.json", audit)
    return audit


def main(run_dir=None):
    global RUN
    if run_dir is not None:
        RUN = Path(run_dir)
    documents = pilot_gold()
    audit = scorer_audit(documents)
    files = sorted((RUN / "responses").glob("*.json"))
    reused = RUN / "reused-responses.json"
    if reused.exists():
        for row in json.loads(reused.read_text(encoding="utf-8")):
            source = OUT / row["path"]
            if hashlib.sha256(source.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("reused_response_hash_changed")
            files.append(source)
    if not files:
        print(json.dumps({"scorer_audit": audit["status"], "pilot": "not_run"}))
        return
    completed, predictions, failures, raw_invalid = [], [], [], 0
    for path in files:
        row = json.loads(path.read_text(encoding="utf-8"))
        if row["state"] == "completed":
            completed.append(row["title"])
            predictions.extend(row["predictions"])
            for index in row.get("invalid_record_indices", []):
                candidate = row["candidate_relations"][index]
                predictions.append({"title": row["title"], **candidate} if isinstance(candidate, dict) else {"title": row["title"]})
                raw_invalid += 1
        else:
            failures.append({"id": row["id"], "error": row.get("error")})
    result = score_relations(documents, predictions, completed_titles=completed)
    if not raw_invalid:
        native = official_primary(documents, predictions)
        if any(abs(native[key] - result[key]) > 1e-12 for key in native):
            raise ValueError("live_result_primary_metric_disagreement")
    else:
        native = {"status": "not_comparable_invalid_records_penalized_by_wrapper"}
    result.update(status="inconclusive", scope="12_native_train_documents_pilot_not_final_acceptance",
                  publisher_primary=native, failures=failures, raw_invalid_records=raw_invalid,
                  task="given_entity_relation_native_ontology_custom_prompt",
                  scorer_audit="reports/relation-scorer-audit-v1.json")
    import numpy as np
    from framework.knowledge_graph.external_benchmark_budget import open_external_budget
    rng = np.random.default_rng(20261029)
    rows = result["by_document"]
    draws = rng.integers(0, len(rows), size=(2000, len(rows)))
    counts = np.array([[row["tp"], row["fp"], row["fn"]] for row in rows])
    totals = counts[draws].sum(axis=1)
    totals[:, 1] += result["fp"] - int(counts[:, 1].sum())
    p = np.divide(totals[:, 0], totals[:, 0]+totals[:, 1], out=np.zeros(2000), where=(totals[:, 0]+totals[:, 1]) > 0)
    r = np.divide(totals[:, 0], totals[:, 0]+totals[:, 2], out=np.zeros(2000), where=(totals[:, 0]+totals[:, 2]) > 0)
    f = np.divide(2*p*r, p+r, out=np.zeros(2000), where=(p+r)>0)
    result["document_bootstrap_95_interval"] = {key: np.quantile(values, [.025, .975]).tolist()
                                                for key, values in [("precision", p), ("recall", r), ("f1", f)]}
    result["bootstrap"] = {"seed": 20261029, "resamples": 2000, "unit": "document",
                           "warning": "12 development documents do not establish dataset-wide acceptance thresholds"}
    budget = open_external_budget(OUT).summary()
    result["budget"] = budget
    result["cost_projection"] = {"basis": "observed_12_development_documents_including_truncation",
                                  "tokens_for_500_documents_linear_estimate": budget["tokens_charged_or_reserved"] / 12 * 500,
                                  "not_a_budget_reservation": True}
    write_json(RUN / "score.json", result)
    print(json.dumps({key: result[key] for key in ("status", "precision", "recall", "f1", "completion_rate", "expected", "tp", "fp", "fn")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    main(parser.parse_args().run_dir)
