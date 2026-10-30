"""Independent offline reconstruction of bounded pilot rankings and manifests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.knowledge_graph.retrieval_diagnostics import signature, pointer


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if Path(args.run_id).name != args.run_id or args.run_id in {".", ".."}:
        raise ValueError("invalid_run_id")
    base = ROOT/"artifacts/knowledge_platform/retrieval-quality-r1"
    run = base/args.run_id
    destination = run/"validation.json"
    if destination.exists():
        raise ValueError("validation_already_exists")
    manifest = read(run/"manifest.json")
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((run/name).read_bytes()).hexdigest() == expected, name
    for name, expected in manifest["code_sha256"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, name
    historical = base/"r1-r2-20261030-v1"
    frozen = read(historical/"manifest.json")["files"]
    for name, expected in frozen.items():
        assert hashlib.sha256((historical/name).read_bytes()).hexdigest() == expected, name
    report = read(run/"candidate-recall-results.json")
    assert report["model_calls"] == report["new_query_vectors"] == 0
    assert not report["target_labels_used_in_retrieval"] and not report["semantic_support_evaluated"]
    assert len(report["results"]) == 9 and report["all_frozen_top20_reproduced"]
    summary = []
    for row in report["results"]:
        for profile in ("baseline", "concepts"):
            data = row[profile]
            assert data["HTTP_status"] == 200
            stages, response = data["stages"], data["response"]
            scores, order = {}, {}
            for leg in ("vector", "lexical"):
                assert len(stages[leg]) <= 60
                seen = set()
                for rank, item in enumerate(stages[leg], 1):
                    key = signature(item)[:3]
                    if key in seen:
                        continue
                    seen.add(key)
                    scores[key] = scores.get(key, 0)+1/(60+rank)
                    order.setdefault(key, item)
            expected = sorted(scores, key=lambda key: -scores[key])
            assert expected == [signature(item)[:3] for item in stages["fused_full"]]
            fused = stages["fused_full"][:60]
            positions = {signature(item)[:3]: rank for rank, item in enumerate(fused, 1)}
            returned = [signature(pointer(item))[:3] for item in response["sources"]]
            assert returned == sorted(returned, key=positions.__getitem__)
            assert len(returned) <= 20 and not response["generation_performed"]
            assert not response["conditions_structurally_evaluated"]
            ids = [item["document_id"] for item in response["documents"]]
            assert len(ids) == len(set(ids))
            for doc in response["documents"]:
                assert doc["support_verified"] is False
                for evidence in doc["evidence_candidates"]:
                    assert (doc["document_id"], doc["content_sha256"], evidence["chunk_index"]) in positions
            expansion = response["retrieval"]["lexical"].get("expansion")
            if expansion:
                assert expansion["original_limit"]+expansion["expanded_limit"] == 60
                assert expansion["query_vector_unchanged"]
        for arm in row["fusion_only_ablations"]:
            assert arm["current_source_revalidated"] and len(arm["fused_top60"]) <= 60
            assert arm["returned"] == arm["after_source_checks"][:20]
            assert arm["vector_limit"]+arm["lexical_limit"] <= 120
        summary.append({"case_id": row["case_id"], "targets": row["target_ranks"]})
    primary = report["results"][:5]
    top10 = all(ranks["documents"] and ranks["documents"][0] <= 10 for row in primary for ranks in row["target_ranks"]["concepts"].values())
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "state": "passed_structural_validation",
              "queries": 9, "HTTP_arms": 18, "fusion_ablation_arms": 45, "frozen_files_unchanged": len(frozen),
              "primary_document_top10_passed": top10, "semantic_support_evaluated": False,
              "model_calls": 0, "target_ranks": summary}
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "target_ranks"}))


if __name__ == "__main__":
    main()
