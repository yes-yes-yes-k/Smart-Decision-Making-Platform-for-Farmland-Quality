"""Validate and import Lechang county, township and village boundaries.

The command is a dry run unless ``--apply`` is supplied. Village-to-village
dispute polygons are retained as non-selectable ``zone`` records instead of
being assigned to either village.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import geopandas as gpd
import psycopg2
from psycopg2.extras import Json


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_BOUNDARY_DIR = Path(
    r"F:\BaiduNetdiskDownload\耕地质量大模型\土壤所数据\广东GIS"
)
SOIL_INSTITUTE_SOURCE = "soil_institute_gd_2020"
LEGACY_SOURCE = "lechang_admin_2016"
REPLACED_SOURCES = (LEGACY_SOURCE, SOIL_INSTITUTE_SOURCE)


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


def _one_shapefile(directory: Path, prefix: str) -> Path:
    matches = sorted(directory.glob(f"{prefix}*.shp"))
    if len(matches) != 1:
        raise RuntimeError(f"{directory} 中应有且仅有一个 {prefix}*.shp，实际 {len(matches)} 个")
    return matches[0]


def _read_boundary(path: Path, county_code: str | None = None) -> gpd.GeoDataFrame:
    frame = gpd.read_file(path)
    epsg = frame.crs.to_epsg() if frame.crs else None
    if epsg != 4490:
        raise RuntimeError(f"{path.name} 坐标系应为 EPSG:4490，实际为 {frame.crs}")
    if county_code is not None:
        if "FXZQDM" not in frame.columns:
            raise RuntimeError(f"{path.name} 缺少 FXZQDM 字段，无法提取乐昌边界")
        frame = frame.loc[frame["FXZQDM"].astype(str) == county_code].copy()
    if frame.empty or frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise RuntimeError(f"{path.name} 包含空数据或空几何")
    if not frame.geometry.is_valid.all():
        invalid = int((~frame.geometry.is_valid).sum())
        raise RuntimeError(f"{path.name} 包含 {invalid} 个无效几何，停止导入")
    return frame


def _boundary_files(directory: Path) -> tuple[Path, Path, Path, str, str]:
    province_layout = directory / "Guangdong_L4_XZQ.shp"
    if province_layout.exists():
        required = (
            directory / "Guangdong_L2_FXZQ.shp",
            directory / "Guangdong_L3_TXZQ.shp",
            province_layout,
        )
        missing = [path.name for path in required if not path.exists()]
        if missing:
            raise RuntimeError(f"广东 L0-L4 数据缺少文件: {missing}")
        return (*required, "guangdong_l0_l4", SOIL_INSTITUTE_SOURCE)
    return (
        _one_shapefile(directory, "01"),
        _one_shapefile(directory, "02"),
        _one_shapefile(directory, "03"),
        "lechang_standalone",
        LEGACY_SOURCE,
    )


def _record(
    object_type: str,
    object_id: str,
    display_name: str,
    area_code: str | None,
    parent: tuple[str, str] | None,
    geometry,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "object_type": object_type,
        "object_id": object_id,
        "display_name": display_name,
        "area_code": area_code,
        "parent_type": parent[0] if parent else None,
        "parent_id": parent[1] if parent else None,
        "wkt": geometry.wkt if geometry is not None else None,
        "metadata": metadata,
    }


def _topology_metrics(parts: gpd.GeoDataFrame, container: gpd.GeoDataFrame) -> dict[str, float]:
    projected_parts = parts.to_crs(6933)
    projected_container = container.to_crs(6933).geometry.union_all()
    combined = projected_parts.geometry.union_all()
    overlap = max(float(projected_parts.geometry.area.sum() - combined.area), 0.0)
    return {
        "overlapSquareKm": round(overlap / 1_000_000, 9),
        "outsideCountySquareKm": round(float(combined.difference(projected_container).area) / 1_000_000, 9),
        "uncoveredCountySquareKm": round(float(projected_container.difference(combined).area) / 1_000_000, 9),
    }


def build_records(directory: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    county_path, township_path, village_path, layout, source_name = _boundary_files(directory)
    filter_code = "440281" if layout == "guangdong_l0_l4" else None
    county = _read_boundary(county_path, filter_code)
    townships = _read_boundary(township_path, filter_code)
    villages = _read_boundary(village_path, filter_code)

    if len(county) != 1 or str(county.iloc[0]["FXZQDM"]) != "440281":
        raise RuntimeError("县界文件不是唯一的乐昌市 440281 边界")
    township_codes = {str(value) for value in townships["TXZQDM"]}
    if len(township_codes) != len(townships):
        raise RuntimeError("镇界文件存在重复 TXZQDM")
    township_topology = _topology_metrics(townships, county)
    village_topology = _topology_metrics(villages, county)
    tolerance_square_km = 0.001
    for level, topology in (("镇界", township_topology), ("村界", village_topology)):
        if any(value > tolerance_square_km for value in topology.values()):
            raise RuntimeError(f"{level}未能无缝覆盖县界: {topology}")

    records = [
        _record("province", "44", "广东省", "44", None, None, {
            "selectable": False, "boundaryAvailable": False,
        }),
        _record("city", "4402", "韶关市", "4402", ("province", "44"), None, {
            "selectable": False, "boundaryAvailable": False,
        }),
    ]
    county_row = county.iloc[0]
    records.append(_record(
        "county", "440281", str(county_row["FXZQMC"]), "440281", ("city", "4402"),
        county_row.geometry,
        {"selectable": True, "sourceFile": county_path.name, "sourceCrs": "EPSG:4490"},
    ))

    for _, row in townships.sort_values("TXZQDM").iterrows():
        code = str(row["TXZQDM"])
        records.append(_record(
            "township", code, str(row["TXZQMC"]), code, ("county", "440281"), row.geometry,
            {
                "selectable": True,
                "sourceObjectId": int(row["OBJECTID"]),
                "sourceFile": township_path.name,
                "sourceCrs": "EPSG:4490",
            },
        ))

    disputed = villages["XZQMC"].astype(str).str.contains("争议", na=False)
    normal_villages = villages.loc[~disputed]
    normal_codes = [str(value) for value in normal_villages["XZQDM"]]
    duplicates = [code for code, count in Counter(normal_codes).items() if count > 1]
    if duplicates:
        raise RuntimeError(f"普通村存在重复 XZQDM: {duplicates[:5]}")

    for _, row in normal_villages.sort_values("XZQDM").iterrows():
        code = str(row["XZQDM"])
        parent_code = str(row["TXZQDM"])
        if parent_code not in township_codes:
            raise RuntimeError(f"村 {code} 的上级乡镇 {parent_code} 不存在")
        records.append(_record(
            "village", code, str(row["XZQMC"]), code, ("township", parent_code), row.geometry,
            {
                "selectable": True,
                "sourceObjectId": int(row["OBJECTID"]),
                "sourceFile": village_path.name,
                "sourceCrs": "EPSG:4490",
            },
        ))

    mismatch_count = 0
    for _, row in villages.loc[disputed].sort_values("OBJECTID").iterrows():
        parent_code = str(row["TXZQDM"])
        raw_code = str(row["XZQDM"])
        mismatch = not raw_code.startswith(parent_code)
        mismatch_count += int(mismatch)
        records.append(_record(
            "zone", f"dispute:{int(row['OBJECTID'])}", str(row["XZQMC"]), raw_code,
            ("township", parent_code), row.geometry,
            {
                "selectable": False,
                "kind": "village_boundary_dispute",
                "rawVillageCode": raw_code,
                "parentCodeMismatch": mismatch,
                "sourceObjectId": int(row["OBJECTID"]),
                "sourceFile": village_path.name,
                "sourceCrs": "EPSG:4490",
            },
        ))

    area_frame = villages.to_crs(6933)
    report = {
        "source": source_name,
        "directory": str(directory),
        "datasetLayout": layout,
        "datasetLineage": "2016 boundary lineage; 2020-10 export metadata",
        "crs": "EPSG:4490",
        "counts": dict(Counter(record["object_type"] for record in records)),
        "villageFeatureCount": len(villages),
        "normalVillageCount": len(normal_villages),
        "disputeFeatureCount": int(disputed.sum()),
        "disputeParentCodeMismatchCount": mismatch_count,
        "disputeAreaSquareKm": round(float(area_frame.loc[disputed].area.sum()) / 1_000_000, 6),
        "allVillageAreaSquareKm": round(float(area_frame.area.sum()) / 1_000_000, 6),
        "townshipTopology": township_topology,
        "villageTopology": village_topology,
    }
    return records, report


def ensure_schema(cursor) -> None:
    cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spatial_region_catalog (
            id BIGSERIAL PRIMARY KEY,
            object_type VARCHAR(16) NOT NULL,
            object_id VARCHAR(64) NOT NULL,
            display_name VARCHAR(128) NOT NULL,
            area_code VARCHAR(32),
            parent_object_type VARCHAR(16),
            parent_object_id VARCHAR(64),
            layer_id BIGINT,
            geom geometry(MULTIPOLYGON,4326),
            source VARCHAR(32) NOT NULL,
            metadata JSON,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uk_spatial_region_catalog_object UNIQUE (object_type, object_id)
        )
    """)
    cursor.execute("""
        ALTER TABLE spatial_region_catalog
        ADD COLUMN IF NOT EXISTS geom geometry(MULTIPOLYGON,4326)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_spatial_region_catalog_geom
        ON spatial_region_catalog USING GIST (geom)
    """)


