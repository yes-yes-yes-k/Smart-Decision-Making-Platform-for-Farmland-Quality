"""Compare representative bounded queries between JSON and Apache AGE."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.knowledge_graph.contracts import GraphQuery
from framework.knowledge_graph.dual_read import compare_graph_stores
from framework.knowledge_graph.stores import (
    AgeGraphStore, JsonGraphStore, SqlAlchemyAgeExecutor,
)


DEFAULT_ENTITIES = (
    "obstacle:acidification", "measure:deep_loosening",
    "indicator:organic_matter", "standard:doc-4",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--graph-name", default="cultivated_land_kg")
    parser.add_argument(
        "--json-graph", type=Path,
        default=ROOT / "artifacts/minimal_kg/cultivated_land_minimal_graph_v0.4.json",
    )
    parser.add_argument("--entity-id", action="append", dest="entity_ids")
    parser.add_argument("--minimum-match-ratio", type=float, default=1.0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    json_store = JsonGraphStore(args.json_graph)
    age_store = AgeGraphStore(
        SqlAlchemyAgeExecutor(create_engine(args.dsn)), graph_name=args.graph_name,
    )
    queries = tuple(
        GraphQuery((entity_id,), max_hops=2, top_k=100, timeout_ms=1000)
        for entity_id in (args.entity_ids or DEFAULT_ENTITIES)
    )
    report = compare_graph_stores(
        json_store, age_store, queries,
        minimum_match_ratio=args.minimum_match_ratio,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
