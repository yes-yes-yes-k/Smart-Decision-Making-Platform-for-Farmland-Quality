"""Backfill per-indicator provenance in parcel_info.soil_indicators.

The migration is a dry run unless ``--apply`` is supplied. Existing
per-indicator provenance wins; only missing entries are added.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_batch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from framework.domain.statistics import PROVENANCE_FIELD, build_source_provenance


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
    parser.add_argument("--measurement-year", type=int, default=2024)
    args = parser.parse_args()

    load_dotenv()
    connection = db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT parcel_id, soil_indicators FROM parcel_info ORDER BY id")
            updates = []
            added_entries = 0
            for parcel_id, raw_indicators in cursor.fetchall():
                indicators = raw_indicators if isinstance(raw_indicators, dict) else {}
                existing = indicators.get(PROVENANCE_FIELD)
                provenance = dict(existing) if isinstance(existing, dict) else {}
                expected = build_source_provenance(indicators, args.measurement_year)
                missing = {key: value for key, value in expected.items() if key not in provenance}
                if not missing:
                    continue
                provenance.update(missing)
                updates.append((json.dumps(provenance, ensure_ascii=False), parcel_id))
                added_entries += len(missing)

            print({
                "candidates": len(updates),
                "provenanceEntries": added_entries,
                "measurementYear": args.measurement_year,
                "mode": "apply" if args.apply else "dry-run",
            })
            if args.apply and updates:
                execute_batch(cursor, """
                    UPDATE parcel_info
                    SET soil_indicators = jsonb_set(
                            COALESCE(soil_indicators::jsonb, '{}'::jsonb),
                            '{indicator_provenance}',
                            %s::jsonb,
                            TRUE
                        ),
                        updated_at = NOW()
                    WHERE parcel_id = %s
                """, updates, page_size=500)
                connection.commit()
                print({"updated": len(updates), "provenanceEntriesAdded": added_entries})
            else:
                connection.rollback()
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
