"""Canonicalize parcel management fields and remove legacy JSON duplicates.

``parcel_info.land_type``, ``fertilizer_type`` and ``target_ph`` are the only
authoritative locations for these values.  The migration promotes a legacy
JSON value only when the canonical column is empty, records genuine conflicts,
removes all three duplicate JSON keys, and installs a database CHECK constraint
that prevents them from being written back.

Usage::

    python scripts/migrate_canonical_parcel_management_fields.py          # audit only
    python scripts/migrate_canonical_parcel_management_fields.py --apply  # migrate atomically
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_NAME = "canonical_parcel_management_fields_v1"
CANONICAL_FIELDS = ("land_type", "fertilizer_type", "target_ph")


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _connect():
    _load_env()
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
    )


AUDIT_SQL = """
SELECT
    count(*) AS total,
    count(*) FILTER (
        WHERE soil_indicators::jsonb ?| ARRAY['land_type','fertilizer_type','target_ph']
    ) AS rows_with_duplicates,
    count(*) FILTER (
        WHERE land_type IS NULL
          AND NULLIF(btrim(soil_indicators->>'land_type'), '') IS NOT NULL
    ) AS land_type_promotable,
    count(*) FILTER (
        WHERE fertilizer_type IS NULL
          AND NULLIF(btrim(soil_indicators->>'fertilizer_type'), '') IS NOT NULL
    ) AS fertilizer_type_promotable,
    count(*) FILTER (
        WHERE target_ph IS NULL
          AND btrim(COALESCE(soil_indicators->>'target_ph', ''))
              ~ '^[+-]?[0-9]+([.][0-9]+)?$'
    ) AS target_ph_promotable
FROM parcel_info
"""


def audit(conn) -> dict[str, int]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(AUDIT_SQL)
        return dict(cur.fetchone())


def migrate(conn) -> dict[str, int]:
    target_expr = """
        CASE
          WHEN btrim(COALESCE(soil_indicators->>'target_ph', ''))
               ~ '^[+-]?[0-9]+([.][0-9]+)?$'
          THEN (soil_indicators->>'target_ph')::double precision
          ELSE NULL
        END
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute("LOCK TABLE parcel_info IN SHARE ROW EXCLUSIVE MODE")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS parcel_info_field_conflict_audit (
                    id BIGSERIAL PRIMARY KEY,
                    parcel_id VARCHAR(64) NOT NULL,
                    field_name VARCHAR(32) NOT NULL,
                    canonical_value TEXT,
                    legacy_json_value TEXT,
                    resolution VARCHAR(64) NOT NULL,
                    migration_name VARCHAR(96) NOT NULL,
                    resolved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uk_parcel_field_conflict_migration
                        UNIQUE (parcel_id, field_name, migration_name)
                )
            """)
            for field in ("land_type", "fertilizer_type"):
                cur.execute(f"""
                    INSERT INTO parcel_info_field_conflict_audit
                        (parcel_id, field_name, canonical_value, legacy_json_value,
                         resolution, migration_name)
                    SELECT parcel_id, %s, {field}, soil_indicators->>%s,
                           'canonical_column_won', %s
                    FROM parcel_info
                    WHERE soil_indicators::jsonb ? %s
                      AND NULLIF(btrim({field}), '') IS NOT NULL
                      AND {field} IS DISTINCT FROM soil_indicators->>%s
                    ON CONFLICT (parcel_id, field_name, migration_name) DO NOTHING
                """, (field, field, MIGRATION_NAME, field, field))
            cur.execute(f"""
                INSERT INTO parcel_info_field_conflict_audit
                    (parcel_id, field_name, canonical_value, legacy_json_value,
                     resolution, migration_name)
                SELECT parcel_id, 'target_ph', target_ph::text,
                       soil_indicators->>'target_ph',
                       CASE WHEN ({target_expr}) IS NULL
                            THEN 'invalid_legacy_removed'
                            ELSE 'canonical_column_won' END,
                       %s
                FROM parcel_info
                WHERE soil_indicators::jsonb ? 'target_ph'
                  AND (
                      target_ph IS NOT NULL
                      AND target_ph IS DISTINCT FROM ({target_expr})
                      OR target_ph IS NULL AND ({target_expr}) IS NULL
                  )
                ON CONFLICT (parcel_id, field_name, migration_name) DO NOTHING
            """, (MIGRATION_NAME,))

            cur.execute(f"""
                UPDATE parcel_info
                SET land_type = COALESCE(
                        NULLIF(btrim(land_type), ''),
                        NULLIF(btrim(soil_indicators->>'land_type'), '')
                    ),
                    fertilizer_type = COALESCE(
                        NULLIF(btrim(fertilizer_type), ''),
                        NULLIF(btrim(soil_indicators->>'fertilizer_type'), '')
                    ),
                    target_ph = COALESCE(target_ph, ({target_expr})),
                    soil_indicators = (
                        COALESCE(soil_indicators, '{{}}'::json)::jsonb
                        - 'land_type' - 'fertilizer_type' - 'target_ph'
                    )::json,
                    updated_at = CURRENT_TIMESTAMP
                WHERE soil_indicators::jsonb
                      ?| ARRAY['land_type','fertilizer_type','target_ph']
            """)
            migrated_rows = cur.rowcount

            cur.execute("""
                ALTER TABLE parcel_info
                DROP CONSTRAINT IF EXISTS ck_parcel_info_no_management_json_fields
            """)
            cur.execute("""
                ALTER TABLE parcel_info
                ADD CONSTRAINT ck_parcel_info_no_management_json_fields
                CHECK (
                    soil_indicators IS NULL OR NOT (
                        soil_indicators::jsonb
                        ?| ARRAY['land_type','fertilizer_type','target_ph']
                    )
                )
            """)
            cur.execute("""
                SELECT count(*)
                FROM parcel_info_field_conflict_audit
                WHERE migration_name = %s
            """, (MIGRATION_NAME,))
            conflict_rows = int(cur.fetchone()[0])

    result = audit(conn)
    result["migrated_rows"] = migrated_rows
    result["conflict_audit_rows"] = conflict_rows
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行原子迁移；缺省仅进行只读审计",
    )
    args = parser.parse_args()
    conn = _connect()
    try:
        before = audit(conn)
        print(json.dumps({"mode": "apply" if args.apply else "audit", "before": before},
                         ensure_ascii=False))
        if not args.apply:
            return
        after = migrate(conn)
        if after["rows_with_duplicates"] != 0:
            raise RuntimeError("迁移后仍存在重复管理字段，事务已回滚")
        print(json.dumps({"status": "ok", "after": after}, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
