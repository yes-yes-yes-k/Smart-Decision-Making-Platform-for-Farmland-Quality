"""导入 Model-1 shp 真实地块数据到数据库。

2024_测试数据.shp → parcel_info (5488 个真实地块)
2018/2021_测试数据.shp → parcel_history_snapshot (10976 条历史记录)
"""
import json
import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

env_path = _PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

import geopandas as gpd
import psycopg2
from psycopg2.extras import execute_values

SHAPEFILE_DIR = r"D:\destkop\模型1-5\模型1_v2\模型1_v2"
YEAR_FILES = {
    2018: "2018_测试数据.shp",
    2021: "2021_测试数据.shp",
    2024: "2024_测试数据.shp",
}

# V2.0 拼音 → V3.0 snake_case 字段映射
FIELD_MAP = {
    "SJD": "soil_ph",
    "YJZ": "organic_matter",
    "YXL": "available_phosphorus",
    "SXJ": "available_potassium",
    "TRRZ": "bulk_density",
    "YXTCHD": "topsoil_thickness",
    "GCHD": "plow_layer_thickness",
    "GCZD": "soil_texture",
    "GGNL": "irrigation_condition",
    "PSNL": "drainage_capacity",
    "DXBW": "terrain_position",
    "ZDGX": "soil_structure",
}

# 地类名称 → land_type
LAND_TYPE_MAP = {
    "旱地": "upland",
    "水浇地": "upland",
    "水田": "paddy",
}

# 新丰县 area_code
AREA_CODE = "440233"


def clean_value(val):
    """清理值：去除所有空白字符（含全角空格），None 转 None。"""
    if val is None:
        return None
    import re
    s = str(val)
    s = re.sub(r"[\s\u3000\xa0]+", "", s)
    return s if s else None


def to_float(val):
    """安全转 float。"""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def build_soil_indicators(row):
    """从 shp 行构建 V3.0 soil_indicators dict。

    只包含土壤指标。管理字段 target_ph、fertilizer_type、land_type
    必须写入 parcel_info 顶层规范列，禁止在 JSON 中重复保存。
    - exchangeable_hydrogen / exchangeable_aluminum / total_n: 由关联脚本
      link_soil_indicators.py 从 third_survey_profiles/topsoils 表按行政区域补充
    """
    indicators = {}
    for shp_field, v3_field in FIELD_MAP.items():
        val = row.get(shp_field)
        if v3_field in ("soil_texture", "irrigation_condition", "drainage_capacity",
                        "terrain_position", "soil_structure"):
            cleaned = clean_value(val)
            if cleaned:
                indicators[v3_field] = cleaned
        else:
            fval = to_float(val)
            if fval is not None:
                indicators[v3_field] = fval
    return indicators


def get_db_conn():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
    )


