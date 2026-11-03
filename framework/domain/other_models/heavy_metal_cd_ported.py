"""移植数据集（原系统 soilgd）的读取、组装、归属与回归比对。

对应 openspec change ``import-cd-ported-dataset``：

- 命名空间：``SGD_<Farmland_ID>`` / ``SGD_<Farmland_ID>_<Sample_ID>``，与自有纯数字 parcel_id 隔离（design 决策 1）
- 列映射按 AcidMap 的 ORM 语义硬编码；``CropCd_input_data`` 的 AvaP/AvaK 是交叉的（design 决策 4）
- 乡镇归属写 ``cd_ported_parcel_township``，不写按面积计算的归属表（design 决策 2/7）
- 回归比对作为导入验收门（design 决策 5）

源库只读，直接 psycopg2 连接（库名固定 ``soilgd``），不经本项目 Session。
"""
from __future__ import annotations

import math
import os
from typing import Any, Iterable, Mapping, Sequence

PREFIX = "SGD_"
SOURCE_DB = "soilgd"

#: 模型对外字段 → soilgd 实际列名（依据 AcidMap 的 ORM Column 定义与 df 构造代码）。
DB_FEATURE_COLUMNS: dict[str, dict[str, str]] = {
    "crop_cd": {
        "silt_fraction": "002_0002IDW",
        "sand_fraction": "02_002IDW",
        "gravel_fraction": "2_02IDW",
        # 交叉：ORM available_phosphorus 建在 AvaK_IDW 列上、available_potassium 建在 AvaP_IDW 列上
        "available_phosphorus": "AvaK_IDW",
        "available_potassium": "AvaP_IDW",
        "slowly_available_potassium": "SAvaK_IDW",
        "total_aluminum": "TAl_IDW",
        "total_calcium": "TCa_IDW",
        "total_iron": "TFe_IDW",
        "total_magnesium": "TMg_IDW",
        "total_manganese": "TMn_IDW",
        "total_nitrogen": "TN_IDW",
        "total_sulfur": "TS_IDW",
        "solution": "solution",
    },
    "effective_cd": {
        "oc_fe_0_30": "OC-Fe_0-30",
        "silt_fraction": "002_0002IDW",
        "sand_fraction": "02_002IDW",
        "gravel_fraction": "2_02IDW",
        "available_potassium": "AvaK_IDW",
        "available_phosphorus": "AvaP_IDW",
        "electrical_conductivity": "EC_IDW",
        "slowly_available_potassium": "SAvaK_IDW",
        "total_aluminum": "TAl_IDW",
        "total_calcium": "TCa_IDW",
        "total_cadmium": "TCd_IDW",
        "exchangeable_base": "TEB_IDW",
        "exchangeable_hydrogen": "TExH_IDW",
        "total_iron": "TFe_IDW",
        "total_potassium": "TK_IDW",
        "total_magnesium": "TMg_IDW",
        "total_manganese": "TMn_IDW",
        "total_nitrogen": "TN_IDW",
        "total_phosphorus": "TP_IDW",
        "total_sulfur": "TS_IDW",
        "cdsolution": "Cdsolution",
    },
}

SOURCE_TABLES: dict[str, dict[str, str]] = {
    "crop_cd": {"input": "CropCd_input_data", "output": "CropCd_output_data", "out_col": "LnCropCd"},
    "effective_cd": {"input": "EffCd_input_data", "output": "EffCd_output_data", "out_col": "LnEffCd"},
}

LIKE_PATTERN = "SGD!_%"  # 配合 ESCAPE '!' 使用，避免下划线被当作通配符


class CdPortedError(RuntimeError):
    """移植数据集相关错误。"""


def ported_parcel_id(farmland_id: Any) -> str:
    return f"{PREFIX}{farmland_id}"


def ported_sample_id(farmland_id: Any, sample_id: Any) -> str:
    return f"{PREFIX}{farmland_id}_{sample_id}"


def source_connection():
    """只读连接源库 ``soilgd``（凭据复用 .env 的 DB_*）。"""
    import psycopg2

    missing = [k for k in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD") if not os.environ.get(k)]
    if missing:
        raise CdPortedError(f"缺少数据库环境变量: {missing}（脚本需先 load_dotenv）")
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dbname=SOURCE_DB,
        connect_timeout=10,
    )


