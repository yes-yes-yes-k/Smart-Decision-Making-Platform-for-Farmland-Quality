"""Evaluate v0.4 standard-indicator role semantics without external models."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph import assess_graph_claim, rank_graph_evidence  # noqa: E402


def evaluate(graph: dict, acceptance: dict) -> dict:
    details = []
    for item in acceptance["questions"]:
        if item["expected_status"] == "supported":
            ranked = rank_graph_evidence(graph, item["question"], top_k=5)
            ids = [row["relation_id"] for row in ranked]
            rank = ids.index(item["expected_relation_id"]) + 1 if item["expected_relation_id"] in ids else None
            passed = rank == 1
            details.append({
                "id": item["id"], "category": item["category"],
                "question": item["question"], "expected_status": "supported",
                "expected_relation_id": item["expected_relation_id"],
                "expected_relation_type": item["expected_relation_type"],
                "rank": rank, "passed": passed,
                "top_relation_id": ids[0] if ids else None,
                "top_relation_type": ranked[0]["relation_type"] if ranked else None,
            })
            continue
        claim = assess_graph_claim(graph, item["question"])
        passed = (
            claim.get("status") == "unsupported"
            and claim.get("relation_type") == item["expected_relation_type"]
            and claim.get("source_entity_id") == item["expected_source_entity"]["id"]
            and claim.get("target_entity_id") == item["expected_target_entity"]["id"]
        )
        details.append({
            "id": item["id"], "category": item["category"],
            "question": item["question"], "expected_status": "unsupported",
            "expected_relation_type": item["expected_relation_type"],
            "actual_status": claim.get("status"),
            "actual_relation_type": claim.get("relation_type"),
            "passed": passed,
        })

    supported = [item for item in details if item["expected_status"] == "supported"]
    counterfactual = [item for item in details if item["expected_status"] == "unsupported"]
    return {
        "schema_version": "kg-v0.4-role-semantics-evaluation-v0.1",
        "generated_at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(),
        "summary": {
            "question_count": len(details),
            "passed_count": sum(item["passed"] for item in details),
            "supported_top1": sum(item["passed"] for item in supported),
            "supported_count": len(supported),
            "counterfactual_strict_hits": sum(item["passed"] for item in counterfactual),
            "counterfactual_count": len(counterfactual),
        },
        "details": details,
    }


def markdown(result: dict) -> str:
    summary = result["summary"]
    lines = [
        "# 知识图谱 v0.4 关系语义细化评估",
        "",
        f"- 执行时间：{result['generated_at']}",
        f"- 总题数：{summary['question_count']}",
        f"- 总通过：{summary['passed_count']}/{summary['question_count']}",
        f"- 支持类严格 Top 1：{summary['supported_top1']}/{summary['supported_count']}",
        f"- 反事实严格识别：{summary['counterfactual_strict_hits']}/{summary['counterfactual_count']}",
        "",
        "| ID | 类别 | 预期 | 结果 | 问题 |",
        "|---|---|---|---:|---|",
    ]
    for item in result["details"]:
        outcome = f"Top {item['rank']}" if item["expected_status"] == "supported" else item.get("actual_status")
        lines.append(
            f"| {item['id']} | {item['category']} | {item['expected_status']} | "
            f"{'通过' if item['passed'] else '失败'}（{outcome}） | {item['question']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json")
    parser.add_argument("--acceptance", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "role_semantics_acceptance_v0.4.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "role_semantics_evaluation_v0.4.json")
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "role_semantics_evaluation_v0.4.md")
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.graph.read_text(encoding="utf-8")),
        json.loads(args.acceptance.read_text(encoding="utf-8")),
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    args.report.write_text(markdown(result), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0 if result["summary"]["passed_count"] == result["summary"]["question_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
