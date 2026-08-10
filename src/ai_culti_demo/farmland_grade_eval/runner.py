"""耕地质量等级评价 Python 调用层。

纯 Python 实现，替代原 Fortran exe + subprocess 调用。
通过直接调用 evaluation/obstacle 模块完成评价，数据源从 CSV 加载。
"""
import os
import dataclasses
from typing import Dict, Any, List

from .config import EvaluationConfig
from .models import Parcel
from .data_loader import load_parcels_from_csv
from .evaluation import evaluate_land_quality
from .obstacle import compute_obstacle_factors
from .potential import compute_single_parcel_potential, county_potential_statistics_data
from .statistics import county_statistics_data

MODEL_VERSION = "python_v1_20260801"
DEFAULT_CSV_PATH = "bin/farmland_quality_eval/Farmland_quality_Level_Database.csv"

# 数值型指标映射：(name, code, 取值函数)
_INDICATOR_MAP = [
    ("酸碱度", "SJD", lambda p: p.sjd),
    ("有机质含量", "YJZ", lambda p: p.yjz),
    ("有效磷含量", "YXL", lambda p: p.yxl),
    ("速效钾含量", "SXJ", lambda p: p.sxj),
    ("土壤容重", "TRRZ", lambda p: p.trrz),
    ("有效土层厚度", "YXTCHD", lambda p: p.yxtchd),
    ("耕层厚度", "GCHD", lambda p: p.gchd),
]

# 概念型指标映射：(name, code, names_list, parcel_field)
_CONCEPT_MAP = [
    ("耕层质地", "GCZD", "zdgc_names", "zdgc"),
    ("排水能力", "PSNL", "psnl_names", "psnl"),
    ("灌溉能力", "GGNL", "ggnl_names", "ggnl"),
    ("地形部位", "DXBW", "dxbw_names", "dxbw"),
    ("质地构型", "ZDGX", "zdgx_names", "zdgx"),
]


class FarmlandGradeRunner:
    """耕地质量等级评价 Python 模型调用包装器。

    签名向后兼容：exe_path 被忽略，dat_path 语义改为 csv_path。
    """

    _parcels_cache = None
    _csv_path_cached = None
    _csv_mtime_cached = None

    def __init__(self, exe_path: str = None, dat_path: str = None, timeout: int = 30):
        # dat_path 语义改为 csv_path；exe_path 忽略；timeout 保留但不使用
        self.csv_path = dat_path or DEFAULT_CSV_PATH
        self.exe_path = exe_path  # 忽略，仅保留属性
        self.timeout = timeout    # 保留，不再用于 subprocess

    def check_deployment(self) -> Dict[str, Any]:
        """检查 CSV 数据文件是否已部署。"""
        csv_exists = os.path.exists(self.csv_path) and os.path.getsize(self.csv_path) > 0
        return {
            "csv_exists": csv_exists,
            "csv_path": self.csv_path,
            "ready": csv_exists,
        }

    def _load_parcels(self) -> List[Parcel]:
        """加载 CSV 数据，带类级缓存 + mtime 校验。

        CSV 重新部署后 mtime 变化，自动失效重载。
        """
        mtime = os.path.getmtime(self.csv_path)
        if (FarmlandGradeRunner._parcels_cache is not None
                and FarmlandGradeRunner._csv_path_cached == self.csv_path
                and FarmlandGradeRunner._csv_mtime_cached == mtime):
            return FarmlandGradeRunner._parcels_cache
        parcels = load_parcels_from_csv(self.csv_path)
        FarmlandGradeRunner._parcels_cache = parcels
        FarmlandGradeRunner._csv_path_cached = self.csv_path
        FarmlandGradeRunner._csv_mtime_cached = mtime
        return parcels

    def run(self, parcel_code: str) -> Dict[str, Any]:
        """调用 Python 模型进行质量等级评价。"""
        deployment = self.check_deployment()
        if not deployment["ready"]:
            return {
                "status": "error",
                "error": {
                    "code": "DEPLOYMENT_ERROR",
                    "message": f"CSV 数据文件缺失: {self.csv_path}"
                }
            }

        try:
            parcels = self._load_parcels()
        except (FileNotFoundError, ValueError) as e:
            return {
                "status": "error",
                "error": {
                    "code": "DEPLOYMENT_ERROR",
                    "message": f"CSV 数据加载失败: {e}"
                }
            }

        parcel = next((p for p in parcels if p.tybh.strip() == parcel_code), None)
        if parcel is None:
            return {
                "status": "error",
                "error": {
                    "code": "PARCEL_NOT_FOUND",
                    "message": f"未找到地块代码: {parcel_code}"
                }
            }

        config = EvaluationConfig()
        try:
            result = evaluate_land_quality(config, parcel)
            obstacles = compute_obstacle_factors(config, parcel.ejnyq, result.y)
        except ValueError as e:
            return {
                "status": "error",
                "error": {
                    "code": "INVALID_ENCODING",
                    "message": str(e)
                }
            }

        return {
            "status": "ok",
            "parcel_code": parcel_code,
            "model_version": MODEL_VERSION,
            "parcel_info": self._build_parcel_info(parcel, config),
            "indicators": self._build_indicators(parcel, config),
            "composite_index": result.quality_index,
            "quality_grade": f"{result.grade}等",
            "obstacle_degree": self._build_obstacle_degree(obstacles),
        }

    def _build_parcel_info(self, parcel: Parcel, config: EvaluationConfig) -> dict:
        return {
            "地块代码": parcel.tybh,
            "经度": str(parcel.jd),
            "纬度": str(parcel.wd),
            "县区名称": config.xqmc_names[parcel.xqmc - 1].strip(),
            "二级农业区名称": config.ejnyq_names[parcel.ejnyq - 1].strip(),
        }

    def _build_indicators(self, parcel: Parcel, config: EvaluationConfig) -> list:
        indicators = []
        # 7 个数值型
        for name, code, fn in _INDICATOR_MAP:
            indicators.append({"name": name, "code": code, "raw_value": f"{fn(parcel):.3f}"})
        # 5 个概念型
        for name, code, names_attr, field in _CONCEPT_MAP:
            names = getattr(config, names_attr)
            idx = getattr(parcel, field)
            indicators.append({"name": name, "code": code, "raw_value": names[idx - 1].strip()})
        return indicators

    def _build_obstacle_degree(self, obstacles) -> list:
        return [
            {"rank": i + 1, "indicator": o.name.strip(), "degree": o.factor, "level": o.degree.strip()}
            for i, o in enumerate(obstacles)
        ]


