"""Stream one generated synthetic capacity dataset into Apache AGE."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph.capacity_loader import load_synthetic_dataset
from framework.knowledge_graph.stores import AgeGraphStore, SqlAlchemyAgeExecutor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--graph-name", default="cultivated_land_kg_capacity")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--release-sequence", type=int, required=True)
    parser.add_argument("--rollback-release-id")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    store = AgeGraphStore(
        SqlAlchemyAgeExecutor(create_engine(args.dsn)), graph_name=args.graph_name,
    )
    report = load_synthetic_dataset(
        args.dataset, store, release_id=args.release_id,
        release_sequence=args.release_sequence, activate=args.activate,
        rollback_release_id=args.rollback_release_id,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
