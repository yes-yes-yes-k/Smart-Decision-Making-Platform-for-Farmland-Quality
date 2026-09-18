"""Validate and import Guangdong L0-L4 administrative boundaries.

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
from shapely import from_wkt, get_parts, make_valid, union_all


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_BOUNDARY_DIR = Path(
    r"F:\BaiduNetdiskDownload\耕地质量大模型\土壤所数据\广东GIS"
)
SOIL_INSTITUTE_SOURCE = "soil_institute_gd_2020"
LEGACY_SOURCE = "lechang_admin_2016"
REPLACED_SOURCES = (LEGACY_SOURCE, SOIL_INSTITUTE_SOURCE)

LEVEL_SPECS = (
    ("province", "Guangdong_L0_PXZQ.shp", "PXZQDM", "PXZQMC", None, None, 2),
    ("city", "Guangdong_L1_CXZQ.shp", "CXZQDM", "CXZQMC", "province", "PXZQDM", 4),
    ("county", "Guangdong_L2_FXZQ.shp", "FXZQDM", "FXZQMC", "city", "CXZQDM", 6),
    ("township", "Guangdong_L3_TXZQ.shp", "TXZQDM", "TXZQMC", "county", "FXZQDM", 9),
    ("village", "Guangdong_L4_XZQ.shp", "XZQDM", "XZQMC", "township", "TXZQDM", 12),
)

SCOPE_CODES = {
    "lechang": "440281",
    "shaoguan": "4402",
    "guangdong": "44",
}


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


def _scope_where(code_field: str, code_length: int, scope_code: str) -> str:
    if code_length <= len(scope_code):
        value = scope_code[:code_length]
        return f"{code_field} = '{value}'"
    return f"{code_field} LIKE '{scope_code}%'"


def _read_scoped_level(
    directory: Path,
    filename: str,
    code_field: str,
    code_length: int,
    scope_code: str,
    repair_invalid: bool = False,
) -> gpd.GeoDataFrame:
    path = directory / filename
    if not path.exists():
        raise RuntimeError(f"广东 L0-L4 数据缺少文件: {filename}")
    frame = gpd.read_file(
        path,
        where=_scope_where(code_field, code_length, scope_code),
        encoding="utf-8",
    )
    epsg = frame.crs.to_epsg() if frame.crs else None
    if epsg != 4490:
        raise RuntimeError(f"{path.name} 坐标系应为 EPSG:4490，实际为 {frame.crs}")
    if frame.empty:
        raise RuntimeError(f"{path.name} 在范围 {scope_code} 内没有数据")
    if frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise RuntimeError(f"{path.name} 包含空几何")
    invalid_mask = ~frame.geometry.is_valid
    invalid = int(invalid_mask.sum())
    if invalid and not repair_invalid:
        invalid_ids = frame.loc[invalid_mask, "OBJECTID"].astype(int).tolist()
        raise RuntimeError(
            f"{path.name} 包含 {invalid} 个无效几何（OBJECTID={invalid_ids[:10]}），"
            "停止导入；复核后可显式传 --repair-invalid"
        )
    if invalid:
        frame = frame.copy()
        for index in frame.index[invalid_mask]:
            fixed = make_valid(frame.at[index, "geometry"])
            polygonal_parts = [
                part for part in get_parts(fixed)
                if part.geom_type in {"Polygon", "MultiPolygon"}
            ]
            if not polygonal_parts:
                object_id = frame.at[index, "OBJECTID"]
                raise RuntimeError(f"{path.name} OBJECTID={object_id} 无法修复为面几何")
            frame.at[index, "geometry"] = union_all(polygonal_parts)
        if (~frame.geometry.is_valid).any() or frame.geometry.is_empty.any():
            raise RuntimeError(f"{path.name} 无效几何修复后仍未通过校验")
    frame.attrs["repaired_invalid_count"] = invalid if repair_invalid else 0
    return frame


def _clean_boundary_name(value: Any) -> str:
    name = str(value or "").replace("\ufffd", "").strip()
    if not name:
        raise RuntimeError("行政区名称为空或无法解码")
    return name


def _best_boundary_name(values) -> str:
    names = [_clean_boundary_name(value) for value in values]
    # Duplicate codes are usually multipart or enclave features. Prefer the
    # shortest clean name because suffixes such as “飞地” describe a part,
    # not the administrative object itself.
    return min(set(names), key=lambda item: ("飞地" in item, len(item), item))


def _dissolved_records(
    frame: gpd.GeoDataFrame,
    *,
    object_type: str,
    code_field: str,
    name_field: str,
    parent_type: str | None,
    parent_field: str | None,
    source_file: str,
    disambiguate_parent_collisions: bool = False,
    parent_name_field: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    duplicate_parts = 0
    collision_codes: set[str] = set()
    group_fields: str | list[str] = code_field
    if disambiguate_parent_collisions and parent_field:
        parent_counts = frame.groupby(code_field, dropna=False)[parent_field].nunique()
        collision_codes = {str(code) for code in parent_counts[parent_counts > 1].index}
        group_fields = [code_field, parent_field]

    for group_key, group in frame.groupby(group_fields, sort=True, dropna=False):
        code_value = group_key[0] if isinstance(group_key, tuple) else group_key
        code = str(code_value or "").strip()
        if not code:
            raise RuntimeError(f"{source_file} 存在空的 {code_field}")
        duplicate_parts += max(len(group) - 1, 0)
        parent = None
        if parent_field:
            parent_codes = {str(value).strip() for value in group[parent_field] if str(value).strip()}
            if len(parent_codes) != 1:
                raise RuntimeError(f"{object_type} {code} 的父级编码不唯一: {sorted(parent_codes)}")
            parent = (str(parent_type), next(iter(parent_codes)))
        geometry = group.geometry.union_all()
        if geometry.is_empty or not geometry.is_valid:
            raise RuntimeError(f"{object_type} {code} 合并后几何无效")
        object_ids = [int(value) for value in group["OBJECTID"] if value is not None]
        catalog_id = code
        if code in collision_codes and parent:
            catalog_id = f"{code}:{parent[1]}"
        metadata = {
            "selectable": True,
            "sourceObjectIds": object_ids,
            "rawAreaCode": code,
            "parentCodeCollision": code in collision_codes,
            "sourceFile": source_file,
            "sourceCrs": "EPSG:4490",
        }
        if parent_name_field:
            metadata["sourceParentName"] = _best_boundary_name(group[parent_name_field])
        if "FXZQMC" in group.columns:
            metadata["sourceCountyName"] = _best_boundary_name(group["FXZQMC"])
        if "CXZQMC" in group.columns:
            metadata["sourceCityName"] = _best_boundary_name(group["CXZQMC"])
        records.append(_record(
            object_type,
            catalog_id,
            _best_boundary_name(group[name_field]),
            code,
            parent,
            geometry,
            metadata,
        ))
    return records, duplicate_parts


def _add_synthetic_region_parents(records: list[dict[str, Any]]) -> dict[str, int]:
    """Create non-selectable parents for direct-admin source placeholders."""
    keys = {(record["object_type"], record["object_id"]) for record in records}
    missing_ids = sorted({
        record["parent_id"]
        for record in records
        if record["parent_type"] == "township"
        and ("township", record["parent_id"]) not in keys
    })
    synthetic_counties = 0
    for parent_id in missing_ids:
        children = [record for record in records if record["parent_type"] == "township" and record["parent_id"] == parent_id]
        county_id = str(parent_id)[:6]
        if ("county", county_id) not in keys:
            city_id = county_id[:4]
            if ("city", city_id) not in keys:
                raise RuntimeError(f"缺失县级 {county_id} 无法挂接地市父节点 {city_id}")
            county_names = [
                record["metadata"].get("sourceCountyName")
                for record in children
                if record["metadata"].get("sourceCountyName")
            ]
            county_name = _best_boundary_name(county_names) if county_names else f"{city_id}直属区域"
            county_geometry = union_all([from_wkt(record["wkt"]) for record in children if record["wkt"]])
            records.append(_record(
                "county",
                county_id,
                county_name,
                county_id,
                ("city", city_id),
                county_geometry,
                {
                    "selectable": False,
                    "syntheticFromVillageParent": True,
                    "sourceChildCount": len(children),
                    "sourceFile": "Guangdong_L4_XZQ.shp",
                    "sourceCrs": "EPSG:4490",
                },
            ))
            keys.add(("county", county_id))
            synthetic_counties += 1
        names = [
            record["metadata"].get("sourceParentName")
            for record in children
            if record["metadata"].get("sourceParentName")
        ]
        display_name = _best_boundary_name(names) if names else f"{county_id}直属区域"
        geometry = union_all([from_wkt(record["wkt"]) for record in children if record["wkt"]])
        records.append(_record(
            "township",
            str(parent_id),
            display_name,
            str(parent_id),
            ("county", county_id),
            geometry,
            {
                "selectable": False,
                "syntheticFromVillageParent": True,
                "sourceChildCount": len(children),
                "sourceFile": "Guangdong_L4_XZQ.shp",
                "sourceCrs": "EPSG:4490",
            },
        ))
        keys.add(("township", str(parent_id)))
    return {"county": synthetic_counties, "township": len(missing_ids)}


def build_scope_records(
    directory: Path,
    scope_code: str = "440281",
    repair_invalid: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build L0-L4 records for a county, city or the whole province.

    ``scope_code`` accepts a 6-digit county, 4-digit city or 2-digit province
    code. Source feature parts sharing one administrative code are dissolved
    into one catalog geometry.
    """
    if len(scope_code) not in {2, 4, 6} or not scope_code.isdigit():
        raise RuntimeError("scope_code 必须为 2 位省、4 位市或 6 位县级行政区代码")
    if len(scope_code) == 2:
        raise RuntimeError("省级范围必须使用分地市流式模式，避免一次载入全省村界导致内存耗尽")

    records: list[dict[str, Any]] = []
    feature_counts: dict[str, int] = {}
    duplicate_counts: dict[str, int] = {}
    repaired_invalid_counts: dict[str, int] = {}
    dispute_count = 0

    for (
        object_type,
        filename,
        code_field,
        name_field,
        parent_type,
        parent_field,
        code_length,
    ) in LEVEL_SPECS:
        frame = _read_scoped_level(
            directory, filename, code_field, code_length, scope_code,
            repair_invalid=repair_invalid,
        )
        feature_counts[object_type] = len(frame)
        repaired_invalid_counts[object_type] = int(frame.attrs.get("repaired_invalid_count", 0))

        if object_type == "village":
            names = frame[name_field].map(_clean_boundary_name)
            disputed = names.str.contains("争议", na=False)
            normal_records, duplicate_parts = _dissolved_records(
                frame.loc[~disputed],
                object_type=object_type,
                code_field=code_field,
                name_field=name_field,
                parent_type=parent_type,
                parent_field=parent_field,
                source_file=filename,
                disambiguate_parent_collisions=True,
                parent_name_field="TXZQMC",
            )
            records.extend(normal_records)
            duplicate_counts[object_type] = duplicate_parts
            for _, row in frame.loc[disputed].sort_values("OBJECTID").iterrows():
                object_id = int(row["OBJECTID"])
                records.append(_record(
                    "zone",
                    f"dispute:{object_id}",
                    _clean_boundary_name(row[name_field]),
                    str(row[code_field]),
                    ("township", str(row[parent_field])),
                    row.geometry,
                    {
                        "selectable": False,
                        "kind": "village_boundary_dispute",
                        "rawVillageCode": str(row[code_field]),
                        "sourceObjectId": object_id,
                        "sourceFile": filename,
                        "sourceCrs": "EPSG:4490",
                        "sourceParentName": _clean_boundary_name(row["TXZQMC"]),
                        "sourceCountyName": _clean_boundary_name(row["FXZQMC"]),
                        "sourceCityName": _clean_boundary_name(row["CXZQMC"]),
                    },
                ))
            dispute_count = int(disputed.sum())
            continue

        level_records, duplicate_parts = _dissolved_records(
            frame,
            object_type=object_type,
            code_field=code_field,
            name_field=name_field,
            parent_type=parent_type,
            parent_field=parent_field,
            source_file=filename,
        )
        records.extend(level_records)
        duplicate_counts[object_type] = duplicate_parts

    synthetic_parent_counts = _add_synthetic_region_parents(records)
    keys = {(record["object_type"], record["object_id"]) for record in records}
    missing_parents = [
        (record["object_type"], record["object_id"], record["parent_type"], record["parent_id"])
        for record in records
        if record["parent_type"] and (record["parent_type"], record["parent_id"]) not in keys
    ]
    if missing_parents:
        raise RuntimeError(f"存在缺失父级的行政区记录: {missing_parents[:5]}")

    return records, {
        "source": SOIL_INSTITUTE_SOURCE,
        "directory": str(directory),
        "datasetLayout": "guangdong_l0_l4",
        "datasetLineage": "2016 boundary lineage; 2020-10 export metadata",
        "scopeCode": scope_code,
        "crs": "EPSG:4490",
        "counts": dict(Counter(record["object_type"] for record in records)),
        "sourceFeatureCounts": feature_counts,
        "dissolvedDuplicateParts": duplicate_counts,
        "disputeFeatureCount": dispute_count,
        "parentIntegrity": "passed",
        "geometryValidity": "passed",
        "repairedInvalidGeometries": repaired_invalid_counts,
        "syntheticRegionParents": synthetic_parent_counts,
    }


