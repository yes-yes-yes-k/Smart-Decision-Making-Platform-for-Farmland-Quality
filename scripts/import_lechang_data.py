"""乐昌市土壤数据导入脚本。

从 data/<area>/ 下的 Excel 文件批量导入到数据库。
- 支持 .xlsx（openpyxl）与 .xls（xlrd）
- 加密文件跳过并 warning，不抛异常
- 幂等：每张表先 DELETE 后 bulk_insert_mappings，每表独立 commit
- datetime 字段转 ISO 字符串存储

用法:
    python scripts/import_lechang_data.py --area lechang
    python scripts/import_lechang_data.py --area lechang --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type

import pandas as pd
from sqlalchemy import inspect as sa_inspect

# 确保 src 在 sys.path（与 init_db.py 一致）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
import framework.models.soil_data as soil_data_models  # noqa: E402,F401 触发注册
from framework.models.soil_data import (  # noqa: E402
    ThirdSurveyTopsoil,
    ThirdSurveyProfile,
    ThirdSurveySiteCondition,
    ThirdSurveyBulkDensity,
    SecondSurveyPoint,
    FormulaFertilization,
    AgriChemicalization,
    GrainYield,
)

logger = logging.getLogger("import_lechang")

# 各数据源列名映射表：{源 Excel 列名: 模型英文字段名}
# 源列名含前导/尾随空格的（如 " Ni"、"TK "）写其 strip 后形式，由 _prepare_dataframe 统一 strip。
COLUMN_MAPS: Dict[str, Dict[str, str]] = {
    "third_survey_topsoil": {
        "ID": "sample_id", "lon": "lon", "lat": "lat", "经度": "lon", "纬度": "lat",
        "City": "city", "County": "county", "LULC": "lulc", "质地": "texture", "SM": "sm",
        "pH": "ph", "CEC": "cec", "SOM": "som", "TN": "tn", "TP": "tp", "TK": "tk",
        "AP": "ap", "AK": "ak", "SAK": "sak",
        "交换性盐基总量": "exchangeable_base_sum", "交换性钙": "exchangeable_ca",
        "交换性镁": "exchangeable_mg", "交换性钠": "exchangeable_na", "交换性钾": "exchangeable_k",
        "水溶性盐总量": "water_soluble_salt_sum", "电导率": "conductivity",
        "S": "s", "Si": "si", "Fe": "fe", "Mn": "mn", "Cu": "cu", "Zn": "zn",
        "B": "b", "Mu": "mu",
        "Hg": "hg", "As": "as", "Pb": "pb", "Cd": "cd", "Cr": "cr", "Ni": "ni",
    },
    "third_survey_profile": {
        "样品编号": "sample_no", "原样品编号": "original_sample_no", "样点编号": "point_no",
        "lon": "lon", "lat": "lat", "经度": "lon", "纬度": "lat",
        "行政区划": "admin_region", "土地利用类型": "land_use_type", "检测实验室": "lab",
        "pH": "ph", "有机质": "organic_matter", "全氮": "total_n", "全磷": "total_p", "全钾": "total_k",
        "有效磷": "avail_p", "速效钾": "quick_k", "缓效钾": "slow_k",
        "阳离子交换量": "cation_exchange_capacity", "交换性酸总量": "exchangeable_acid_total",
        "土纲": "soil_order", "亚纲": "soil_suborder", "土类": "soil_group",
        "亚类": "soil_subgroup", "土属": "soil_genus", "土种": "soil_species",
        "有效土层厚度": "effective_soil_depth", "耕作层厚度": "plow_layer_depth",
    },
    "third_survey_site_condition": {
        "样点编号": "point_no", "lon": "lon", "lat": "lat", "经度": "lon", "纬度": "lat",
        "行政区划": "admin_region", "坐落位置": "location", "采样类型": "sample_type",
        "地类": "land_class", "土壤类型": "soil_type", "调查时间": "survey_time",
        "海拔高度": "altitude", "天气情况": "weather",
        "大地形": "macro_landform", "中地形": "meso_landform", "小地形": "micro_landform",
        "地形部位": "slope_position", "坡度": "slope", "坡向": "slope_aspect",
        "母岩": "parent_rock", "母质": "parent_material",
        "植被类型": "vegetation_type", "植被覆盖度": "vegetation_coverage",
        "土地利用类型现状": "land_use_current", "灌溉保证率": "irrigation_guarantee_rate",
        "排水条件": "drainage_condition", "熟制类型": "cropping_system",
        "轮作制度第一季": "rotation_first", "施肥方式": "fertilization_method",
    },
    "third_survey_bulk_density": {
        "行政区划": "admin_region", "lon": "lon", "lat": "lat", "经度": "lon", "纬度": "lat",
        "接样时间": "sample_time", "报告时间": "report_time",
        "土壤容重1": "bulk_density_1", "土壤容重2": "bulk_density_2",
        "土壤容重3": "bulk_density_3", "土壤容重4": "bulk_density_4",
        "土壤容重平均值": "bulk_density_avg", "检测方法": "test_method",
    },
    "second_survey_point": {
        "ID": "sample_id", "序号": "seq", "市": "city", "县": "county",
        "数据来源": "data_source", "报告页码": "report_page", "样点编号": "point_no",
        "二普采样地点": "sampling_location", "现行地址": "current_address",
        "lon": "lon", "lat": "lat", "经度": "lon", "纬度": "lat",
        "二普土类": "soil_type_2p", "二普亚类": "subgroup_2p", "二普土属": "soil_genus_2p",
        "二普土种": "soil_species_2p",
        "第一层pH水提": "ph_water_l1", "第一层pH盐提": "ph_salt_l1",
        "第一层有机质%": "om_l1", "第一层全氮%": "tn_l1", "第一层全磷P2O5%": "tp_l1",
        "第一层全钾K2O%": "tk_l1", "第一层碱解氮PPM": "alkali_n_l1",
        "第一层速效磷PPM": "avail_p_l1", "第一层速效钾PPM": "avail_k_l1",
        "耕层厚度cm": "plow_layer_depth_cm", "有效土层厚度cm": "effective_depth_cm",
    },
    "formula_fertilization": {
        "ID": "sample_id", "采样日期": "sample_date", "年份": "year",
        "市": "city", "县": "county", "镇": "town",
        "lat": "lat", "lon": "lon", "纬度": "lat", "经度": "lon", "海拔m": "altitude",
        "地貌": "landform", "地形": "terrain", "地面坡度": "surface_slope",
        "田面坡度": "field_slope", "坡向": "slope_aspect",
        "通常地下水": "usual_groundwater", "最高地下水": "max_groundwater",
        "最深地下水": "min_groundwater", "基础设施": "infrastructure",
        "排水能力": "drainage_capacity", "灌溉能力": "irrigation_capacity",
        "水源条件": "water_source", "熟制": "cropping_system",
        "种植制度": "planting_system", "年产量kg/亩": "annual_yield_kg_mu", "作物": "crop",
        "土类": "soil_type", "土亚类": "soil_subgroup", "土属": "soil_genus",
        "土种": "soil_species", "成土母质": "parent_material", "剖面构型": "profile_structure",
        "土壤质地": "soil_texture", "土壤结构": "soil_structure",
        "障碍因素": "obstacle_factor", "侵蚀程度": "erosion_degree",
        "pH": "ph", "有机质": "organic_matter", "全氮": "total_n", "碱解氮": "alkali_n",
        "有效磷": "avail_p", "缓效钾": "slow_k", "速效钾": "quick_k",
        "交换性钙": "exchangeable_ca", "交换性镁": "exchangeable_mg",
        "有效铁": "avail_fe", "有效锰": "avail_mn", "有效铜": "avail_cu",
        "有效锌": "avail_zn", "水溶态硼": "water_sol_b", "有效钼": "avail_mo", "有效硫": "avail_s",
    },
    "agri_chemicalization": {
        "年份": "year", "县区": "county", "化肥施用量": "chemical_fertilizer_amount",
    },
    "grain_yield": {
        "年份": "year", "县区": "county", "播种面积": "sown_area", "产量": "yield",
    },
}

# 数据源配置：source_name -> (模型类, 文件名模板列表)
# 文件名模板支持年份通配符 {year}，遍历 2020-2024 匹配；单文件直接给出文件名。
DATA_SOURCES: Dict[str, tuple] = {
    "third_survey_topsoil": (
        ThirdSurveyTopsoil,
        ["01_乐昌市土壤三普表层土点位数据_fake.xlsx"],
    ),
    "third_survey_profile": (
        ThirdSurveyProfile,
        ["乐昌市土壤三普剖面理化和基本数据_fake.xlsx"],
    ),
    "third_survey_site_condition": (
        ThirdSurveySiteCondition,
        ["乐昌市土壤三普立地条件_fake.xlsx"],
    ),
    "third_survey_bulk_density": (
        ThirdSurveyBulkDensity,
        ["乐昌市三普土壤容重_fake.xlsx"],
    ),
    "second_survey_point": (
        SecondSurveyPoint,
        ["01_乐昌市二普点数据.xlsx"],
    ),
    "formula_fertilization": (
        FormulaFertilization,
        ["乐昌市测土配方表层土数据2008_fake.xlsx"],
    ),
    "agri_chemicalization": (
        AgriChemicalization,
        ["各县(区)农村电气化和农业化学化情况{year}(1).xls"],
    ),
    "grain_yield": (
        GrainYield,
        ["各县(区)粮食作物播种面积和产量{year}(1).xls"],
    ),
}

FAKE_SOURCES = {"third_survey_topsoil", "third_survey_profile",
                 "third_survey_site_condition", "third_survey_bulk_density",
                 "formula_fertilization"}


def _read_excel(path: str) -> pd.DataFrame:
    """读取 Excel，按扩展名选择引擎。加密文件抛异常由调用方捕获。"""
    if path.lower().endswith(".xls"):
        return pd.read_excel(path, engine="xlrd")
    return pd.read_excel(path, engine="openpyxl")


def _resolve_files(patterns: List[str], data_dir: str) -> List[str]:
    """解析文件名模板。{year} 通配符展开为 2020-2024；无通配符原样返回存在的文件。"""
    resolved: List[str] = []
    for pat in patterns:
        if "{year}" in pat:
            for year in range(2020, 2025):
                p = os.path.join(data_dir, pat.format(year=year))
                if os.path.exists(p):
                    resolved.append(p)
        else:
            p = os.path.join(data_dir, pat)
            if os.path.exists(p):
                resolved.append(p)
    return resolved


def _prepare_dataframe(df: pd.DataFrame, column_map: Dict[str, str], model_class) -> pd.DataFrame:
    """strip 列名 -> rename -> datetime 转 ISO -> 仅保留模型字段列。"""
    # 1. 列名 strip（处理 " Ni" / "TK "）
    df = df.rename(columns={c: str(c).strip() for c in df.columns})
    # 2. 映射表 key 也 strip，构造实际 rename
    stripped_map = {str(k).strip(): v for k, v in column_map.items()}
    df = df.rename(columns=stripped_map)
    # 3. datetime 列转 ISO 字符串
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    # 4. 仅保留模型定义的字段，丢弃未映射列
    model_fields = {c.name for c in model_class.__table__.columns}
    keep = [c for c in df.columns if c in model_fields]
    return df[keep].copy()


def import_one_source(model_class, column_map: Dict[str, str], file_paths: List[str],
                      dry_run: bool = False) -> int:
    """对单数据源执行幂等导入，返回导入行数。加密/缺失文件返回 0。"""
    if not file_paths:
        logger.warning("未找到数据文件，跳过: %s", model_class.__tablename__)
        return 0

    frames: List[pd.DataFrame] = []
    for path in file_paths:
        try:
            raw = _read_excel(path)
        except Exception as e:  # noqa: BLE001
            if "encrypted" in str(e).lower():
                logger.warning("文件已加密，跳过: %s", path)
                continue
            logger.error("读取失败 %s: %s", path, e)
            continue
        frames.append(_prepare_dataframe(raw, column_map, model_class))

    if not frames:
        return 0

    df = pd.concat(frames, ignore_index=True)
    records = df.to_dict(orient="records")
    # 移除全为 None 的空记录键，避免主键冲突（id 由 DB 自增，剔除）
    for rec in records:
        rec.pop("id", None)

    if dry_run:
        logger.info("[dry-run] %s 将导入 %d 行（不写库）", model_class.__tablename__, len(records))
        return len(records)

    db.session.query(model_class).delete()
    if records:
        db.session.bulk_insert_mappings(model_class, records)
    db.session.commit()  # 每表独立 commit
    logger.info("导入完成: %s %d 行%s",
                model_class.__tablename__, len(records),
                "（脱敏 _fake 数据）" if model_class.__tablename__.startswith(("third_survey", "formula")) else "")
    return len(records)


def run_import(area: str = "lechang", data_dir: Optional[str] = None,
               dry_run: bool = False) -> Dict[str, int]:
    """遍历所有数据源执行导入，返回 {source_name: rows}。"""
    if data_dir is None:
        data_dir = str(PROJECT_ROOT / "data" / area)
    if not os.path.isdir(data_dir):
        logger.error("数据目录不存在: %s", data_dir)
        return {}

    results: Dict[str, int] = {}
    for source_name, (model_class, patterns) in DATA_SOURCES.items():
        files = _resolve_files(patterns, data_dir)
        results[source_name] = import_one_source(
            model_class, COLUMN_MAPS[source_name], files, dry_run=dry_run
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="乐昌土壤数据导入")
    parser.add_argument("--area", default="lechang", help="区域目录名（默认 lechang）")
    parser.add_argument("--dry-run", action="store_true", help="预览不写库")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = create_app()
    with app.app_context():
        results = run_import(area=args.area, dry_run=args.dry_run)

    print("=" * 60)
    print("导入结果汇总：")
    for name, rows in results.items():
        print(f"  {name}: {rows} 行")
    if args.dry_run:
        print("（dry-run 模式，未实际写库）")
    print("=" * 60)


if __name__ == "__main__":
    main()