def import_records(records: list[dict[str, Any]], source_name: str) -> None:
    connection = db_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                ensure_schema(cursor)
                cursor.execute(
                    "UPDATE spatial_region_catalog SET enabled = FALSE, updated_at = NOW() WHERE source = ANY(%s)",
                    (list(REPLACED_SOURCES),),
                )
                for record in records:
                    cursor.execute("""
                        INSERT INTO spatial_region_catalog (
                            object_type, object_id, display_name, area_code,
                            parent_object_type, parent_object_id, geom, source,
                            metadata, enabled, updated_at
                        ) VALUES (
                            %(object_type)s, %(object_id)s, %(display_name)s, %(area_code)s,
                            %(parent_type)s, %(parent_id)s,
                            CASE WHEN %(wkt)s IS NULL THEN NULL ELSE
                                ST_Multi(ST_Transform(ST_GeomFromText(%(wkt)s, 4490), 4326))
                            END,
                            %(source)s, %(metadata)s, TRUE, NOW()
                        )
                        ON CONFLICT (object_type, object_id) DO UPDATE SET
                            display_name = EXCLUDED.display_name,
                            area_code = EXCLUDED.area_code,
                            parent_object_type = EXCLUDED.parent_object_type,
                            parent_object_id = EXCLUDED.parent_object_id,
                            geom = EXCLUDED.geom,
                            source = EXCLUDED.source,
                            metadata = EXCLUDED.metadata,
                            enabled = TRUE,
                            updated_at = NOW()
                    """, {
                        **record,
                        "source": source_name,
                        "metadata": Json(record["metadata"], dumps=lambda value: json.dumps(value, ensure_ascii=False)),
                    })
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="导入乐昌市县、镇、村行政边界")
    parser.add_argument(
        "--boundary-dir",
        type=Path,
        default=Path(os.environ.get("LECHANG_BOUNDARY_DIR", DEFAULT_BOUNDARY_DIR)),
    )
    parser.add_argument("--apply", action="store_true", help="写入数据库；默认只校验")
    args = parser.parse_args()
    load_dotenv()
    records, report = build_records(args.boundary_dir)
    report["mode"] = "apply" if args.apply else "dry-run"
    if args.apply:
        import_records(records, report["source"])
        report["databaseWrite"] = "committed"
    else:
        report["databaseWrite"] = "none"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
