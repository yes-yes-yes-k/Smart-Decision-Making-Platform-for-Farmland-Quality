"""Audit and correct parcel county codes from spatial overlap.

Default mode is read-only. With ``--apply``, only parcels whose dominant county
contains at least 95% of their area are updated. Every inspected parcel is
recorded in an audit run, which can later be reverted with ``--rollback-run``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import psycopg2
from psycopg2.extras import Json, execute_values
from shapely import wkb


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_COUNTY_FILE = Path(
    r"F:\BaiduNetdiskDownload\耕地质量大模型\土壤所数据\广东GIS\Guangdong_L2_FXZQ.shp"
)


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


def boundary_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    for suffix in (".shp", ".shx", ".dbf", ".prj"):
        sidecar = path.with_suffix(suffix)
        if sidecar.exists():
            digest.update(sidecar.name.encode("utf-8"))
            with sidecar.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
    return digest.hexdigest()


def read_counties(path: Path) -> gpd.GeoDataFrame:
    counties = gpd.read_file(path)
    epsg = counties.crs.to_epsg() if counties.crs else None
    if epsg != 4490:
        raise RuntimeError(f"县级边界应为 EPSG:4490，实际为 {counties.crs}")
    required = {"FXZQDM", "FXZQMC", "geometry"}
    if missing := required.difference(counties.columns):
        raise RuntimeError(f"县级边界缺少字段: {sorted(missing)}")
    counties = counties.loc[counties.geometry.notna() & ~counties.geometry.is_empty].copy()
    if not counties.geometry.is_valid.all():
        counties.geometry = counties.geometry.make_valid()
    counties["FXZQDM"] = counties["FXZQDM"].astype(str)
    counties["FXZQMC"] = counties["FXZQMC"].astype(str)
    counties = counties.dissolve(by="FXZQDM", aggfunc={"FXZQMC": "first"}).reset_index()
    return counties.to_crs(6933)


def read_parcels(connection) -> gpd.GeoDataFrame:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT parcel_id, area_code, ST_AsBinary(geom)
            FROM parcel_info
            WHERE geom IS NOT NULL
            ORDER BY parcel_id
        """)
        rows = cursor.fetchall()
    return gpd.GeoDataFrame(
        {
            "parcel_id": [str(row[0]) for row in rows],
            "area_code": [row[1] for row in rows],
        },
        geometry=[wkb.loads(bytes(row[2])) for row in rows],
        crs=4326,
    ).to_crs(6933)


def infer_assignments(
    parcels: gpd.GeoDataFrame,
    counties: gpd.GeoDataFrame,
    minimum_overlap: float,
) -> list[dict[str, Any]]:
    spatial_index = counties.sindex
    assignments: list[dict[str, Any]] = []
    for _, parcel in parcels.iterrows():
        geometry = parcel.geometry
        parcel_area = float(geometry.area)
        candidates = list(spatial_index.query(geometry, predicate="intersects"))
        overlaps = []
        for index in candidates:
            county = counties.iloc[index]
            overlap_area = float(geometry.intersection(county.geometry).area)
            if overlap_area <= 0:
                continue
            overlaps.append({
                "areaCode": str(county["FXZQDM"]),
                "name": str(county["FXZQMC"]),
                "ratio": overlap_area / parcel_area if parcel_area > 0 else 0.0,
            })
        overlaps.sort(key=lambda item: (-item["ratio"], item["areaCode"]))
        dominant = overlaps[0] if overlaps else None

        point_codes = []
        point = geometry.centroid
        for index in spatial_index.query(point, predicate="intersects"):
            county = counties.iloc[index]
            if county.geometry.covers(point):
                point_codes.append(str(county["FXZQDM"]))
        point_code = sorted(set(point_codes))[0] if point_codes else None
        inferred = dominant["areaCode"] if dominant else None
        ratio = dominant["ratio"] if dominant else 0.0
        original = parcel["area_code"]
        if inferred is not None and ratio >= minimum_overlap:
            decision = "confirmed" if original == inferred else "applied"
        else:
            decision = "review_required"
        assignments.append({
            "parcel_id": parcel["parcel_id"],
            "original_area_code": original,
            "inferred_area_code": inferred,
            "point_area_code": point_code,
            "overlap_ratio": ratio,
            "intersections": overlaps,
            "decision": decision,
        })
    return assignments


