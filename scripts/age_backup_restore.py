"""Create or restore a whole-database PostgreSQL/AGE backup with graph checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.knowledge_graph.backup import (
    create_postgres_age_backup, restore_postgres_age_backup,
)
from framework.knowledge_graph.stores import AgeGraphStore, SqlAlchemyAgeExecutor


def _store(dsn: str, graph_name: str) -> AgeGraphStore:
    return AgeGraphStore(
        SqlAlchemyAgeExecutor(create_engine(dsn)), graph_name=graph_name,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup")
    backup.add_argument("--dsn", required=True)
    backup.add_argument("--database-name", required=True)
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--graph-name", default="cultivated_land_kg")
    backup.add_argument("--pg-dump", default="pg_dump")
    backup.add_argument("--pg-restore", default="pg_restore")
    restore = subparsers.add_parser("restore")
    restore.add_argument("--dsn", required=True)
    restore.add_argument("--dump", type=Path, required=True)
    restore.add_argument("--manifest", type=Path, required=True)
    restore.add_argument("--graph-name", default="cultivated_land_kg")
    restore.add_argument("--pg-restore", default="pg_restore")
    restore.add_argument("--apply", action="store_true")
    restore.add_argument("--repair-age-catalog", action="store_true", help="Repair restored AGE catalog OIDs before verification")
    restore.add_argument("--report", type=Path)
    args = parser.parse_args()

    if args.command == "backup":
        report = create_postgres_age_backup(
            dsn=args.dsn, output_path=args.output,
            database_name=args.database_name,
            store=_store(args.dsn, args.graph_name),
            pg_dump=args.pg_dump, pg_restore=args.pg_restore,
        )
    else:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = restore_postgres_age_backup(
            dsn=args.dsn, dump_path=args.dump, manifest=manifest,
            restored_store=_store(args.dsn, args.graph_name),
            apply=args.apply, pg_restore=args.pg_restore,
            repair_catalog_oids=args.repair_age_catalog,
        )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if getattr(args, "report", None):
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
