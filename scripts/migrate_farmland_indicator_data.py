"""Normalize existing parcel indicator JSON for the grouped statistics API.

The migration only copies values already present under historical aliases.  It
never manufactures pollution measurements or risk conclusions.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


NORMALIZE_SQL = """
UPDATE {table_name}
SET soil_indicators = ((
    CASE
      WHEN soil_indicators::jsonb ? 'topsoil_thickness'
       AND NOT soil_indicators::jsonb ? 'effective_soil_depth'
      THEN jsonb_set(soil_indicators::jsonb, '{{effective_soil_depth}}', soil_indicators::jsonb->'topsoil_thickness')
      ELSE soil_indicators::jsonb
    END
) || (
    CASE
      WHEN soil_indicators::jsonb ? 'total_n'
       AND NOT soil_indicators::jsonb ? 'total_nitrogen'
      THEN jsonb_build_object('total_nitrogen', soil_indicators::jsonb->'total_n')
      ELSE '{{}}'::jsonb
    END
))::json
WHERE soil_indicators IS NOT NULL
  AND (
       (soil_indicators::jsonb ? 'topsoil_thickness' AND NOT soil_indicators::jsonb ? 'effective_soil_depth')
    OR (soil_indicators::jsonb ? 'total_n' AND NOT soil_indicators::jsonb ? 'total_nitrogen')
  )
"""


def migrate(connection, *, apply: bool) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        with connection.cursor() as cursor:
            for table_name in ("parcel_info", "parcel_history_snapshot"):
                cursor.execute(NORMALIZE_SQL.format(table_name=table_name))
                counts[table_name] = int(cursor.rowcount or 0)
        if apply:
            connection.commit()
        else:
            connection.rollback()
        return counts
    except Exception:
        connection.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="规范化耕地统计指标字段")
    parser.add_argument("--apply", action="store_true", help="实际写库；默认仅预览后回滚")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    args = parser.parse_args()
    if args.env_file.exists():
        load_dotenv(args.env_file, override=False)
    connection = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
    )
    try:
        counts = migrate(connection, apply=args.apply)
    finally:
        connection.close()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