def fetch_feature_rows(model_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    """从源库取完整特征行（含原始 Farmland_ID / Sample_ID 与坐标）。"""
    if model_id not in DB_FEATURE_COLUMNS:
        raise CdPortedError("unknown_model")
    columns = DB_FEATURE_COLUMNS[model_id]
    table = SOURCE_TABLES[model_id]["input"]
    select_cols = ", ".join(f'i."{col}"' for col in columns.values())
    sql = f"""
        SELECT i."Farmland_ID", i."Sample_ID", f.lon, f.lan, {select_cols}
        FROM "{table}" i
        JOIN "Farmland_data" f ON f."Farmland_ID" = i."Farmland_ID" AND f."Sample_ID" = i."Sample_ID"
        ORDER BY i."Farmland_ID"
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    con = source_connection()
    try:
        con.autocommit = True
        cur = con.cursor()
        cur.execute(sql)
        names = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        con.close()

    payload: list[dict[str, Any]] = []
    field_names = list(columns.keys())
    for row in rows:
        record = dict(zip(names, row))
        feature_values = [record[col] for col in columns.values()]
        if any(value is None for value in feature_values):
            continue  # 源表若有空值，该行不可用
        item: dict[str, Any] = {
            "farmland_id": record["Farmland_ID"],
            "recorded_sample_id": record["Sample_ID"],
            "lon": record["lon"],
            "lan": record["lan"],
        }
        for field, value in zip(field_names, feature_values):
            item[field] = float(value)
        payload.append(item)
    return payload


def rows_from_items(model_id: str, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """把 ``fetch_feature_rows`` 的结果转成 ``run(rows=...)`` 的完整特征行。"""
    if model_id not in DB_FEATURE_COLUMNS:
        raise CdPortedError("unknown_model")
    fields = list(DB_FEATURE_COLUMNS[model_id].keys())
    rows: list[dict[str, Any]] = []
    for item in items:
        row: dict[str, Any] = {
            "parcel_id": ported_parcel_id(item["farmland_id"]),
            "sample_id": ported_sample_id(item["farmland_id"], item["recorded_sample_id"]),
        }
        for field in fields:
            row[field] = item[field]
        rows.append(row)
    return rows


def build_rows(model_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    """组装成 ``run(rows=...)`` 需要的完整特征行（带 SGD_ 命名空间）。"""
    return rows_from_items(model_id, fetch_feature_rows(model_id, limit=limit))


def upsert_parcel_info(rows: Sequence[Mapping[str, Any]], source_items: Sequence[Mapping[str, Any]]) -> int:
    """把移植地块写入 ``parcel_info``：geom / area_code 留空（design 决策 6）。"""
    from sqlalchemy import text

    from framework.models.user import db

    if not rows:
        return 0
    payload = [
        {
            "parcel_id": row["parcel_id"],
            "legacy_parcel_code": f"soilgd:{item['farmland_id']}",
            "centroid_lon": item["lon"],
            "centroid_lat": item["lan"],
        }
        for row, item in zip(rows, source_items)
    ]
    inserted = 0
    batch = 2000
    for start in range(0, len(payload), batch):
        chunk = payload[start : start + batch]
        result = db.session.execute(
            text(
                """
                INSERT INTO parcel_info (parcel_id, legacy_parcel_code, centroid_lon, centroid_lat)
                VALUES (:parcel_id, :legacy_parcel_code, :centroid_lon, :centroid_lat)
                ON CONFLICT (parcel_id) DO NOTHING
                """
            ),
            chunk,
        )
        inserted += max(result.rowcount or 0, 0)
    db.session.commit()
    return inserted


def assign_townships() -> dict[str, int]:
    """移植点 → 乡镇：先点面包含，再对未命中的点取最近乡镇（记录距离）。"""
    from sqlalchemy import text

    from framework.models.user import db

    contains_sql = text(
        """
        INSERT INTO cd_ported_parcel_township (parcel_id, township_id, township_name, distance_m)
        SELECT p.parcel_id, t.object_id, t.display_name, 0
        FROM parcel_info p
        JOIN spatial_region_catalog t
          ON t.object_type = 'township'
         AND t.enabled
         AND t.geom IS NOT NULL
         AND ST_Contains(t.geom, ST_SetSRID(ST_MakePoint(p.centroid_lon, p.centroid_lat), 4326))
        WHERE p.parcel_id LIKE :pattern ESCAPE '!'
          AND p.centroid_lon IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM cd_ported_parcel_township x WHERE x.parcel_id = p.parcel_id
          )
        ON CONFLICT (parcel_id) DO NOTHING
        """
    )
    nearest_sql = text(
        """
        INSERT INTO cd_ported_parcel_township (parcel_id, township_id, township_name, distance_m)
        SELECT p.parcel_id, t.object_id, t.display_name,
               ST_Distance(t.geom::geography, pt.geog)
        FROM parcel_info p
        CROSS JOIN LATERAL (
            SELECT object_id, display_name, geom
            FROM spatial_region_catalog
            WHERE object_type = 'township' AND enabled AND geom IS NOT NULL
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint(p.centroid_lon, p.centroid_lat), 4326)
            LIMIT 1
        ) t
        CROSS JOIN LATERAL (
            SELECT ST_SetSRID(ST_MakePoint(p.centroid_lon, p.centroid_lat), 4326)::geography AS geog
        ) pt
        WHERE p.parcel_id LIKE :pattern ESCAPE '!'
          AND p.centroid_lon IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM cd_ported_parcel_township x WHERE x.parcel_id = p.parcel_id
          )
        """
    )
    inside = db.session.execute(contains_sql, {"pattern": LIKE_PATTERN}).rowcount or 0
    fallback = db.session.execute(nearest_sql, {"pattern": LIKE_PATTERN}).rowcount or 0
    db.session.commit()
    return {"inside": int(inside), "fallback": int(fallback)}


def compare_with_source(model_id: str, tolerance: float = 1e-4) -> dict[str, Any]:
    """导入后回归比对：本地结果 vs 源系统输出列。

    - crop_cd：源列 ``LnCropCd`` 是自然对数，比对本地 ``ln_*`` 的绝对差
    - effective_cd：源列 ``LnEffCd`` 实测存的是**浓度**，比对本地 ``exp(ln_*)`` 的相对差
    """
    if model_id not in SOURCE_TABLES:
        raise CdPortedError("unknown_model")
    from sqlalchemy import text

    from framework.models.user import db

    table = "cd_crop_prediction_result" if model_id == "crop_cd" else "cd_effective_prediction_result"
    column = "ln_crop_cd" if model_id == "crop_cd" else "ln_eff_cd"
    src = SOURCE_TABLES[model_id]
    con = source_connection()
    try:
        con.autocommit = True
        cur = con.cursor()
        cur.execute(f'SELECT "Farmland_ID", "Sample_ID", "{src["out_col"]}" FROM "{src["output"]}"')
        expected = {
            ported_sample_id(fid, sid): float(value)
            for fid, sid, value in cur.fetchall()
            if value is not None
        }
    finally:
        con.close()

    rows = db.session.execute(
        text(
            f"""
            SELECT parcel_id, sample_id, {column}
            FROM {table}
            WHERE parcel_id LIKE :pattern ESCAPE '!'
            """
        ),
        {"pattern": LIKE_PATTERN},
    ).all()

    diffs: list[float] = []
    over = 0
    for parcel_id, sample_id, log_value in rows:
        target = expected.get(sample_id)
        if target is None:
            continue
        if model_id == "crop_cd":
            diff = abs(float(log_value) - target)
        else:
            local_value = math.exp(float(log_value))
            diff = abs(local_value - target) / max(abs(target), 1e-12)
        diffs.append(diff)
        if diff > tolerance:
            over += 1

    diffs.sort()
    return {
        "model_id": model_id,
        "compared": len(diffs),
        "tolerance": tolerance,
        "max_diff": diffs[-1] if diffs else None,
        "median_diff": diffs[len(diffs) // 2] if diffs else None,
        "over_tolerance": over,
        "passed": bool(diffs) and over == 0,
    }


def rollback() -> dict[str, int]:
    """删除全部移植数据（只删 SGD_ 前缀，不碰自有数据）。"""
    from sqlalchemy import text

    from framework.models.user import db

    affected: dict[str, int] = {}
    for table, column in (
        ("cd_crop_prediction_result", "parcel_id"),
        ("cd_effective_prediction_result", "parcel_id"),
        ("cd_ported_parcel_township", "parcel_id"),
        ("parcel_info", "parcel_id"),
    ):
        result = db.session.execute(
            text(f"DELETE FROM {table} WHERE {column} LIKE :pattern ESCAPE '!'"),
            {"pattern": LIKE_PATTERN},
        )
        affected[table] = int(result.rowcount or 0)
    db.session.commit()
    return affected


def source_summary(model_id: str) -> dict[str, Any]:
    """源表规模概览（dry-run 用）。"""
    import psycopg2

    src = SOURCE_TABLES.get(model_id)
    if src is None:
        raise CdPortedError("unknown_model")
    con = source_connection()
    try:
        con.autocommit = True
        cur = con.cursor()
        cur.execute(f'SELECT count(*) FROM "{src["input"]}"')
        total = cur.fetchone()[0]
        cur.execute(f'SELECT count(*) FROM "{src["output"]}"')
        outputs = cur.fetchone()[0]
    finally:
        con.close()
    return {"model_id": model_id, "input_rows": int(total), "output_rows": int(outputs)}
