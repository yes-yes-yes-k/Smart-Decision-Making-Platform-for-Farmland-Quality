"""Validate candidate-stage attribution and unchanged historical evidence offline."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.knowledge_graph.retrieval_diagnostics import signature, target_summary

BASE = ROOT/"artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1"
OUT = BASE.parent/"candidate-trace-20261030-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    target = OUT/"validation.json"
    if target.exists():
        raise ValueError("validation_exists_use_new_version")
    trace = json.loads((OUT/"candidate-trace.json").read_text(encoding="utf-8"))
    probe = json.loads((OUT/"miss-probes.json").read_text(encoding="utf-8"))
    require(len(trace["results"]) == 9 and trace["model_calls"] == probe["model_calls"] == 0, "Unexpected query/model count")
    require(trace["all_previous_top20_reproduced"] and trace["all_source_stages_verified"], "Replay or source stage mismatch")
    for case in trace["results"]:
        stages = case["stages"]
        # Independently reconstruct the existing RRF ranking from both legs.
        scores, order, seen_by_leg = {}, {}, {}
        for name in ("vector", "lexical"):
            seen_by_leg[name] = set()
            for rank, item in enumerate(stages[name], 1):
                key = (item["document_id"], item["content_sha256"], item["chunk_index"])
                if key in seen_by_leg[name]:
                    continue
                seen_by_leg[name].add(key)
                scores[key] = scores.get(key, 0)+1/(trace["fusion_k"]+rank)
                order.setdefault(key, item)
        expected = sorted(scores, key=lambda k: -scores[k])
        actual = [(i["document_id"], i["content_sha256"], i["chunk_index"]) for i in stages["fused_full"]]
        require(expected == actual, "RRF full ranking cannot be reconstructed")
        require(all(abs(scores[key]-item["rrf_score"]) < 1e-14 for key, item in zip(actual, stages["fused_full"])), "RRF score mismatch")
        require(stages["fused_top60"] == stages["fused_full"][:60], "Fusion cutoff changed")
        require([signature(i) for i in stages["returned"]] == [signature(i) for i in stages["after_source_checks"][:20]], "Return cutoff not reconstructed")
        require(all(a.get("rrf_score") == b.get("rrf_score") and a.get("retrieval_ranks") == b.get("retrieval_ranks")
                    for a, b in zip(stages["returned"], stages["after_source_checks"])), "Returned ranking provenance changed")
        local = [item for values in case["vector_collections"].values() for item in values]
        merged = sorted(local, key=lambda item: item["distance"])[:60]
        require([signature(i) for i in merged] == [signature(i) for i in stages["vector"]], "Global vector merge mismatch")
        for item in case["targets"]:
            expected_summary = target_summary(item["document_id"], stages, source_checks_verified=True)
            require(all(item[k] == v for k, v in expected_summary.items()), "Target summary mismatch")
            inventory = item["inventory"]
            live = inventory["current_source"]
            require(inventory["indexed_chunks"] == inventory["public_academic_chunks"] > 0, "Target not in eligible index snapshot")
            require(live["completed"] and live["source_bytes_valid"] and live["review_status"] == "approved" and live["visibility_scope"] == "public", "Target current qualification unresolved")
    expected_stages = {"U1": (None, None, None), "U2": (None, None, None), "U3": (15, None, 35),
                       "U4": (None, None, None), "U5": (1, 1, 1)}
    for case in trace["results"][:5]:
        best = case["targets"][0]["stages"]
        require(tuple(best[name]["best_chunk_rank"] for name in ("vector", "lexical", "fused_full")) == expected_stages[case["case_id"]], "Primary findings changed")
    for row in probe["results"][:4]:
        require(not row["query_terms_found_in_target_stored_terms"], "Stored-term overlap finding changed")
    previous_manifest = json.loads((BASE/"manifest.json").read_text(encoding="utf-8"))
    for relative, digest in previous_manifest["files"].items():
        require(hashlib.sha256((BASE/relative).read_bytes()).hexdigest() == digest, "Frozen R1/R2 artifact changed:"+relative)
    command = [sys.executable, "-m", "unittest", "tests.test_retrieval_candidate_diagnostics"]
    tested = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (OUT/"tests.log").write_text(tested.stdout, encoding="utf-8")
    require(tested.returncode == 0, "Diagnostic fault tests failed")
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "state": "passed", "replayed_queries": 9,
              "RRF_ranking_rebuilt": True, "source_filter_and_cutoff_rebuilt": True, "previous_top20_reproduced": True,
              "frozen_R1_R2_files_unchanged": len(previous_manifest["files"]), "diagnostic_tests_passed": 7,
              "model_calls": 0, "ranking_or_filters_changed": False, "test_command": " ".join(command)}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
