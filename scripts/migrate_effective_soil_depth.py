"""Backfill the canonical effective_soil_depth parcel indicator.

The historical importer stored YXTCHD (有效土层厚度) under the misleading
``topsoil_thickness`` key.  This migration is a dry run unless ``--apply`` is
provided and leaves the legacy key in place for older clients.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2


PROJECT_ROOT = Path(__file__).resolve().parent.parent


COUNT_SQL = """
    SELECT COUNT(*)
    FROM parcel_info
    WHERE NULLIF(soil_indicators->>'effective_soil_depth', '') IS NULL
      AND NULLIF(soil_indicators->>'topsoil_thickness', '') IS NOT NULL
"""

UPDATE_SQL = """
    UPDATE parcel_info
    SET soil_indicators = jsonb_set(
            COALESCE(soil_indicators::jsonb, '{}'::jsonb),
            '{effective_soil_depth}',
            soil_indicators::jsonb->'topsoil_thickness',
            TRUE
        ),
        updated_at = NOW()
    WHERE NULLIF(soil_indicators->>'effective_soil_depth', '') IS NULL
      AND NULLIF(soil_indicators->>'topsoil_thickness', '') IS NOT NULL
"""


def load_dotenv() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="执行回填；默认只统计")
    args = parser.parse_args()

    load_dotenv()
    connection = db_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(COUNT_SQL)
                candidates = int(cursor.fetchone()[0] or 0)
                print({"candidates": candidates, "mode": "apply" if args.apply else "dry-run"})
                if args.apply and candidates:
                    cursor.execute(UPDATE_SQL)
                    print({"updated": int(cursor.rowcount or 0)})
                elif not args.apply:
                    connection.rollback()
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
