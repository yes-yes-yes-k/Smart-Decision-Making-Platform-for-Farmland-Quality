"""Evaluate the frozen 120-case holdout without invoking an external model."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph import assess_graph_claim, rank_graph_evidence
from framework.rag.kg_runtime import rewrite_query_for_retrieval


def evaluate(graph: dict, acceptance: dict, top_k: int = 5) -> dict:
    rows = []
    for item in acceptance["questions"]:
        query = rewrite_query_for_retrieval(item["question"], item.get("history"))
        ranked = rank_graph_evidence(graph, query, top_k=top_k)
        relation_ids = [row.get("relation_id") for row in ranked]
        status = item["expected_status"]
        if status == "supported":
            passed = item.get("expected_relation_id") in relation_ids
            actual = "relation_hit" if passed else "relation_miss"
        elif status == "unsupported":
            claim = assess_graph_claim(graph, query)
            passed = (
                claim.get("status") == "unsupported"
                and item.get("expected_relation_id") in relation_ids
            )
            actual = claim.get("status")
        elif status == "no_graph_match":
            passed = not ranked
            actual = "no_graph_match" if passed else "unexpected_graph_match"
        else:
            # Permission attacks are enforced by ACL-filtered Chroma resolution,
            # covered by integration tests. Here they must not match a relation.
            passed = not ranked
            actual = "no_graph_match" if passed else "unexpected_graph_match"
        rows.append({
            "id": item["id"], "stratum": item["stratum"], "passed": passed,
            "expected_status": status, "actual": actual,
            "rewritten_query": query, "relation_ids_at_k": relation_ids,
        })
    strata = {}
    for name in sorted({row["stratum"] for row in rows}):
        selected = [row for row in rows if row["stratum"] == name]
        strata[name] = {
            "count": len(selected),
            "passed": sum(row["passed"] for row in selected),
            "pass_rate": round(sum(row["passed"] for row in selected) / len(selected), 4),
        }
    return {
        "schema_version": "kg-production-acceptance-evaluation-v1",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "graph_schema_version": graph["schema_version"], "top_k": top_k,
        "summary": {
            "count": len(rows), "passed": sum(row["passed"] for row in rows),
            "pass_rate": round(sum(row["passed"] for row in rows) / len(rows), 4),
            "strata": strata,
        },
        "failures": [row for row in rows if not row["passed"]],
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json")
    parser.add_argument("--acceptance", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "production_acceptance_120_v0.4.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "production_acceptance_evaluation_v0.4.json")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.graph.read_text(encoding="utf-8")),
        json.loads(args.acceptance.read_text(encoding="utf-8")),
        top_k=args.top_k,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if result["summary"]["passed"] == result["summary"]["count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