def create_history_table(cur):
    """创建 parcel_history_snapshot 表（如不存在）。"""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS parcel_history_snapshot (
            id SERIAL PRIMARY KEY,
            parcel_id VARCHAR(64) NOT NULL REFERENCES parcel_info(parcel_id),
            survey_year INTEGER NOT NULL,
            soil_indicators JSON,
            quality_grade VARCHAR(8),
            composite_index FLOAT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uk_parcel_history_parcel_year UNIQUE (parcel_id, survey_year)
        );
        CREATE INDEX IF NOT EXISTS idx_parcel_history_year ON parcel_history_snapshot(survey_year);
        CREATE INDEX IF NOT EXISTS idx_parcel_history_parcel_id ON parcel_history_snapshot(parcel_id);
    """)
    print("  parcel_history_snapshot 表已确保创建")


def import_parcels_2024(conn):
    """导入 2024 年数据到 parcel_info。"""
    print("\n=== 导入 2024 年数据到 parcel_info ===")
    shp_path = os.path.join(SHAPEFILE_DIR, YEAR_FILES[2024])
    gdf = gpd.read_file(shp_path, encoding="utf-8")
    gdf = gdf.to_crs(epsg=4326)  # CGCS2000 → WGS84

    cur = conn.cursor()

    rows = []
    skip_count = 0
    for _, row in gdf.iterrows():
        parcel_id = str(int(row["TYBH"]))
        land_type = LAND_TYPE_MAP.get(clean_value(row.get("DLMC")), "upland")
        indicators = build_soil_indicators(row)

        # 添加质量等级和综合指数到 indicators（供 Model-1 模块 4 邻域查询使用）
        gdzldj = clean_value(row.get("GDZLDJ"))
        zhqz = to_float(row.get("ZHQZ"))
        if gdzldj:
            indicators["quality_grade"] = gdzldj
        if zhqz is not None:
            indicators["composite_index"] = zhqz

        # 几何 WKT
        geom_wkt = row.geometry.wkt if row.geometry else None

        # 质心坐标
        centroid = row.geometry.centroid if row.geometry else None
        centroid_lon = float(centroid.x) if centroid else None
        centroid_lat = float(centroid.y) if centroid else None

        rows.append((
            parcel_id,
            geom_wkt,
            AREA_CODE,
            centroid_lon,
            centroid_lat,
            land_type,
            "compound",  # fertilizer_type（源数据无此字段，采用系统默认值）
            6.5,  # target_ph（广东省耕地一般目标值）
            json.dumps(indicators, ensure_ascii=False),
        ))

    # 批量插入（ON CONFLICT 跳过已存在的 parcel_id）
    insert_sql = """
        INSERT INTO parcel_info (parcel_id, geom, area_code, centroid_lon, centroid_lat,
                                  land_type, fertilizer_type, target_ph, soil_indicators)
        VALUES %s
        ON CONFLICT (parcel_id) DO UPDATE SET
            geom = EXCLUDED.geom,
            area_code = EXCLUDED.area_code,
            centroid_lon = EXCLUDED.centroid_lon,
            centroid_lat = EXCLUDED.centroid_lat,
            land_type = EXCLUDED.land_type,
            fertilizer_type = COALESCE(parcel_info.fertilizer_type, EXCLUDED.fertilizer_type),
            target_ph = COALESCE(parcel_info.target_ph, EXCLUDED.target_ph),
            soil_indicators = EXCLUDED.soil_indicators,
            updated_at = CURRENT_TIMESTAMP
    """

    # 使用 ST_GeomFromText 转换 WKT
    formatted_rows = []
    for r in rows:
        parcel_id, geom_wkt, area_code, lon, lat, lt, ft, tp, si = r
        if geom_wkt:
            geom_sql = psycopg2.sql.SQL("ST_GeomFromText(%s, 4326)").as_string(conn) if False else "ST_GeomFromText(%s, 4326)"
            # 直接用占位符
            formatted_rows.append((parcel_id, geom_wkt, area_code, lon, lat, lt, ft, tp, si))
        else:
            formatted_rows.append((parcel_id, None, area_code, lon, lat, lt, ft, tp, si))

    # 需要特殊处理 geom 列：用 ST_GeomFromText
    # 使用 execute_values 但 geom 列需要函数包裹
    # 改用逐行执行（5488 行不会太慢）
    batch_size = 500
    total = 0
    for i in range(0, len(formatted_rows), batch_size):
        batch = formatted_rows[i:i + batch_size]
        for r in batch:
            parcel_id, geom_wkt, area_code, lon, lat, lt, ft, tp, si = r
            if geom_wkt:
                cur.execute("""
                    INSERT INTO parcel_info (parcel_id, geom, area_code, centroid_lon, centroid_lat,
                                              land_type, fertilizer_type, target_ph, soil_indicators)
                    VALUES (%s, ST_GeomFromText(%s, 4326), %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (parcel_id) DO UPDATE SET
                        geom = EXCLUDED.geom,
                        area_code = EXCLUDED.area_code,
                        centroid_lon = EXCLUDED.centroid_lon,
                        centroid_lat = EXCLUDED.centroid_lat,
                        land_type = EXCLUDED.land_type,
                        fertilizer_type = COALESCE(parcel_info.fertilizer_type, EXCLUDED.fertilizer_type),
                        target_ph = COALESCE(parcel_info.target_ph, EXCLUDED.target_ph),
                        soil_indicators = EXCLUDED.soil_indicators,
                        updated_at = CURRENT_TIMESTAMP
                """, (parcel_id, geom_wkt, area_code, lon, lat, lt, ft, tp, si))
            else:
                cur.execute("""
                    INSERT INTO parcel_info (parcel_id, geom, area_code, centroid_lon, centroid_lat,
                                              land_type, fertilizer_type, target_ph, soil_indicators)
                    VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (parcel_id) DO UPDATE SET
                        area_code = EXCLUDED.area_code,
                        centroid_lon = EXCLUDED.centroid_lon,
                        centroid_lat = EXCLUDED.centroid_lat,
                        land_type = EXCLUDED.land_type,
                        fertilizer_type = COALESCE(parcel_info.fertilizer_type, EXCLUDED.fertilizer_type),
                        target_ph = COALESCE(parcel_info.target_ph, EXCLUDED.target_ph),
                        soil_indicators = EXCLUDED.soil_indicators,
                        updated_at = CURRENT_TIMESTAMP
                """, (parcel_id, area_code, lon, lat, lt, ft, tp, si))
        conn.commit()
        total += len(batch)
        print(f"  已导入 {total}/{len(formatted_rows)} ...")

    print(f"parcel_info 导入完成: {total} 个地块")
    return total


def import_history_snapshots(conn):
    """导入 2018/2021 年数据到 parcel_history_snapshot。"""
    cur = conn.cursor()

    for year in [2018, 2021]:
        print(f"\n=== 导入 {year} 年历史数据到 parcel_history_snapshot ===")
        shp_path = os.path.join(SHAPEFILE_DIR, YEAR_FILES[year])
        gdf = gpd.read_file(shp_path, encoding="utf-8")

        batch_size = 500
        total = 0
        for i in range(0, len(gdf), batch_size):
            batch = gdf.iloc[i:i + batch_size]
            for _, row in batch.iterrows():
                parcel_id = str(int(row["TYBH"]))
                indicators = build_soil_indicators(row)
                quality_grade = clean_value(row.get("GDZLDJ"))
                composite_index = to_float(row.get("ZHQZ"))

                cur.execute("""
                    INSERT INTO parcel_history_snapshot
                        (parcel_id, survey_year, soil_indicators, quality_grade, composite_index)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (parcel_id, survey_year) DO UPDATE SET
                        soil_indicators = EXCLUDED.soil_indicators,
                        quality_grade = EXCLUDED.quality_grade,
                        composite_index = EXCLUDED.composite_index
                """, (parcel_id, year, json.dumps(indicators, ensure_ascii=False),
                      quality_grade, composite_index))

            conn.commit()
            total += len(batch)
            print(f"  已导入 {total}/{len(gdf)} ...")

        print(f"{year} 年历史快照导入完成: {total} 条")

    # 也导入 2024 年到历史快照
    print(f"\n=== 导入 2024 年历史数据到 parcel_history_snapshot ===")
    shp_path = os.path.join(SHAPEFILE_DIR, YEAR_FILES[2024])
    gdf = gpd.read_file(shp_path, encoding="utf-8")

    batch_size = 500
    total = 0
    for i in range(0, len(gdf), batch_size):
        batch = gdf.iloc[i:i + batch_size]
        for _, row in batch.iterrows():
            parcel_id = str(int(row["TYBH"]))
            indicators = build_soil_indicators(row)
            quality_grade = clean_value(row.get("GDZLDJ"))
            composite_index = to_float(row.get("ZHQZ"))

            cur.execute("""
                INSERT INTO parcel_history_snapshot
                    (parcel_id, survey_year, soil_indicators, quality_grade, composite_index)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (parcel_id, survey_year) DO UPDATE SET
                    soil_indicators = EXCLUDED.soil_indicators,
                    quality_grade = EXCLUDED.quality_grade,
                    composite_index = EXCLUDED.composite_index
            """, (parcel_id, 2024, json.dumps(indicators, ensure_ascii=False),
                  quality_grade, composite_index))

        conn.commit()
        total += len(batch)
        print(f"  已导入 {total}/{len(gdf)} ...")

    print(f"2024 年历史快照导入完成: {total} 条")


def verify_import(conn):
    """验证导入结果。"""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM parcel_info")
    parcel_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM parcel_history_snapshot")
    history_count = cur.fetchone()[0]
    cur.execute("SELECT survey_year, COUNT(*) FROM parcel_history_snapshot GROUP BY survey_year ORDER BY survey_year")
    year_counts = cur.fetchall()

    print(f"\n=== 导入验证 ===")
    print(f"parcel_info: {parcel_count} 条")
    print(f"parcel_history_snapshot: {history_count} 条")
    for year, count in year_counts:
        print(f"  {year} 年: {count} 条")

    # 抽样检查
    cur.execute("""
        SELECT parcel_id, land_type, soil_indicators->>'soil_ph', soil_indicators->>'soil_texture',
               soil_indicators->>'irrigation_condition'
        FROM parcel_info WHERE parcel_id NOT LIKE 'P-VERIFY-%' LIMIT 5
    """)
    print(f"\n抽样检查 (前5个真实地块):")
    for r in cur.fetchall():
        print(f"  parcel_id={r[0]}, land_type={r[1]}, pH={r[2]}, texture={r[3]}, irrigation={r[4]}")


if __name__ == "__main__":
    t0 = time.time()
    conn = get_db_conn()
    cur = conn.cursor()
    create_history_table(cur)
    conn.commit()

    import_parcels_2024(conn)
    import_history_snapshots(conn)
    verify_import(conn)

    conn.close()
    elapsed = time.time() - t0
    print(f"\n总耗时: {elapsed:.1f}s")
