"""Measure bounded AGE query and explicit release switch/rollback SLOs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph.capacity_benchmark import (
    benchmark_age_queries, benchmark_release_switch,
)
from framework.knowledge_graph.stores import AgeGraphStore, SqlAlchemyAgeExecutor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--graph-name", default="cultivated_land_kg_capacity")
    parser.add_argument("--entity-id", action="append", dest="entity_ids", required=True)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--target-release", required=True)
    parser.add_argument("--rollback-release", required=True)
    parser.add_argument("--apply-release-switch", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.apply_release_switch:
        parser.error("--apply-release-switch is required for activation/rollback measurement")
    store = AgeGraphStore(
        SqlAlchemyAgeExecutor(create_engine(args.dsn)), graph_name=args.graph_name,
    )
    report = {
        "schema": "knowledge-platform-age-runtime-benchmark-v1",
        "status": "completed",
        "query": benchmark_age_queries(store, args.entity_ids, rounds=args.rounds),
        "release": benchmark_release_switch(
            store, target_release=args.target_release,
            rollback_release=args.rollback_release,
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
