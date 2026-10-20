"""Query v0.3 entities, ranked evidence or a relation claim."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph import assess_graph_claim, query_graph, rank_graph_evidence


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="实体规范名称或别名，如 土壤pH、酸化、石灰")
    parser.add_argument(
        "--graph",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json",
    )
    parser.add_argument("--max-relations", type=int, default=20)
    parser.add_argument(
        "--mode", choices=("rank", "entity", "claim"), default="rank",
        help="rank=自然问句证据排序；entity=实体一跳关系；claim=判断关系是否获当前证据支持",
    )
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    if args.mode == "entity":
        result = query_graph(graph, args.query)
        result["relations"] = result["relations"][: args.max_relations]
    elif args.mode == "claim":
        result = assess_graph_claim(graph, args.query)
    else:
        result = {
            "query": args.query,
            "ranked_evidence": rank_graph_evidence(
                graph, args.query, top_k=args.max_relations,
            ),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    has_result = bool(
        result.get("entities")
        or result.get("ranked_evidence")
        or result.get("status") in {"supported", "unsupported"}
    )
    return 0 if has_result else 2


if __name__ == "__main__":
    raise SystemExit(main())