def _province_city_codes(directory: Path, province_code: str) -> list[str]:
    frame = _read_scoped_level(
        directory,
        "Guangdong_L1_CXZQ.shp",
        "CXZQDM",
        4,
        province_code,
    )
    return sorted({str(value).strip() for value in frame["CXZQDM"] if str(value).strip()})


def _merge_city_reports(reports: list[dict[str, Any]], province_code: str) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    duplicate_counts: Counter[str] = Counter()
    repaired_counts: Counter[str] = Counter()
    for report in reports:
        counts.update(report["counts"])
        source_counts.update(report["sourceFeatureCounts"])
        duplicate_counts.update(report["dissolvedDuplicateParts"])
        repaired_counts.update(report["repairedInvalidGeometries"])
    # Every city batch contains the same province feature. It is upserted in
    # apply mode and must only be counted once in the province summary.
    counts["province"] = 1
    source_counts["province"] = 1
    return {
        "source": SOIL_INSTITUTE_SOURCE,
        "directory": reports[0]["directory"] if reports else None,
        "datasetLayout": "guangdong_l0_l4_streamed_by_city",
        "datasetLineage": "2016 boundary lineage; 2020-10 export metadata",
        "scopeCode": province_code,
        "crs": "EPSG:4490",
        "cityBatchCount": len(reports),
        "counts": dict(counts),
        "sourceFeatureCounts": dict(source_counts),
        "dissolvedDuplicateParts": dict(duplicate_counts),
        "disputeFeatureCount": sum(int(report["disputeFeatureCount"]) for report in reports),
        "parentIntegrity": "passed",
        "geometryValidity": "passed",
        "repairedInvalidGeometries": dict(repaired_counts),
        "syntheticRegionParents": {
            "county": sum(int(report["syntheticRegionParents"]["county"]) for report in reports),
            "township": sum(int(report["syntheticRegionParents"]["township"]) for report in reports),
        },
    }


