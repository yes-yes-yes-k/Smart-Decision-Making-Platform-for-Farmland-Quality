"""Compare repeated reference judges with verified identical model packets."""
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_kg_external_qa_pilot_v2 import RUN, OUT, read
from scripts.judge_kg_external_qa import prepare
from scripts.prepare_kg_external_benchmarks import write_json


def main():
    from framework.knowledge_graph.external_benchmark_freeze import require_mutable
    require_mutable(OUT, OUT/"reports/qa-judge-repeat-stability-v1.json")
    report = {"status": "inconclusive", "same_model_and_prompt": True, "expert_certified": False,
              "error_correlation_not_identifiable_without_independent_truth": True,
              "reference_repeat_agreement_not_annotation_truth": True, "model_calls": 0, "datasets": {}}
    with TemporaryDirectory() as temporary:
        for dataset, partition in (("qasper", "development"), ("multihop_rag", "calibration")):
            packets, judgments = {}, {}
            for arm in ("vector", "graphrag"):
                folder = RUN/dataset/arm
                jobs, _ = prepare(dataset, partition, folder/"predictions.jsonl", Path(temporary)/dataset/arm)
                packets[arm] = {job["question_id"]: hashlib.sha256(json.dumps(job["options"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                                for job in jobs if job["kind"] == "reference"}
                judgments[arm] = {row["question_id"]: row["judgment"] for row in read(folder/"semantic-v1/judgments.jsonl")}
            if packets["vector"] != packets["graphrag"]:
                raise ValueError("reference_repeat_packets_differ")
            differences = [{"question_id": identifier, "reference_request_sha256": fingerprint,
                            "vector_reference_judgment": judgments["vector"][identifier]["reference_support"],
                            "graphrag_reference_judgment": judgments["graphrag"][identifier]["reference_support"]}
                           for identifier, fingerprint in packets["vector"].items()
                           if judgments["vector"][identifier]["reference_support"] != judgments["graphrag"][identifier]["reference_support"]]
            report["datasets"][dataset] = {"paired_reference_requests": len(packets["vector"]), "disagreements": differences,
                                           "agreement": 1-len(differences)/len(packets["vector"]),
                                           "reference_request_hashes": packets["vector"],
                                           "repeated_requests_receive_same_reference_and_source_packet": True}
    write_json(OUT/"reports/qa-judge-repeat-stability-v1.json", report)
    print(json.dumps({name: {"paired": value["paired_reference_requests"], "disagreements": len(value["disagreements"])} for name, value in report["datasets"].items()}))


if __name__ == "__main__":
    main()
