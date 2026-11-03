"""Complete only the fixed nonfinal pilot's 104 independent semantic requests."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_kg_external_qa_pilot_v2 import RUN, OUT
from framework.knowledge_graph.external_benchmark_budget import open_external_budget
from scripts.score_kg_external_qa import run


def main(execute=False):
    state = json.loads((RUN/"run-state.json").read_text(encoding="utf-8"))
    if state["state"] != "completed" or open_external_budget(OUT).summary()["inflight"]:
        raise ValueError("QA_generation_must_be_terminal_and_no_active_requests")
    for dataset, partition, count in (("qasper", "development", 10), ("multihop_rag", "calibration", 16)):
        for arm in ("vector", "graphrag"):
            folder = RUN/dataset/arm
            predictions = folder/"predictions.jsonl"
            if len(predictions.read_text(encoding="utf-8").splitlines()) != count:
                raise ValueError("fixed_pilot_predictions_incomplete")
            command = [sys.executable, str(REPO/"scripts/judge_kg_external_qa.py"), "--dataset", dataset,
                       "--partition", partition, "--predictions", str(predictions), "--out-dir", str(folder/"semantic-v1")]
            if execute:
                command.append("--execute")
            print(json.dumps({"stage": "independent_semantic", "dataset": dataset, "arm": arm, "execute": execute}), flush=True)
            subprocess.run(command, cwd=REPO, check=True)
            if execute:
                run(dataset, partition, predictions, folder/"score.json", "live_backend_predictions",
                    folder/"semantic-v1/judgments.jsonl", RUN/"selection.json")
    if execute:
        for script in ("report_kg_external_qa_pilot_v2.py", "audit_kg_external_qa_evidence.py", "render_kg_external_qa_review.py"):
            subprocess.run([sys.executable, str(REPO/"scripts"/script)], cwd=REPO, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    main(parser.parse_args().execute)