def ensure_audit_table(cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parcel_region_assignment_audit (
            run_id VARCHAR(36) NOT NULL,
            parcel_id VARCHAR(64) NOT NULL,
            original_area_code VARCHAR(32),
            inferred_area_code VARCHAR(32),
            point_area_code VARCHAR(32),
            overlap_ratio DOUBLE PRECISION NOT NULL,
            intersected_counties JSONB NOT NULL,
            decision VARCHAR(24) NOT NULL,
            boundary_source VARCHAR(160) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (run_id, parcel_id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_parcel_region_assignment_audit_parcel
        ON parcel_region_assignment_audit (parcel_id, created_at)
    """)


def apply_assignments(
    connection,
    assignments: list[dict[str, Any]],
    run_id: str,
    boundary_source: str,
) -> int:
    audit_rows = [(
        run_id,
        item["parcel_id"],
        item["original_area_code"],
        item["inferred_area_code"],
        item["point_area_code"],
        item["overlap_ratio"],
        Json(item["intersections"]),
        item["decision"],
        boundary_source,
    ) for item in assignments]
    updates = [
        (item["inferred_area_code"], item["parcel_id"], item["original_area_code"])
        for item in assignments if item["decision"] == "applied"
    ]
    with connection:
        with connection.cursor() as cursor:
            ensure_audit_table(cursor)
            execute_values(cursor, """
                INSERT INTO parcel_region_assignment_audit (
                    run_id, parcel_id, original_area_code, inferred_area_code,
                    point_area_code, overlap_ratio, intersected_counties,
                    decision, boundary_source
                ) VALUES %s
            """, audit_rows, page_size=500)
            updated = 0
            for inferred_code, parcel_id, original_code in updates:
                cursor.execute("""
                    UPDATE parcel_info
                    SET area_code = %s, updated_at = NOW()
                    WHERE parcel_id = %s
                      AND area_code IS NOT DISTINCT FROM %s
                """, (inferred_code, parcel_id, original_code))
                updated += cursor.rowcount
    return updated


def rollback_run(connection, run_id: str) -> dict[str, Any]:
    with connection:
        with connection.cursor() as cursor:
            ensure_audit_table(cursor)
            cursor.execute("""
                UPDATE parcel_info AS parcel
                SET area_code = audit.original_area_code,
                    updated_at = NOW()
                FROM parcel_region_assignment_audit AS audit
                WHERE audit.run_id = %s
                  AND audit.decision = 'applied'
                  AND parcel.parcel_id = audit.parcel_id
                  AND parcel.area_code IS NOT DISTINCT FROM audit.inferred_area_code
            """, (run_id,))
            restored = cursor.rowcount
            cursor.execute("""
                SELECT COUNT(*) FROM parcel_region_assignment_audit
                WHERE run_id = %s AND decision = 'applied'
            """, (run_id,))
            expected = cursor.fetchone()[0]
    return {
        "mode": "rollback",
        "runId": run_id,
        "restored": restored,
        "notRestoredBecauseChangedOrMissing": expected - restored,
    }


def report_for(
    assignments: list[dict[str, Any]],
    minimum_overlap: float,
    mode: str,
    run_id: str | None,
    boundary_source: str,
) -> dict[str, Any]:
    inferred_distribution = Counter(
        item["inferred_area_code"] or "unmatched" for item in assignments
    )
    original_distribution = Counter(
        item["original_area_code"] or "missing" for item in assignments
    )
    decisions = Counter(item["decision"] for item in assignments)
    low_confidence = [item for item in assignments if item["decision"] == "review_required"]
    return {
        "mode": mode,
        "runId": run_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "minimumOverlap": minimum_overlap,
        "boundarySource": boundary_source,
        "parcelCount": len(assignments),
        "decisionCounts": dict(decisions),
        "originalAreaCodeDistribution": dict(sorted(original_distribution.items())),
        "inferredAreaCodeDistribution": dict(sorted(inferred_distribution.items())),
        "pointDominantAgreementCount": sum(
            item["point_area_code"] == item["inferred_area_code"] for item in assignments
        ),
        "multipleCountyIntersectionCount": sum(
            len(item["intersections"]) > 1 for item in assignments
        ),
        "reviewRequiredExamples": [{
            "parcelId": item["parcel_id"],
            "storedAreaCode": item["original_area_code"],
            "inferredAreaCode": item["inferred_area_code"],
            "overlapRatio": round(item["overlap_ratio"], 6),
            "intersections": item["intersections"],
        } for item in low_confidence[:20]],
    }


def write_report(report: dict[str, Any]) -> Path:
    output_dir = PROJECT_ROOT / "outputs" / "region_audits"
    output_dir.mkdir(parents=True, exist_ok=True)
    identity = report.get("runId") or "dry-run"
    path = output_dir / f"parcel-region-{identity}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="按县界空间重合度审计并纠正地块 area_code")
    parser.add_argument(
        "--county-file",
        type=Path,
        default=Path(os.environ.get("GUANGDONG_COUNTY_FILE", DEFAULT_COUNTY_FILE)),
    )
    parser.add_argument("--minimum-overlap", type=float, default=0.95)
    parser.add_argument("--apply", action="store_true", help="写入审计并纠正高置信地块")
    parser.add_argument("--rollback-run", help="回滚指定审计批次，不执行空间分析")
    args = parser.parse_args()
    load_dotenv()
    connection = db_connection()
    try:
        if args.rollback_run:
            report = rollback_run(connection, args.rollback_run)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if not 0 < args.minimum_overlap <= 1:
            parser.error("--minimum-overlap 必须在 (0,1] 范围内")
        fingerprint = boundary_fingerprint(args.county_file)
        source_owner = "soil_institute" if "土壤所数据" in str(args.county_file) else "external"
        boundary_source = f"{source_owner}:{args.county_file.name}:sha256:{fingerprint}"
        counties = read_counties(args.county_file)
        parcels = read_parcels(connection)
        assignments = infer_assignments(parcels, counties, args.minimum_overlap)
        run_id = str(uuid.uuid4()) if args.apply else None
        report = report_for(
            assignments,
            args.minimum_overlap,
            "apply" if args.apply else "dry-run",
            run_id,
            boundary_source,
        )
        if args.apply:
            report["updatedParcelCount"] = apply_assignments(
                connection, assignments, run_id, boundary_source,
            )
        else:
            report["updatedParcelCount"] = 0
        report_path = write_report(report)
        report["reportPath"] = str(report_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
