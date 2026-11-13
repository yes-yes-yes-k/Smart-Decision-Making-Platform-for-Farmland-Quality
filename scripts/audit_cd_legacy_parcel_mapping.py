"""Read-only point-in-parcel pilot. Outputs audit evidence, never writes mappings."""
import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor


REGION_SQL = """
SELECT object_id, display_name, source, updated_at, ST_SRID(geom) AS srid,
       ST_IsValid(geom) AS valid, ST_IsEmpty(geom) AS empty,
       md5(encode(ST_AsEWKB(geom), 'hex')) AS geometry_fingerprint
FROM spatial_region_catalog
WHERE object_type = 'township' AND object_id = %(township)s AND enabled
"""

MATCH_SQL = """
WITH region AS (
    SELECT geom FROM spatial_region_catalog
    WHERE object_type = 'township' AND object_id = %(township)s AND enabled
), old_points AS (
    SELECT mapping.parcel_id AS legacy_id, mapping.distance_m AS township_distance_m,
           CASE WHEN p.centroid_lon BETWEEN -180 AND 180
                  AND p.centroid_lat BETWEEN -90 AND 90
                THEN ST_SetSRID(ST_MakePoint(p.centroid_lon, p.centroid_lat), 4326)
           END AS point
    FROM cd_ported_parcel_township mapping
    LEFT JOIN parcel_info p ON p.parcel_id = mapping.parcel_id
    WHERE mapping.township_id = %(township)s
), point_extent AS (
    SELECT ST_SetSRID(ST_Extent(point)::geometry, 4326) AS extent FROM old_points
), native_parcels AS MATERIALIZED (
    SELECT parcel_id, geom
    FROM parcel_info CROSS JOIN point_extent
    WHERE left(parcel_id, 4) <> 'SGD_'
      AND geom && extent
      AND geom IS NOT NULL AND ST_SRID(geom) = 4326
      AND NOT ST_IsEmpty(geom) AND ST_IsValid(geom)
)
SELECT old.legacy_id, old.township_distance_m,
       old.point IS NOT NULL AS coordinate_valid,
       ST_Covers(region.geom, old.point) AS in_township,
       hits.parcel_ids, hits.interior_hits
FROM old_points old
CROSS JOIN region
CROSS JOIN LATERAL (
    SELECT array_agg(parcel.parcel_id ORDER BY parcel.parcel_id) AS parcel_ids,
           count(*) FILTER (WHERE ST_Contains(parcel.geom, old.point)) AS interior_hits
    FROM native_parcels parcel
    WHERE parcel.geom && old.point AND ST_Covers(parcel.geom, old.point)
) hits
ORDER BY old.legacy_id
"""


def classification(row):
    if not row["coordinate_valid"]:
        return "invalid_coordinate"
    count = len(row["parcel_ids"] or [])
    if count == 0:
        return "unmatched"
    if count > 1:
        return "multiple"
    return "unique_interior" if row["interior_hits"] else "unique_boundary"


def audit(connection, township):
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SHOW transaction_read_only")
        if cursor.fetchone()["transaction_read_only"] != "on":
            raise RuntimeError("A read-only transaction is required")
        params = {"township": township}
        cursor.execute(REGION_SQL, params)
        regions = cursor.fetchall()
        if len(regions) != 1 or regions[0]["srid"] != 4326 or not regions[0]["valid"] or regions[0]["empty"]:
            raise ValueError("Expected one valid, nonempty EPSG:4326 township boundary")
        cursor.execute("""
            SELECT ST_SRID(geom) AS srid, GeometryType(geom) AS geometry_type,
                   count(*) AS records,
                   count(*) FILTER (WHERE geom IS NULL OR ST_IsEmpty(geom) OR NOT ST_IsValid(geom)) AS unusable
            FROM parcel_info
            WHERE left(parcel_id, 4) <> 'SGD_'
            GROUP BY 1, 2 ORDER BY 1, 2
        """)
        geometry_inventory = cursor.fetchall()
        cursor.execute("""
            SELECT count(DISTINCT parcel_id) AS parcels
            FROM farmland_region_parcel_area
            WHERE region_type = 'township' AND region_id = %(township)s
        """, params)
        area_mapping_parcels = cursor.fetchone()["parcels"]
        cursor.execute(MATCH_SQL, params)
        rows = [dict(row) for row in cursor.fetchall()]

    counts = Counter()
    in_township_counts = Counter()
    candidate_parcels = set()
    for row in rows:
        status = classification(row)
        row["status"] = status
        counts[status] += 1
        if row["in_township"]:
            in_township_counts[status] += 1
        candidate_parcels.update(row["parcel_ids"] or [])
    return {
        "region": dict(regions[0]),
        "current_geometry_inventory": [dict(row) for row in geometry_inventory],
        "current_area_mapping_parcels": area_mapping_parcels,
        "legacy_points": len(rows),
        "legacy_points_in_township": sum(in_township_counts.values()),
        "legacy_points_outside_township": sum(row["in_township"] is False for row in rows),
        "positive_township_assignment_distance": sum((row["township_distance_m"] or 0) > 0 for row in rows),
        "match_counts": dict(counts),
        "match_counts_inside_township": dict(in_township_counts),
        "distinct_current_candidates": len(candidate_parcels),
    }, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--township", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load_dotenv(args.env_file)
    connection = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USER", "postgres"), password=os.getenv("DB_PASSWORD"),
        dbname=args.database, connect_timeout=10,
        options="-c default_transaction_read_only=on -c statement_timeout=60000",
    )
    try:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        report, rows = audit(connection, args.township)
    finally:
        connection.rollback()
        connection.close()
    report.update(database=args.database, read_only=True, audited_at=datetime.now(timezone.utc).isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with args.output.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as file:
        fields = ["legacy_id", "status", "coordinate_valid", "in_township", "township_distance_m",
                  "interior_hits", "parcel_ids"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "parcel_ids": "|".join(row["parcel_ids"] or [])})
    print(json.dumps(report, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