def run_grade_evaluation(parcel_code: str, exe_path: str = None, dat_path: str = None) -> Dict[str, Any]:
    """便捷函数：调用 Python 模型进行质量等级评价。

    签名向后兼容：exe_path 被忽略，dat_path 语义改为 CSV 路径。
    """
    runner = FarmlandGradeRunner(exe_path, dat_path)
    return runner.run(parcel_code)


def run_potential_analysis(parcel_code: str, csv_path: str = None) -> Dict[str, Any]:
    """单地块潜力分析：模拟各指标改良后的潜在质量指数与等级提升。"""
    runner = FarmlandGradeRunner(dat_path=csv_path)
    deployment = runner.check_deployment()
    if not deployment["ready"]:
        return {"status": "error", "error": {"code": "DEPLOYMENT_ERROR",
                "message": f"CSV 数据文件缺失: {runner.csv_path}"}}

    try:
        parcels = runner._load_parcels()
    except (FileNotFoundError, ValueError) as e:
        return {"status": "error", "error": {"code": "DEPLOYMENT_ERROR",
                "message": f"CSV 数据加载失败: {e}"}}

    parcel = next((p for p in parcels if p.tybh.strip() == parcel_code), None)
    if parcel is None:
        return {"status": "error", "error": {"code": "PARCEL_NOT_FOUND",
                "message": f"未找到地块代码: {parcel_code}"}}

    config = EvaluationConfig()
    try:
        result = evaluate_land_quality(config, parcel)
        items, full_result = compute_single_parcel_potential(
            config, parcel, result.y, result.quality_index, result.grade)
    except ValueError as e:
        return {"status": "error", "error": {"code": "INVALID_ENCODING", "message": str(e)}}

    return {
        "status": "ok",
        "parcel_code": parcel_code,
        "original": {"quality_index": result.quality_index, "grade": result.grade},
        "full_potential": {"quality_index": full_result.quality_index, "grade": full_result.grade},
        "items": [dataclasses.asdict(item) for item in items],
    }


def run_county_statistics(xqmc_code: int, csv_path: str = None) -> Dict[str, Any]:
    """县域常规统计：等级分布、障碍度统计、首要障碍指标。"""
    runner = FarmlandGradeRunner(dat_path=csv_path)
    deployment = runner.check_deployment()
    if not deployment["ready"]:
        return {"status": "error", "error": {"code": "DEPLOYMENT_ERROR",
                "message": f"CSV 数据文件缺失: {runner.csv_path}"}}

    try:
        parcels = runner._load_parcels()
    except (FileNotFoundError, ValueError) as e:
        return {"status": "error", "error": {"code": "DEPLOYMENT_ERROR",
                "message": f"CSV 数据加载失败: {e}"}}

    config = EvaluationConfig()
    stats = county_statistics_data(config, parcels, xqmc_code)
    if stats is None:
        return {"status": "error", "error": {"code": "NO_DATA",
                "message": f"县区 {xqmc_code} 无地块数据"}}
    return {"status": "ok", "county_code": xqmc_code, "stats": dataclasses.asdict(stats)}


def run_county_potential(xqmc_code: int, scenario: int, csv_path: str = None) -> Dict[str, Any]:
    """县域潜力情景分析：scenario=1 理想潜力，scenario=2 最佳潜力。"""
    runner = FarmlandGradeRunner(dat_path=csv_path)
    deployment = runner.check_deployment()
    if not deployment["ready"]:
        return {"status": "error", "error": {"code": "DEPLOYMENT_ERROR",
                "message": f"CSV 数据文件缺失: {runner.csv_path}"}}

    try:
        parcels = runner._load_parcels()
    except (FileNotFoundError, ValueError) as e:
        return {"status": "error", "error": {"code": "DEPLOYMENT_ERROR",
                "message": f"CSV 数据加载失败: {e}"}}

    config = EvaluationConfig()
    result = county_potential_statistics_data(config, parcels, xqmc_code, scenario)
    if result is None:
        return {"status": "error", "error": {"code": "NO_DATA",
                "message": f"县区 {xqmc_code} 无地块数据"}}
    return {"status": "ok", "county_code": xqmc_code, "scenario": scenario,
            "result": dataclasses.asdict(result)}
