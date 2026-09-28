"""Build the administrative-region to parcel area cache used by statistics.

The cache contains only derived spatial relations and clipped areas. Indicator
values remain live because API reads join the cache back to ``parcel_info``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_REGION_TYPES = ("province", "city", "county", "township", "village")
VALID_REGION_TYPES = frozenset((*DEFAULT_REGION_TYPES, "zone"))


def ensure_schema(engine: sa.Engine) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "farmland_region_parcel_area",
        metadata,
        sa.Column("region_type", sa.String(16), primary_key=True),
        sa.Column("region_id", sa.String(64), primary_key=True),
        sa.Column("parcel_id", sa.String(64), primary_key=True),
        sa.Column("area_mu", sa.Float, nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Index("idx_farmland_region_parcel_area_parcel", "parcel_id"),
    )
    sa.Table(
        "farmland_region_precompute_state",
        metadata,
        sa.Column("region_type", sa.String(16), primary_key=True),
        sa.Column("region_id", sa.String(64), primary_key=True),
        sa.Column("region_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_parcel_count", sa.Integer, nullable=False),
        sa.Column("source_parcel_max_updated_at", sa.DateTime(timezone=True)),
        sa.Column("relation_count", sa.Integer, nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    metadata.create_all(engine, checkfirst=True)


def _region_type_clause(region_types: Sequence[str]) -> tuple[str, dict[str, str]]:
    unknown = sorted(set(region_types) - VALID_REGION_TYPES)
    if unknown:
        raise ValueError(f"unsupported region types: {', '.join(unknown)}")
    if not region_types:
        raise ValueError("at least one region type is required")
    params = {f"region_type_{index}": value for index, value in enumerate(region_types)}
    placeholders = ", ".join(f":{key}" for key in params)
    return placeholders, params


def rebuild_cache(
    engine: sa.Engine,
    region_types: Sequence[str] = DEFAULT_REGION_TYPES,
) -> dict[str, int | list[str]]:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("farmland spatial precomputation requires PostgreSQL/PostGIS")
    ensure_schema(engine)
    placeholders, params = _region_type_clause(tuple(dict.fromkeys(region_types)))

    with engine.begin() as connection:
        connection.execute(sa.text(
            "DROP TABLE IF EXISTS pg_temp.tmp_farmland_region_parcel_area"
        ))
        connection.execute(sa.text(f"""
            CREATE TEMP TABLE tmp_farmland_region_parcel_area ON COMMIT DROP AS
            WITH selected_regions AS MATERIALIZED (
                SELECT object_type AS region_type, object_id AS region_id, geom
                FROM spatial_region_catalog
                WHERE enabled = TRUE
                  AND geom IS NOT NULL
                  AND object_type IN ({placeholders})
            ),
            clipped AS MATERIALIZED (
                SELECT region.region_type, region.region_id, parcel.parcel_id,
                       CASE
                         WHEN ST_CoveredBy(parcel.geom, region.geom) THEN parcel.geom
                         ELSE ST_Intersection(parcel.geom, region.geom)
                       END AS clipped_geom
                FROM selected_regions AS region
                JOIN parcel_info AS parcel
                  ON parcel.geom IS NOT NULL
                 AND parcel.geom && region.geom
                 AND ST_Intersects(parcel.geom, region.geom)
            ),
            measured AS MATERIALIZED (
                SELECT region_type, region_id, parcel_id,
                       ST_Area(clipped_geom::geography) / 666.6666666666666 AS area_mu
                FROM clipped
                WHERE NOT ST_IsEmpty(clipped_geom)
            )
            SELECT region_type, region_id, parcel_id, area_mu
            FROM measured
            WHERE area_mu > 0
        """), params)
        connection.execute(sa.text(
            "CREATE UNIQUE INDEX ON tmp_farmland_region_parcel_area "
            "(region_type, region_id, parcel_id)"
        ))

        connection.execute(sa.text(f"""
            DELETE FROM farmland_region_parcel_area
            WHERE region_type IN ({placeholders})
        """), params)
        connection.execute(sa.text("""
            INSERT INTO farmland_region_parcel_area (
                region_type, region_id, parcel_id, area_mu, computed_at
            )
            SELECT region_type, region_id, parcel_id, area_mu, CURRENT_TIMESTAMP
            FROM tmp_farmland_region_parcel_area
        """))

        connection.execute(sa.text(f"""
            DELETE FROM farmland_region_precompute_state
            WHERE region_type IN ({placeholders})
        """), params)
        connection.execute(sa.text(f"""
            WITH parcel_source AS (
                SELECT COUNT(*)::integer AS parcel_count,
                       MAX(updated_at) AS parcel_max_updated_at
                FROM parcel_info
                WHERE geom IS NOT NULL
            )
            INSERT INTO farmland_region_precompute_state (
                region_type, region_id, region_updated_at,
                source_parcel_count, source_parcel_max_updated_at,
                relation_count, computed_at
            )
            SELECT region.object_type, region.object_id, region.updated_at,
                   source.parcel_count, source.parcel_max_updated_at,
                   COUNT(cached.parcel_id)::integer, CURRENT_TIMESTAMP
            FROM spatial_region_catalog AS region
            CROSS JOIN parcel_source AS source
            LEFT JOIN tmp_farmland_region_parcel_area AS cached
              ON cached.region_type = region.object_type
             AND cached.region_id = region.object_id
            WHERE region.enabled = TRUE
              AND region.geom IS NOT NULL
              AND region.object_type IN ({placeholders})
            GROUP BY region.object_type, region.object_id, region.updated_at,
                     source.parcel_count, source.parcel_max_updated_at
        """), params)

        connection.execute(sa.text("ANALYZE farmland_region_parcel_area"))
        connection.execute(sa.text("ANALYZE farmland_region_precompute_state"))

        summary = connection.execute(sa.text(f"""
            SELECT
                (SELECT COUNT(*) FROM farmland_region_precompute_state
                 WHERE region_type IN ({placeholders})) AS regions,
                (SELECT COUNT(*) FROM farmland_region_parcel_area
                 WHERE region_type IN ({placeholders})) AS relations
        """), params).mappings().one()

    return {
        "regionTypes": list(dict.fromkeys(region_types)),
        "regions": int(summary["regions"]),
        "relations": int(summary["relations"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--region-type",
        action="append",
        choices=sorted(VALID_REGION_TYPES),
        dest="region_types",
        help="Region type to rebuild; repeat as needed. Defaults to non-zone types.",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Create the cache tables without populating them.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass

    from framework.config import Config

    engine = sa.create_engine(Config.SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)
    ensure_schema(engine)
    result: dict[str, object] = {"schemaCreated": True}
    if not args.schema_only:
        result.update(rebuild_cache(engine, args.region_types or DEFAULT_REGION_TYPES))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
