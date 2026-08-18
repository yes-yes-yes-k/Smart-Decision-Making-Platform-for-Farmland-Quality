# scripts/import_history_snapshots.py
"""从原始 Shapefile 导入历史数据到 parcel_history_snapshot 表。

读取 D:\\destkop\\模型1-5\\模型1_v2\\模型1_v2\\ 下 2018/2021/2024 Shapefile，
按 parcel_id 关联写入 DB。
"""
import os
import sys
import logging

logger = logging.getLogger(__name__)

SHAPEFILE_DIR = r"D:\destkop\模型1-5\模型1_v2\模型1_v2"
YEAR_FILES = {
    2018: "2018_测试数据.shp",
    2021: "2021_测试数据.shp",
    2024: "2024_测试数据.shp",
}


def import_history_snapshots():
    """导入历史快照。"""
    try:
        import shapefile  # pyshp
    except ImportError:
        logger.error("pyshp 未安装，请运行: pip install pyshp")
        return

    from framework import db
    from framework.models.thematic_model import ParcelHistorySnapshot, ParcelInfo

    # 建立 parcel_id 映射（按顺序关联，实际应按地块编号匹配）
    existing_parcels = {p.parcel_id: p for p in ParcelInfo.query.all()}

    for year, filename in YEAR_FILES.items():
        filepath = os.path.join(SHAPEFILE_DIR, filename)
        if not os.path.exists(filepath):
            logger.warning("Shapefile 不存在: %s", filepath)
            continue

        sf = shapefile.Reader(filepath)
        fields = [f[0] for f in sf.fields[1:]]  # 跳过 DeletionFlag

        for record in sf.records():
            row = dict(zip(fields, record))
            # 尝试匹配 parcel_id（原始 Shapefile 用 TYBH 或地块编号）
            parcel_id = _match_parcel_id(row, existing_parcels)
            if not parcel_id:
                continue

            # 检查是否已存在
            existing = ParcelHistorySnapshot.query.filter_by(
                parcel_id=parcel_id, survey_year=year).first()
            if existing:
                continue

            snapshot = ParcelHistorySnapshot(
                parcel_id=parcel_id,
                survey_year=year,
                soil_indicators=_extract_indicators(row),
                quality_grade=str(row.get("GDZLDJ", "")),
                composite_index=float(row.get("ZHQZ", 0)),
            )
            db.session.add(snapshot)

        db.session.commit()
        logger.info("已导入 %d 年历史数据", year)


def _match_parcel_id(row: dict, existing_parcels: dict) -> str:
    """匹配 Shapefile 记录到 DB parcel_id。"""
    # 尝试 TYBH 或其他字段
    for key in ("TYBH", "tybh", "parcel_id", "PARCEL_ID"):
        if key in row:
            val = str(row[key])
            if val in existing_parcels:
                return val
    return None


def _extract_indicators(row: dict) -> dict:
    """从 Shapefile 记录提取指标。"""
    indicators = {}
    field_map = {
        "SJD": "soil_ph", "YJZ": "organic_matter", "YXL": "available_phosphorus",
        "SXJ": "available_potassium", "TRRZ": "bulk_density",
        "YXTCHD": "topsoil_thickness", "GCHD": "plow_layer_thickness",
    }
    for old_key, new_key in field_map.items():
        if old_key in row:
            indicators[new_key] = float(row[old_key])
    return indicators


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import_history_snapshots()
