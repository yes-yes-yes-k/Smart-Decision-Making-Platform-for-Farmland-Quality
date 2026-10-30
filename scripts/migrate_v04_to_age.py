"""Idempotently migrate the reviewed v0.4 JSON graph into Apache AGE."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.knowledge_graph.age_migration import migrate_reviewed_graph
from framework.knowledge_graph.stores import AgeGraphStore, SqlAlchemyAgeExecutor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True, help="PostgreSQL SQLAlchemy DSN")
    parser.add_argument(
        "--graph", type=Path,
        default=ROOT / "artifacts/minimal_kg/cultivated_land_minimal_graph_v0.4.json",
    )
    parser.add_argument("--graph-name", default="cultivated_land_kg")
    parser.add_argument("--release-id", default="kg-v0.4-production-candidate-1")
    parser.add_argument("--release-sequence", type=int, default=1)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--audit-output", type=Path)
    args = parser.parse_args()

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    engine = create_engine(args.dsn)
    store = AgeGraphStore(SqlAlchemyAgeExecutor(engine), graph_name=args.graph_name)
    report = migrate_reviewed_graph(
        graph, store, release_id=args.release_id,
        release_sequence=args.release_sequence, activate=args.activate,
    )
    if args.audit_output:
        args.audit_output.parent.mkdir(parents=True, exist_ok=True)
        args.audit_output.write_text(
            json.dumps(store.export_snapshot(args.release_id), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8", newline="\n",
        )
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