def process_province_scope(
    directory: Path,
    province_code: str,
    *,
    repair_invalid: bool,
    apply: bool,
) -> dict[str, Any]:
    """Validate and optionally import a province one city at a time."""
    city_codes = _province_city_codes(directory, province_code)
    reports: list[dict[str, Any]] = []

    # Complete a read-only preflight before any database record is changed.
    for city_code in city_codes:
        records, report = build_scope_records(
            directory, city_code, repair_invalid=repair_invalid,
        )
        reports.append(report)
        print(json.dumps({"preflightCity": city_code, "counts": report["counts"]}, ensure_ascii=False), flush=True)
        del records

    if apply:
        for index, city_code in enumerate(city_codes):
            records, report = build_scope_records(
                directory, city_code, repair_invalid=repair_invalid,
            )
            import_records(
                records,
                report["source"],
                deactivate_existing=index == 0,
            )
            print(json.dumps({"importedCity": city_code, "counts": report["counts"]}, ensure_ascii=False), flush=True)
            del records

    return _merge_city_reports(reports, province_code)


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


def import_records(
    records: list[dict[str, Any]],
    source_name: str,
    *,
    deactivate_existing: bool = True,
) -> None:
    connection = db_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                ensure_schema(cursor)
                if deactivate_existing:
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
    parser = argparse.ArgumentParser(description="校验并导入广东 L0-L4 行政边界")
    parser.add_argument(
        "--boundary-dir",
        type=Path,
        default=Path(os.environ.get(
            "GUANGDONG_BOUNDARY_DIR",
            os.environ.get("LECHANG_BOUNDARY_DIR", DEFAULT_BOUNDARY_DIR),
        )),
    )
    parser.add_argument("--apply", action="store_true", help="写入数据库；默认只校验")
    parser.add_argument(
        "--scope",
        choices=tuple(SCOPE_CODES),
        default="lechang",
        help="预设导入范围；默认 lechang",
    )
    parser.add_argument(
        "--scope-code",
        help="自定义 2 位省、4 位市或 6 位县级代码；设置后覆盖 --scope",
    )
    parser.add_argument(
        "--repair-invalid",
        action="store_true",
        help="显式修复源数据中的无效面并重新校验；默认遇到无效几何即停止",
    )
    args = parser.parse_args()
    load_dotenv()
    scope_code = args.scope_code or SCOPE_CODES[args.scope]
    if len(scope_code) == 2:
        report = process_province_scope(
            args.boundary_dir,
            scope_code,
            repair_invalid=args.repair_invalid,
            apply=args.apply,
        )
        records = None
    else:
        records, report = build_scope_records(
            args.boundary_dir,
            scope_code,
            repair_invalid=args.repair_invalid,
        )
    report["mode"] = "apply" if args.apply else "dry-run"
    if args.apply and records is not None:
        import_records(records, report["source"])
        report["databaseWrite"] = "committed"
    else:
        report["databaseWrite"] = "none"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
