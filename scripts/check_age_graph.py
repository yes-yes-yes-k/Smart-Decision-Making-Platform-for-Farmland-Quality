"""Fail-fast Apache AGE/PostgreSQL compatibility and active-release check."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.knowledge_graph.stores import AgeGraphStore, SqlAlchemyAgeExecutor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--graph-name", default="cultivated_land_kg")
    args = parser.parse_args()
    health = AgeGraphStore(
        SqlAlchemyAgeExecutor(create_engine(args.dsn)), graph_name=args.graph_name,
    ).health()
    print(json.dumps(health, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if health.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
