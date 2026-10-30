"""Explicit M1 pilot migration. Never selects the production database."""
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sqlalchemy as sa
from framework.knowledge_graph.research_store import migrate, rollback_empty


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--rollback-empty", action="store_true")
    args = parser.parse_args()
    allowed = (REPO/"artifacts/knowledge_platform/evidence-m1-v1/runtime").resolve()
    path = args.database.resolve()
    if allowed not in path.parents or path.suffix != ".sqlite3":
        raise ValueError("M1_cli_only_allows_explicit_isolated_runtime_database")
    if not path.exists() and not args.apply:
        print(json.dumps({"database_exists": False, "applied": False, "requires_explicit_apply": True}))
        return
    if args.apply:
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = sa.create_engine(sa.URL.create("sqlite", database=str(path)))
    try:
        if args.rollback_empty:
            rollback_empty(engine); report = {"rolled_back": True}
        else:
            report = migrate(engine, apply=args.apply)
        print(json.dumps(report))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
