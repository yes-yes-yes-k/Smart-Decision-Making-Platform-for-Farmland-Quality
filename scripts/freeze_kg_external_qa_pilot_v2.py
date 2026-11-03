"""Freeze faithful-source QA pilot, original responses, scorers and diagnostics."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_kg_external_qa_pilot_v2 import RUN, OUT, read, prepare
from scripts.prepare_kg_external_benchmarks import write_json
from framework.knowledge_graph.external_benchmark_budget import open_external_budget


def main():
    target = OUT/"reports/qa-pilot-result-manifest-v2.json"
    if target.exists():
        data = json.loads(target.read_text(encoding="utf-8"))
        for name, expected in data["files"].items():
            if hashlib.sha256((OUT/name).read_bytes()).hexdigest() != expected:
                raise ValueError("frozen_QA_v2_changed:" + name)
        print(json.dumps({"state": "already_frozen_unchanged", "files": len(data["files"])}))
        return
    prepare()  # Verify frozen selection, source and implementation dependencies.
    budget = open_external_budget(OUT).summary()
    state = json.loads((RUN/"run-state.json").read_text(encoding="utf-8"))
    if state["state"] != "completed" or budget["inflight"]:
        raise ValueError("QA_v2_not_terminal")
    for dataset, count in (("qasper", 10), ("multihop_rag", 16)):
        graph = json.loads((RUN/dataset/"graph-build.json").read_text(encoding="utf-8"))
        if graph["units"] != graph["completed"]:
            raise ValueError("QA_graph_units_incomplete")
        for arm in ("vector", "graphrag"):
            folder = RUN/dataset/arm
            predictions, judgments = read(folder/"predictions.jsonl"), read(folder/"semantic-v1/judgments.jsonl")
            if len(predictions) != count or len(judgments) != count or len({row["question_id"] for row in judgments}) != count:
                raise ValueError("QA_v2_prediction_or_semantic_count_mismatch")
            score = json.loads((folder/"score.json").read_text(encoding="utf-8"))
            if score["semantic_support"]["judged"] != count or score["semantic_support"]["status"] != "measured":
                raise ValueError("QA_v2_semantic_evidence_incomplete")
    scripts = ["run_kg_external_qa_pilot_v2", "prepare_kg_external_qa_pilot_v2", "complete_kg_external_qa_pilot_v2",
               "report_kg_external_qa_pilot_v2", "judge_kg_external_qa", "score_kg_external_qa",
               "audit_kg_external_qa_evidence", "audit_kg_external_qa_judge_stability", "render_kg_external_qa_review",
               "propose_kg_external_qa_acceptance", "freeze_kg_external_qa_pilot_v2"]
    modules = ["external_qa_metadata", "external_qa_retrieval", "external_qa_evaluation", "external_qasper_scoring",
               "external_benchmark_freeze", "external_benchmark_budget", "acceptance_budget"]
    names = ["scripts/"+name+".py" for name in scripts] + ["framework/knowledge_graph/"+name+".py" for name in modules]
    names += ["tests/"+name+".py" for name in ("test_external_qa_metadata", "test_external_qa_scoring", "test_external_qa_retrieval", "test_external_budget_scope")]
    for name in names:
        source, dest = REPO/name, RUN/"frozen-code"/name
        if dest.exists() and dest.read_bytes() != source.read_bytes():
            raise ValueError("QA_v2_frozen_code_collision")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
    reports = ["real-QA-pilot-v2.json", "QA-evidence-granularity-v2.json", "qa-threshold-proposal-v1.json",
               "qa-judge-repeat-stability-v1.json", "qa-scoring-chain-v3.json"]
    paths = [path for path in RUN.rglob("*") if path.is_file()] + [OUT/"reports"/name for name in reports]
    files = {str(path.relative_to(OUT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    write_json(target, {"status": "frozen_nonfinal_faithful_source_trial", "created_at": datetime.now(timezone.utc).isoformat(),
                       "files": files, "final_acceptance": False, "expert_certified": False,
                       "same_model_judge_bias": True, "reference_changes": 0, "budget_checkpoint": budget})
    print(json.dumps({"state": "frozen", "files": len(files), "reference_changes": 0}))


if __name__ == "__main__":
    main()
