---
change: replace-grade-eval-with-python-model
design-doc: docs/superpowers/specs/2026-08-01-replace-grade-eval-with-python-model-design.md
base-ref: 140230f6a23fd10d0877e6f24bb645f89b4254d5
---

# 耕地质量等级评价 Python 模型替换实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 model-7（耕地质量等级评价）从 Fortran exe + .dat 二进制依赖改为纯 Python 实现，移植 model2 完整系统（核心评价 + 潜力分析 + 县域统计 + 调理剂库函数），保持 `run_grade_evaluation` 签名向后兼容。

**Architecture:** 将 model2 的 8 个模块移植到 `src/ai_culti_demo/farmland_grade_eval/` 包内，统一改为包内相对导入；重写 `runner.py` 为 Python 直接调用层（去除 subprocess），保持对外契约一致；HTTP `/api/v1/data/import` 的 `data_type=dat` 分支改为接受 CSV 文件；数据源从二进制 .dat 改为 CSV（入库）。

**Tech Stack:** Python 3.12 标准库（csv / math / typing / dataclasses / os），Flask（HTTP 路由），pytest（测试）

## Global Constraints

- `MODEL_VERSION` SHALL 为 `python_v1_20260801`（设计文档 2.2 节）
- `run_grade_evaluation(parcel_code, exe_path=None, dat_path=None)` 签名 SHALL 保持不变，`dat_path` 语义改为 CSV 路径，`exe_path` 被忽略（spec: 向后兼容的 API 签名）
- 默认 CSV 路径 SHALL 为 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`（设计文档 2.2 节）
- A0001 回归容差 SHALL < 0.01（composite_index=0.6728、quality_grade="10等"）（spec: 数值等价性）
- 20 个必需 CSV 字段名（以首行表头为准）：`SiteID, JD, WD, MJ, SJD, YJZ, YXL, SXJ, TRRZ, YXTCHD, GCHD, JHXLLZ, JHXQLZ, EJNYQcode, XQMCcode, GCZDcode, PSNLcode, GGNLcode, DXBWcode, ZDGXcode`（spec: 耕地质量评价 CSV 数据校验）
- CSV 文件大小限制 SHALL > 0 且 ≤ 200MB，编码 SHALL 为 UTF-8（带或不带 BOM）（spec: 耕地质量评价 CSV 数据校验）
- conditioner 库函数 SHALL NOT 通过 HTTP API 暴露（spec: 调理剂库函数）
- 无新增第三方依赖（model2 仅用 Python 标准库）

## File Structure

### 新建文件

| 文件路径 | 职责 |
|---------|------|
| `src/ai_culti_demo/farmland_grade_eval/models.py` | 数据类：Parcel, QualityResult, ObstacleItem, PotentialItem, CountyStats, CountyPotentialResult |
| `src/ai_culti_demo/farmland_grade_eval/config.py` | EvaluationConfig：隶属函数参数、概念型隶属度、权重、等级阈值、名称字典 |
| `src/ai_culti_demo/farmland_grade_eval/data_loader.py` | load_parcels_from_csv：UTF-8-sig CSV → List[Parcel] |
| `src/ai_culti_demo/farmland_grade_eval/evaluation.py` | membership_numeric + evaluate_land_quality：隶属函数 + 综合指数 + 等级评定 |
| `src/ai_culti_demo/farmland_grade_eval/obstacle.py` | calc_limiting_factors + compute_obstacle_factors：障碍度因子计算与分级 |
| `src/ai_culti_demo/farmland_grade_eval/potential.py` | compute_single_parcel_potential + county_potential_statistics_data：潜力分析 |
| `src/ai_culti_demo/farmland_grade_eval/statistics.py` | county_statistics_data：县域常规统计 |
| `src/ai_culti_demo/farmland_grade_eval/conditioner.py` | calculate_soil_conditioner：调理剂库函数（不接 API） |
| `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv` | 1193 地块 CSV 数据文件（入库） |

### 修改文件

| 文件路径 | 改动内容 |
|---------|---------|
| `src/ai_culti_demo/farmland_grade_eval/runner.py` | 重写为 Python 调用层（去除 subprocess/parse_output） |
| `src/ai_culti_demo/farmland_grade_eval/__init__.py` | 导出新增对外函数 |
| `framework/agents/specialized/grade_agent.py` | docstring 从"Fortran exe"改为"Python 实现" |
| `src/ai_culti_demo/thematic_models.py` | reliability.message 从"Fortran exe"改为"Python 实现" |
| `framework/core_engine/adapter.py` | check_grade_eval_deployment 返回字段从 exe/dat 改为 csv |
| `framework/upload/data_validator.py` | validate_dat → validate_grade_csv（CSV 校验） |
| `framework/upload/data_deployer.py` | deploy_dat → deploy_grade_csv（部署为 .csv） |
| `framework/upload/data_trigger.py` | trigger_dat_check → trigger_grade_csv_check |
| `framework/api/routes/data_import.py` | data_type=dat 分支改用 CSV 校验/部署/触发 |
| `.gitignore` | 允许 CSV 入库，保持 exe/.dat 排除 |
| `bin/farmland_quality_eval/README.md` | 部署说明从 exe/.dat 改为 CSV |
| `tests/test_farmland_grade_eval.py` | 删除 parse_output 测试，新增 Python 评价逻辑测试 + 回归测试 |
| `tests/test_data_trigger.py` | 更新 trigger 函数名和测试 |
| `README.md` | model-7 架构说明从 exe 改为 Python |
| `docs/api.md` | data/import 接口 data_type=dat → CSV 说明 |
| `docs/openapi.json` | 版本号递增、data/import 字段更新 |

### 删除文件

| 文件路径 | 原因 |
|---------|------|
| `bin/farmland_quality_eval/Farmland_quality_evaluation.exe` | Fortran exe 不再需要 |
| `bin/farmland_quality_eval/Farmlands_Quality_Level_Database.dat` | 二进制 .dat 被 CSV 替换 |

---

## Task 1: 移植数据层模块（models.py + config.py + data_loader.py）

**Files:**
- Create: `src/ai_culti_demo/farmland_grade_eval/models.py`
- Create: `src/ai_culti_demo/farmland_grade_eval/config.py`
- Create: `src/ai_culti_demo/farmland_grade_eval/data_loader.py`
- Test: `tests/test_farmland_grade_eval.py`（新建，本任务写入数据层测试）

**Interfaces:**
- Consumes: 无（基础层，无外部依赖）
- Produces:
  - `models.Parcel`（20 字段 dataclass）、`models.QualityResult`、`models.ObstacleItem`、`models.PotentialItem`、`models.CountyStats`、`models.CountyPotentialResult`
  - `config.EvaluationConfig`（含 a/c/ut1/ut2 矩阵、mem_* 隶属度、weights、limits、*_names 字典）
  - `data_loader.load_parcels_from_csv(filename: str) -> List[Parcel]`

**model2 源码位置:** `D:\destkop\模型\模型2\models.py`、`config.py`、`data_loader.py`

- [x] **Step 1: 编写数据层失败测试**

在 `tests/test_farmland_grade_eval.py` 写入以下内容（替换原有 parse_output 测试文件）：

```python
"""farmland_grade_eval Python 模型单元测试。

覆盖数据层（models/config/data_loader）、评价层（evaluation/obstacle）、
runner 集成、潜力分析、县域统计、conditioner 库函数、部署校验、向后兼容。
"""
import sys
import os
import tempfile
from pathlib import Path

import pytest

# 将 src 加入 sys.path 以便导入 ai_culti_demo 包
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ========== 数据层测试 ==========

class TestModels:
    """数据类实例化测试。"""

    def test_parcel_dataclass_has_20_fields(self):
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        parcel = Parcel(
            tybh="A0001", jd=112.97, wd=25.32, mj=100.0,
            sjd=4.6, yjz=16.2, yxl=66.9, sxj=51.7, trrz=1.24,
            yxtchd=120.0, gchd=17.0, jhxllz=0.0, jhxqlz=0.0,
            ejnyq=1, xqmc=8, zdgc=6, psnl=3, ggnl=2, dxbw=6, zdgx=5,
        )
        assert parcel.tybh == "A0001"
        assert parcel.sjd == 4.6
        assert parcel.ejnyq == 1

    def test_quality_result_dataclass(self):
        from ai_culti_demo.farmland_grade_eval.models import QualityResult
        r = QualityResult(y=[0.5] * 12, quality_index=0.7, grade=8)
        assert len(r.y) == 12
        assert r.quality_index == 0.7
        assert r.grade == 8


class TestEvaluationConfig:
    """配置类参数完整性测试。"""

    def test_config_has_all_parameters(self):
        from ai_culti_demo.farmland_grade_eval.config import EvaluationConfig
        cfg = EvaluationConfig()
        assert cfg.max_ejnyq == 4
        assert len(cfg.a) == 4  # 4 个二级农业区
        assert len(cfg.c) == 4
        assert len(cfg.weights) == 4
        assert len(cfg.weights[0]) == 12  # 12 个指标权重
        assert len(cfg.limits) == 4
        assert len(cfg.limits[0]) == 9  # 9 个等级阈值
        assert len(cfg.zdgc_names) == 12
        assert len(cfg.psnl_names) == 4
        assert len(cfg.ggnl_names) == 4
        assert len(cfg.dxbw_names) == 11
        assert len(cfg.zdgx_names) == 7
        assert len(cfg.ejnyq_names) == 4
        assert len(cfg.xqmc_names) == 10
        assert len(cfg.indicator_names) == 12


class TestDataLoader:
    """CSV 数据加载器测试。"""

    @pytest.fixture
    def sample_csv(self, tmp_path):
        """创建包含 2 行测试数据的 CSV 文件。"""
        csv_content = (
            "SiteID,JD,WD,MJ,SJD,YJZ,YXL,SXJ,TRRZ,YXTCHD,GCHD,"
            "JHXLLZ,JHXQLZ,EJNYQcode,XQMCcode,GCZDcode,PSNLcode,"
            "GGNLcode,DXBWcode,ZDGXcode\n"
            "A0001,112.973801,25.324301,100.0,4.600,16.200,66.900,51.700,"
            "1.240,120.000,17.000,0.0,0.0,1,8,6,3,2,6,5\n"
            "A0002,113.0,25.3,80.0,5.5,25.0,30.0,100.0,1.35,60.0,20.0,"
            "0.0,0.0,1,8,3,1,1,1,2\n"
        )
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(csv_content, encoding="utf-8-sig")
        return str(csv_path)

    def test_load_parcels_returns_list(self, sample_csv):
        from ai_culti_demo.farmland_grade_eval.data_loader import load_parcels_from_csv
        parcels = load_parcels_from_csv(sample_csv)
        assert len(parcels) == 2

    def test_load_parcels_first_row_fields(self, sample_csv):
        from ai_culti_demo.farmland_grade_eval.data_loader import load_parcels_from_csv
        parcels = load_parcels_from_csv(sample_csv)
        p = parcels[0]
        assert p.tybh == "A0001"
        assert p.sjd == 4.600
        assert p.ejnyq == 1
        assert p.xqmc == 8
        assert p.zdgc == 6

    def test_load_parcels_skips_insufficient_fields(self, tmp_path):
        """字段不足的行应被跳过（打印警告），不中断加载。"""
        csv_content = (
            "SiteID,JD,WD,MJ,SJD,YJZ,YXL,SXJ,TRRZ,YXTCHD,GCHD,"
            "JHXQLZ,EJNYQcode,XQMCcode,GCZDcode,PSNLcode,"
            "GGNLcode,DXBWcode,ZDGXcode\n"
            "A0001,112.97,25.32,100.0,4.6,16.2,66.9,51.7,1.24,120.0,17.0,"
            "0.0,1,8,6,3,2,6,5\n"
        )
        csv_path = tmp_path / "short.csv"
        csv_path.write_text(csv_content, encoding="utf-8-sig")
        from ai_culti_demo.farmland_grade_eval.data_loader import load_parcels_from_csv
        parcels = load_parcels_from_csv(str(csv_path))
        assert len(parcels) == 0  # 19 列 < 20，跳过

    def test_load_parcels_missing_file_raises(self, tmp_path):
        from ai_culti_demo.farmland_grade_eval.data_loader import load_parcels_from_csv
        with pytest.raises(FileNotFoundError):
            load_parcels_from_csv(str(tmp_path / "nonexistent.csv"))
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_farmland_grade_eval.py::TestModels::test_parcel_dataclass_has_20_fields tests/test_farmland_grade_eval.py::TestEvaluationConfig::test_config_has_all_parameters tests/test_farmland_grade_eval.py::TestDataLoader -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_culti_demo.farmland_grade_eval.models'`

- [x] **Step 3: 移植 models.py**

创建 `src/ai_culti_demo/farmland_grade_eval/models.py`，从 `D:\destkop\模型\模型2\models.py` 复制全部内容（6 个 dataclass），无导入修正需要（原文件仅用 `dataclasses` 和 `typing` 标准库）：

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class Parcel:
    tybh: str
    jd: float
    wd: float
    mj: float
    sjd: float
    yjz: float
    yxl: float
    sxj: float
    trrz: float
    yxtchd: float
    gchd: float
    jhxllz: float
    jhxqlz: float
    ejnyq: int
    xqmc: int
    zdgc: int
    psnl: int
    ggnl: int
    dxbw: int
    zdgx: int

@dataclass
class QualityResult:
    y: List[float]
    quality_index: float
    grade: int

@dataclass
class ObstacleItem:
    name: str
    factor: float
    degree: str

@dataclass
class PotentialItem:
    indicator_name: str
    original_value: str
    potential_value: str
    original_quality_index: float
    potential_quality_index: float
    original_grade: int
    potential_grade: int

@dataclass
class CountyStats:
    county_name: str
    parcel_count: int
    total_area: float
    avg_grade: float
    avg_ind: List[float]
    min_ind: List[float]
    max_ind: List[float]
    avg_lim_factors: List[float]
    sorted_avg_factors: List[float]
    sorted_names: List[str]
    cnt_grade: List[int]
    mj_grade: List[float]
    cnt_primary: List[int]
    mj_primary: List[float]

@dataclass
class CountyPotentialResult:
    scenario: int
    county_name: str
    parcel_count: int
    total_area: float
    avg_grade_pot: float
    avg_ind_pot: List[float]
    min_ind_pot: List[float]
    max_ind_pot: List[float]
    avg_lim_pot: List[float]
    sorted_avg_pot: List[float]
    sorted_names_pot: List[str]
    cnt_grade_pot: List[int]
    mj_grade_pot: List[float]
    cnt_primary_pot: List[int]
    mj_primary_pot: List[float]
    avg_grade_orig: float
    avg_ind_orig: List[float]
    avg_contrib_orig: List[float]
    avg_contrib_pot: List[float]
    cnt_grade_orig: List[int]
    mj_grade_orig: List[float]
```

- [x] **Step 4: 移植 config.py**

创建 `src/ai_culti_demo/farmland_grade_eval/config.py`，从 `D:\destkop\模型\模型2\config.py` 复制全部内容（EvaluationConfig 类），无导入修正需要：

```python
"""评估配置参数（不可变风格，但允许一次性初始化）。"""

class EvaluationConfig:
    def __init__(self):
        self.max_ejnyq = 4
        self.n_indicators = 12
        self.n_numeric = 7

        # 数值指标参数
        self.a = [
            [0.221129, 0.002163, 0.003800, 0.000068, 2.786523, 0.000230, 0.019247],
            [0.221129, 0.002163, 0.003800, 0.000068, 2.786523, 0.000230, 0.019247],
            [0.221129, 0.002163, 0.003800, 0.000068, 2.786523, 0.000230, 0.019247],
            [0.221129, 0.001842, 0.002025, 0.000081, 2.236726, 0.000205, 0.019247],
        ]
        self.c = [
            [6.70, 38.0, 40.0, 205.0, 1.35, 100.0, 20.2],
            [6.70, 38.0, 40.0, 205.0, 1.35, 100.0, 20.2],
            [6.70, 38.0, 40.0, 205.0, 1.35, 100.0, 20.2],
            [6.811204, 33.656446, 33.346824, 181.622535, 1.211674, 99.092342, 20.2],
        ]
        self.ut1 = [
            [4.0, 6.0, 5.0, 30.0, 0.90, 10.0, 5.0],
            [4.0, 6.0, 5.0, 30.0, 0.90, 10.0, 5.0],
            [4.0, 6.0, 5.0, 30.0, 0.90, 10.0, 5.0],
            [3.0, 0.0, 0.0, 0.0, 0.50, 10.0, 5.0],
        ]
        self.ut2 = [
            [9.5, 38.0, 40.0, 205.0, 2.10, 100.0, 20.2],
            [9.5, 38.0, 40.0, 205.0, 2.10, 100.0, 20.2],
            [9.5, 38.0, 40.0, 205.0, 2.10, 100.0, 20.2],
            [10.0, 33.7, 33.3, 192.0, 3.21, 99.9, 20.0],
        ]
        # 概念型隶属度
        self.mem_zdgc = [
            [0.40, 0.75, 1.00, 0.95, 0.85, 0.80, 0.90, 0.60, 0.40, 0.65, 0.55, 0.50],
            [0.40, 0.75, 1.00, 0.95, 0.85, 0.80, 0.90, 0.60, 0.40, 0.65, 0.55, 0.50],
            [0.40, 0.75, 1.00, 0.95, 0.85, 0.80, 0.90, 0.60, 0.40, 0.65, 0.55, 0.50],
            [0.40, 0.75, 1.00, 0.95, 0.85, 0.80, 0.90, 0.60, 0.40, 0.65, 0.55, 0.50],
        ]
        self.mem_psnl = [
            [1.0, 0.8, 0.6, 0.3],
            [1.0, 0.8, 0.6, 0.3],
            [1.0, 0.8, 0.6, 0.3],
            [1.0, 0.8, 0.6, 0.3],
        ]
        self.mem_ggnl = [
            [1.0, 0.8, 0.6, 0.3],
            [1.0, 0.8, 0.6, 0.3],
            [1.0, 0.8, 0.6, 0.3],
            [1.0, 0.8, 0.6, 0.3],
        ]
        self.mem_dxbw = [
            [1.0, 0.9, 0.8, 0.9, 0.7, 0.6, 0.5, 0.4, 0.5, 0.3, 0.2],
            [1.0, 0.9, 0.8, 0.9, 0.7, 0.6, 0.5, 0.4, 0.5, 0.3, 0.2],
            [1.0, 0.9, 0.8, 0.9, 0.7, 0.6, 0.5, 0.4, 0.5, 0.3, 0.2],
            [1.0, 0.95, 0.9, 0.95, 0.8, 0.8, 0.6, 0.7, 0.68, 0.45, 0.3],
        ]
        self.mem_zdgx = [
            [1.0, 0.8, 0.7, 0.5, 0.4, 0.3, 0.2],
            [1.0, 0.8, 0.7, 0.5, 0.4, 0.3, 0.2],
            [1.0, 0.8, 0.7, 0.5, 0.4, 0.3, 0.2],
            [1.0, 0.95, 0.85, 0.75, 0.4, 0.55, 0.3],
        ]
        # 权重
        self.weights = [
            [0.0668, 0.0958, 0.0574, 0.0736, 0.0596, 0.0716, 0.0585,
             0.0827, 0.1057, 0.1253, 0.1240, 0.0790],
            [0.0668, 0.0958, 0.0574, 0.0736, 0.0596, 0.0716, 0.0585,
             0.0827, 0.1057, 0.1253, 0.1240, 0.0790],
            [0.0668, 0.0958, 0.0574, 0.0736, 0.0596, 0.0716, 0.0585,
             0.0827, 0.1057, 0.1253, 0.1240, 0.0790],
            [0.0704, 0.1046, 0.0557, 0.0681, 0.0494, 0.0579, 0.0594,
             0.0905, 0.1070, 0.1369, 0.1270, 0.0731],
        ]
        # 等级阈值
        self.limits = [
            [0.8850, 0.8619, 0.8388, 0.8157, 0.7926, 0.7695, 0.7464, 0.7233, 0.7002],
            [0.8850, 0.8619, 0.8388, 0.8157, 0.7926, 0.7695, 0.7464, 0.7233, 0.7002],
            [0.8850, 0.8619, 0.8388, 0.8157, 0.7926, 0.7695, 0.7464, 0.7233, 0.7002],
            [0.9170, 0.8924, 0.8678, 0.8431, 0.8185, 0.7939, 0.7693, 0.7446, 0.7200],
        ]
        # 名称
        self.ejnyq_names = [
            '闽南粤中农林水产区', '粤西桂南农林区  ', '琼雷及南海诸岛农林区', '南岭丘陵山地林农区'
        ]
        self.xqmc_names = [
            '乐昌市', '乳源瑶族自治县', '仁化县', '南雄市', '始兴县',
            '新丰县', '曲江区', '武江区', '浈江区', '翁源县'
        ]
        self.zdgc_names = [
            '砂土及壤质砂土', '砂质壤土    ', '壤土        ', '粉（砂）质壤土  ',
            '砂质黏壤土  ', '黏壤土      ', '粉（砂）质黏壤土', '砂质黏土    ',
            '壤质粘土    ', '粉（砂）质黏土  ', '黏土        ', '重黏土      '
        ]
        self.psnl_names = ['充分满足', '满足    ', '基本满足', '不满足  ']
        self.ggnl_names = ['充分满足', '满足    ', '基本满足', '不满足  ']
        self.dxbw_names = [
            '平原低阶', '平原中阶', '平原高阶', '宽谷盆地', '山间盆地',
            '丘陵下部', '丘陵中部', '丘陵上部', '山地坡下', '山地坡中', '山地坡上'
        ]
        self.zdgx_names = [
            '上松下紧型', '海绵型    ', '夹层型    ', '紧实型    ',
            '上紧下松型', '薄层型    ', '松散型    '
        ]

        # 指标名称（用于显示）
        self.indicator_names = [
            '酸碱度   ', '有机质   ', '有效磷   ', '速效钾   ',
            '土壤容重  ', '有效土层厚度', '耕层厚度  ', '质地构成  ',
            '排水能力  ', '灌溉能力  ', '地形部位  ', '质地构型  '
        ]
```

- [x] **Step 5: 移植 data_loader.py（修正导入 + 错误处理）**

创建 `src/ai_culti_demo/farmland_grade_eval/data_loader.py`。相比 model2 原文件的改动：`from models import Parcel` → `from .models import Parcel`；`raise SystemExit(1)` → `raise FileNotFoundError` / `raise ValueError`（库函数不应调用 SystemExit）：

```python
import csv
from typing import List
from .models import Parcel

def load_parcels_from_csv(filename: str) -> List[Parcel]:
    """从 UTF-8-sig CSV 文件加载地块数据。

    Args:
        filename: CSV 文件路径，首行为表头，后续每行 20 字段。

    Returns:
        Parcel 列表。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 行解析失败（字段值类型转换错误）。
    """
    parcels = []
    with open(filename, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader)  # 标题行
        for lineno, row in enumerate(reader, start=2):
            if not row or len(row) < 20:
                print(f'警告：第 {lineno} 行字段不足，已跳过。')
                continue
            try:
                parcel = Parcel(
                    tybh=row[0],
                    jd=float(row[1]), wd=float(row[2]), mj=float(row[3]),
                    sjd=float(row[4]), yjz=float(row[5]), yxl=float(row[6]),
                    sxj=float(row[7]), trrz=float(row[8]), yxtchd=float(row[9]),
                    gchd=float(row[10]), jhxllz=float(row[11]), jhxqlz=float(row[12]),
                    ejnyq=int(row[13]), xqmc=int(row[14]),
                    zdgc=int(row[15]), psnl=int(row[16]), ggnl=int(row[17]),
                    dxbw=int(row[18]), zdgx=int(row[19])
                )
                parcels.append(parcel)
            except (ValueError, IndexError) as e:
                raise ValueError(f'第 {lineno} 行解析失败: {e}') from e
    return parcels
```

- [x] **Step 6: 运行测试验证通过**

Run: `python -m pytest tests/test_farmland_grade_eval.py::TestModels tests/test_farmland_grade_eval.py::TestEvaluationConfig tests/test_farmland_grade_eval.py::TestDataLoader -v`
Expected: PASS（全部 6 个测试通过）

- [x] **Step 7: 提交**

```bash
git add src/ai_culti_demo/farmland_grade_eval/models.py src/ai_culti_demo/farmland_grade_eval/config.py src/ai_culti_demo/farmland_grade_eval/data_loader.py tests/test_farmland_grade_eval.py
git commit -m "feat(grade-eval): 移植 model2 数据层模块（models/config/data_loader）"
```

---

## Task 2: 移植核心评价模块（evaluation.py + obstacle.py）

**Files:**
- Create: `src/ai_culti_demo/farmland_grade_eval/evaluation.py`
- Create: `src/ai_culti_demo/farmland_grade_eval/obstacle.py`
- Test: `tests/test_farmland_grade_eval.py`（追加评价层测试类）

**Interfaces:**
- Consumes: `config.EvaluationConfig`、`models.Parcel`、`models.QualityResult`、`models.ObstacleItem`（来自 Task 1）
- Produces:
  - `evaluation.membership_numeric(config: EvaluationConfig, u: float, idx: int, ejnyq: int) -> float`
  - `evaluation.evaluate_land_quality(config: EvaluationConfig, parcel: Parcel) -> QualityResult`（QualityResult.y 为 12 元素列表，quality_index 为浮点，grade 为 1-10 整数；ejnyq/编码越界时 raise ValueError）
  - `obstacle.calc_limiting_factors(config: EvaluationConfig, ejnyq: int, y: List[float]) -> List[float]`
  - `obstacle.compute_obstacle_factors(config: EvaluationConfig, ejnyq: int, y: List[float]) -> List[ObstacleItem]`（按 factor 降序排序）

**model2 源码位置:** `D:\destkop\模型\模型2\evaluation.py`、`obstacle.py`

- [x] **Step 1: 编写评价层失败测试**

在 `tests/test_farmland_grade_eval.py` 末尾追加：

```python
# ========== 评价层测试 ==========

class TestEvaluation:
    """核心评价函数测试。"""

    @pytest.fixture
    def config(self):
        from ai_culti_demo.farmland_grade_eval.config import EvaluationConfig
        return EvaluationConfig()

    @pytest.fixture
    def parcel_a0001(self):
        """A0001 地块数据（与 exe 历史输出对应的已知值）。"""
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        return Parcel(
            tybh="A0001", jd=112.973801, wd=25.324301, mj=100.0,
            sjd=4.600, yjz=16.200, yxl=66.900, sxj=51.700, trrz=1.240,
            yxtchd=120.000, gchd=17.000, jhxllz=0.0, jhxqlz=0.0,
            ejnyq=1, xqmc=8, zdgc=6, psnl=3, ggnl=2, dxbw=6, zdgx=5,
        )

    def test_a0001_composite_index_matches_exe(self, config, parcel_a0001):
        """A0001 综合指数与 exe 历史输出 0.6728 一致（容差 < 0.01）。"""
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        result = evaluate_land_quality(config, parcel_a0001)
        assert abs(result.quality_index - 0.6728) < 0.01

    def test_a0001_grade_is_10(self, config, parcel_a0001):
        """A0001 质量等级为 10 等。"""
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        result = evaluate_land_quality(config, parcel_a0001)
        assert result.grade == 10

    def test_a0001_has_12_membership_values(self, config, parcel_a0001):
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        result = evaluate_land_quality(config, parcel_a0001)
        assert len(result.y) == 12

    def test_invalid_ejnyq_raises_value_error(self, config):
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        parcel = Parcel(
            tybh="X", jd=0, wd=0, mj=0, sjd=5.0, yjz=20, yxl=30, sxj=100,
            trrz=1.35, yxtchd=60, gchd=20, jhxllz=0, jhxqlz=0,
            ejnyq=99, xqmc=1, zdgc=3, psnl=1, ggnl=1, dxbw=1, zdgx=1,
        )
        with pytest.raises(ValueError, match="无效的二级农业区代码"):
            evaluate_land_quality(config, parcel)

    def test_invalid_zdgc_raises_value_error(self, config):
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        parcel = Parcel(
            tybh="X", jd=0, wd=0, mj=0, sjd=5.0, yjz=20, yxl=30, sxj=100,
            trrz=1.35, yxtchd=60, gchd=20, jhxllz=0, jhxqlz=0,
            ejnyq=1, xqmc=1, zdgc=99, psnl=1, ggnl=1, dxbw=1, zdgx=1,
        )
        with pytest.raises(ValueError, match="ZDGC 编码超出范围"):
            evaluate_land_quality(config, parcel)


class TestObstacle:
    """障碍度计算测试。"""

    @pytest.fixture
    def config(self):
        from ai_culti_demo.farmland_grade_eval.config import EvaluationConfig
        return EvaluationConfig()

    def test_a0001_obstacle_factors_sorted_descending(self, config):
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        from ai_culti_demo.farmland_grade_eval.obstacle import compute_obstacle_factors
        parcel = Parcel(
            tybh="A0001", jd=112.973801, wd=25.324301, mj=100.0,
            sjd=4.600, yjz=16.200, yxl=66.900, sxj=51.700, trrz=1.240,
            yxtchd=120.000, gchd=17.000, jhxllz=0.0, jhxqlz=0.0,
            ejnyq=1, xqmc=8, zdgc=6, psnl=3, ggnl=2, dxbw=6, zdgx=5,
        )
        result = evaluate_land_quality(config, parcel)
        obstacles = compute_obstacle_factors(config, parcel.ejnyq, result.y)
        assert len(obstacles) == 12
        factors = [o.factor for o in obstacles]
        assert factors == sorted(factors, reverse=True)

    def test_a0001_top_obstacle_is_zdgx(self, config):
        """A0001 首要障碍因子为质地构型（与 exe 历史输出一致）。"""
        from ai_culti_demo.farmland_grade_eval.models import Parcel
        from ai_culti_demo.farmland_grade_eval.evaluation import evaluate_land_quality
        from ai_culti_demo.farmland_grade_eval.obstacle import compute_obstacle_factors
        parcel = Parcel(
            tybh="A0001", jd=112.973801, wd=25.324301, mj=100.0,
            sjd=4.600, yjz=16.200, yxl=66.900, sxj=51.700, trrz=1.240,
            yxtchd=120.000, gchd=17.000, jhxllz=0.0, jhxqlz=0.0,
            ejnyq=1, xqmc=8, zdgc=6, psnl=3, ggnl=2, dxbw=6, zdgx=5,
        )
        result = evaluate_land_quality(config, parcel)
        obstacles = compute_obstacle_factors(config, parcel.ejnyq, result.y)
        assert obstacles[0].name.strip() == "质地构型"
        assert abs(obstacles[0].factor - 0.169) < 0.01
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_farmland_grade_eval.py::TestEvaluation tests/test_farmland_grade_eval.py::TestObstacle -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_culti_demo.farmland_grade_eval.evaluation'`

- [x] **Step 3: 移植 evaluation.py（修正导入）**

创建 `src/ai_culti_demo/farmland_grade_eval/evaluation.py`。相比 model2 原文件：`from config import` → `from .config import`，`from models import` → `from .models import`：

```python
"""核心评价函数"""
from typing import List
from .config import EvaluationConfig
from .models import Parcel, QualityResult

def membership_numeric(config: EvaluationConfig, u: float, idx: int, ejnyq: int) -> float:
    j = idx - 1
    pa = config.a[ejnyq-1][j]
    pc = config.c[ejnyq-1][j]
    u1 = config.ut1[ejnyq-1][j]
    u2 = config.ut2[ejnyq-1][j]

    if idx in (1, 5):  # 峰型
        if u <= u1 or u >= u2:
            return 0.0
        return 1.0 / (1.0 + pa * (u - pc)**2)
    else:  # 戒上型
        if u <= u1:
            return 0.0
        if u < pc:
            return 1.0 / (1.0 + pa * (u - pc)**2)
        return 1.0

def evaluate_land_quality(config: EvaluationConfig, parcel: Parcel) -> QualityResult:
    ejnyq = parcel.ejnyq
    if ejnyq < 1 or ejnyq > config.max_ejnyq:
        raise ValueError(f"无效的二级农业区代码 {ejnyq}")

    y = [0.0] * 12
    y[0] = membership_numeric(config, parcel.sjd, 1, ejnyq)
    y[1] = membership_numeric(config, parcel.yjz, 2, ejnyq)
    y[2] = membership_numeric(config, parcel.yxl, 3, ejnyq)
    y[3] = membership_numeric(config, parcel.sxj, 4, ejnyq)
    y[4] = membership_numeric(config, parcel.trrz, 5, ejnyq)
    y[5] = membership_numeric(config, parcel.yxtchd, 6, ejnyq)
    y[6] = membership_numeric(config, parcel.gchd, 7, ejnyq)

    if not (1 <= parcel.zdgc <= 12):
        raise ValueError("ZDGC 编码超出范围")
    if not (1 <= parcel.psnl <= 4):
        raise ValueError("PSNL 编码超出范围")
    if not (1 <= parcel.ggnl <= 4):
        raise ValueError("GGNL 编码超出范围")
    if not (1 <= parcel.dxbw <= 11):
        raise ValueError("DXBW 编码超出范围")
    if not (1 <= parcel.zdgx <= 7):
        raise ValueError("ZDGX 编码超出范围")

    y[7]  = config.mem_zdgc[ejnyq-1][parcel.zdgc-1]
    y[8]  = config.mem_psnl[ejnyq-1][parcel.psnl-1]
    y[9]  = config.mem_ggnl[ejnyq-1][parcel.ggnl-1]
    y[10] = config.mem_dxbw[ejnyq-1][parcel.dxbw-1]
    y[11] = config.mem_zdgx[ejnyq-1][parcel.zdgx-1]

    qi = sum(y[i] * config.weights[ejnyq-1][i] for i in range(12))

    grade = 10
    for i in range(9):
        if qi >= config.limits[ejnyq-1][i]:
            grade = i + 1
            break
    return QualityResult(y=y, quality_index=qi, grade=grade)
```

- [x] **Step 4: 移植 obstacle.py（修正导入）**

创建 `src/ai_culti_demo/farmland_grade_eval/obstacle.py`。相比 model2 原文件：`from config import` → `from .config import`，`from models import` → `from .models import`：

```python
"""障碍度计算"""
from typing import List
from .config import EvaluationConfig
from .models import ObstacleItem

def calc_limiting_factors(config: EvaluationConfig, ejnyq: int, y: List[float]) -> List[float]:
    d = [1.0 - v for v in y]
    df = [d[i] * config.weights[ejnyq-1][i] for i in range(12)]
    total = sum(df)
    if total != 0.0:
        return [v / total for v in df]
    return [0.0] * 12

def compute_obstacle_factors(config: EvaluationConfig, ejnyq: int, y: List[float]) -> List[ObstacleItem]:
    lf = calc_limiting_factors(config, ejnyq, y)
    items = []
    for i, v in enumerate(lf):
        if v <= 0.0:
            degree = '无障碍    '
        elif v <= 0.1:
            degree = '轻度障碍  '
        elif v <= 0.2:
            degree = '中度障碍  '
        else:
            degree = '重度障碍  '
        items.append(ObstacleItem(config.indicator_names[i], v, degree))
    items.sort(key=lambda x: x.factor, reverse=True)
    return items
```

- [x] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_farmland_grade_eval.py::TestEvaluation tests/test_farmland_grade_eval.py::TestObstacle -v`
Expected: PASS（全部 7 个测试通过，A0001 composite_index ≈ 0.6728，grade=10，首要障碍为质地构型）

- [x] **Step 6: 提交**

```bash
git add src/ai_culti_demo/farmland_grade_eval/evaluation.py src/ai_culti_demo/farmland_grade_eval/obstacle.py tests/test_farmland_grade_eval.py
git commit -m "feat(grade-eval): 移植 model2 核心评价模块（evaluation/obstacle）"
```

---

## Task 3: 部署 CSV 数据文件 + 更新 .gitignore

**Files:**
- Create: `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`（从 model2 源码复制）
- Modify: `.gitignore:35-38`（允许 CSV 入库）
- Test: 无独立测试（数据部署任务，后续 Task 4 的 runner 集成测试依赖此文件）

**数据源:** `D:\destkop\模型\模型2\Farmland_quality_Level_Database.csv`（1193 地块，20 字段）

- [x] **Step 1: 复制 CSV 数据文件**

```powershell
Copy-Item "D:\destkop\模型\模型2\Farmland_quality_Level_Database.csv" "d:\17417\Documents\agent_culti_demo\bin\farmland_quality_eval\Farmland_quality_Level_Database.csv" -Force
```

- [x] **Step 2: 验证 CSV 文件内容**

Run: `python -c "import csv; r=list(csv.reader(open('bin/farmland_quality_eval/Farmland_quality_Level_Database.csv', encoding='utf-8-sig'))); print(f'行数: {len(r)}, 表头字段数: {len(r[0])}, 首行: {r[0][:5]}...'); print(f'数据行数: {len(r)-1}')"`
Expected: 行数 1194, 表头字段数 20, 数据行数 1193

- [x] **Step 3: 更新 .gitignore 允许 CSV 入库**

编辑 `.gitignore`，在现有的 `bin/farmland_quality_eval` 规则块中添加 CSV 例外。找到：

```
# Fortran exe 及 .dat 数据库二进制文件（不入库）
bin/farmland_quality_eval/*
!bin/farmland_quality_eval/.gitkeep
!bin/farmland_quality_eval/README.md
```

替换为：

```
# 耕地质量评价数据（CSV 入库，exe/.dat 二进制不入库）
bin/farmland_quality_eval/*
!bin/farmland_quality_eval/.gitkeep
!bin/farmland_quality_eval/README.md
!bin/farmland_quality_eval/Farmland_quality_Level_Database.csv
```

- [x] **Step 4: 验证 CSV 不被 gitignore 排除**

Run: `git -C "d:\17417\Documents\agent_culti_demo" status bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`
Expected: 显示为新文件（未被 ignore）

- [x] **Step 5: 提交**

```bash
git add bin/farmland_quality_eval/Farmland_quality_Level_Database.csv .gitignore
git commit -m "chore(grade-eval): 部署 CSV 数据文件并更新 .gitignore"
```

---

## Task 4: 重写 runner.py + 更新 __init__.py

**Files:**
- Modify: `src/ai_culti_demo/farmland_grade_eval/runner.py`（完全重写，去除 subprocess/parse_output）
- Modify: `src/ai_culti_demo/farmland_grade_eval/__init__.py`（更新导出）
- Test: `tests/test_farmland_grade_eval.py`（追加 runner 集成测试）

**Interfaces:**
- Consumes: `evaluation.evaluate_land_quality`、`obstacle.compute_obstacle_factors`、`data_loader.load_parcels_from_csv`、`config.EvaluationConfig`、`models.Parcel`（来自 Task 1-2）
- Produces:
  - `runner.FarmlandGradeRunner`（`__init__(exe_path=None, dat_path=None, timeout=30)`，`check_deployment() -> Dict`，`run(parcel_code) -> Dict`）
  - `runner.run_grade_evaluation(parcel_code, exe_path=None, dat_path=None) -> Dict`
  - `runner.MODEL_VERSION = "python_v1_20260801"`
  - `runner.DEFAULT_CSV_PATH = "bin/farmland_quality_eval/Farmland_quality_Level_Database.csv"`

**当前 runner.py 问题:** 现有文件使用 subprocess.Popen 调用 exe，有 parse_output 方法解析 GBK 文本输出。重写后去除全部 subprocess/parse 逻辑，改为直接调用 Python 评价模块。

- [x] **Step 1: 编写 runner 集成失败测试**

在 `tests/test_farmland_grade_eval.py` 末尾追加：

```python
# ========== Runner 集成测试 ==========

@pytest.fixture
def runner():
    from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
    return FarmlandGradeRunner()


class TestRunnerDeployment:
    """部署校验测试。"""

    def test_check_deployment_csv_exists(self, runner):
        """CSV 已部署时 check_deployment 返回 ready=True。"""
        result = runner.check_deployment()
        assert result["csv_exists"] is True
        assert result["ready"] is True
        assert "csv_path" in result

    def test_check_deployment_csv_missing(self, tmp_path):
        """CSV 不存在时 check_deployment 返回 ready=False。"""
        from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
        runner = FarmlandGradeRunner(dat_path=str(tmp_path / "nonexistent.csv"))
        result = runner.check_deployment()
        assert result["csv_exists"] is False
        assert result["ready"] is False


class TestRunnerRun:
    """runner.run() 端到端测试（需要 CSV 已部署）。"""

    def test_run_a0001_returns_ok(self, runner):
        result = runner.run("A0001")
        assert result["status"] == "ok"
        assert result["parcel_code"] == "A0001"
        assert result["model_version"] == "python_v1_20260801"

    def test_run_a0001_composite_index_regression(self, runner):
        """A0001 综合指数与 exe 历史输出 0.6728 一致。"""
        result = runner.run("A0001")
        assert abs(result["composite_index"] - 0.6728) < 0.01

    def test_run_a0001_quality_grade(self, runner):
        result = runner.run("A0001")
        assert result["quality_grade"] == "10等"

    def test_run_a0001_parcel_info(self, runner):
        result = runner.run("A0001")
        info = result["parcel_info"]
        assert info["地块代码"] == "A0001"
        assert "经度" in info
        assert "纬度" in info
        assert info["县区名称"] == "武江区"
        assert info["二级农业区名称"].strip() == "闽南粤中农林水产区"

    def test_run_a0001_indicators_format(self, runner):
        """12 项指标，数值型 raw_value 格式为 {:.3f}，概念型为名称。"""
        result = runner.run("A0001")
        indicators = result["indicators"]
        assert len(indicators) == 12
        assert indicators[0] == {"name": "酸碱度", "code": "SJD", "raw_value": "4.600"}
        # 概念型指标（耕层质地）
        gczd = [i for i in indicators if i["code"] == "GCZD"][0]
        assert gczd["name"] == "耕层质地"
        assert gczd["raw_value"] == "黏壤土"

    def test_run_a0001_obstacle_degree(self, runner):
        """12 项障碍度，按 degree 降序，rank 1-12 递增。"""
        result = runner.run("A0001")
        obstacles = result["obstacle_degree"]
        assert len(obstacles) == 12
        assert obstacles[0]["indicator"] == "质地构型"
        assert abs(obstacles[0]["degree"] - 0.169) < 0.01
        assert obstacles[0]["level"].strip() == "中度障碍"
        assert [o["rank"] for o in obstacles] == list(range(1, 13))
        degrees = [o["degree"] for o in obstacles]
        assert degrees == sorted(degrees, reverse=True)

    def test_run_invalid_parcel_returns_error(self, runner):
        result = runner.run("INVALID_CODE_99999")
        assert result["status"] == "error"
        assert result["error"]["code"] == "PARCEL_NOT_FOUND"

    def test_run_csv_missing_returns_deployment_error(self, tmp_path):
        from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
        runner = FarmlandGradeRunner(dat_path=str(tmp_path / "nonexistent.csv"))
        result = runner.run("A0001")
        assert result["status"] == "error"
        assert result["error"]["code"] == "DEPLOYMENT_ERROR"


class TestBackwardCompatibility:
    """向后兼容测试。"""

    def test_run_grade_evaluation_default_path(self):
        from ai_culti_demo.farmland_grade_eval.runner import run_grade_evaluation
        result = run_grade_evaluation("A0001")
        assert result["status"] == "ok"

    def test_run_grade_evaluation_with_exe_path_ignored(self):
        """传 exe_path（旧调用方式）不报错，被忽略。"""
        from ai_culti_demo.farmland_grade_eval.runner import run_grade_evaluation
        result = run_grade_evaluation("A0001", exe_path="bin/nonexistent.exe")
        assert result["status"] == "ok"

    def test_runner_init_with_exe_and_dat_path(self):
        """FarmlandGradeRunner 接受 exe_path 和 dat_path 参数。"""
        from ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
        runner = FarmlandGradeRunner(exe_path="ignored.exe", dat_path=None)
        assert runner.csv_path is not None  # 使用默认 CSV 路径
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_farmland_grade_eval.py::TestRunnerDeployment tests/test_farmland_grade_eval.py::TestRunnerRun tests/test_farmland_grade_eval.py::TestBackwardCompatibility -v`
Expected: FAIL — 现有 runner 仍用 subprocess，`check_deployment` 返回 `exe_exists`/`dat_exists` 而非 `csv_exists`

- [x] **Step 3: 重写 runner.py**

完全替换 `src/ai_culti_demo/farmland_grade_eval/runner.py` 的内容：

```python
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
```

- [x] **Step 4: 更新 __init__.py**

替换 `src/ai_culti_demo/farmland_grade_eval/__init__.py` 内容（暂只导出 runner，潜力/县域函数在 Task 5 追加）：

```python
from .runner import FarmlandGradeRunner, run_grade_evaluation

__all__ = ['FarmlandGradeRunner', 'run_grade_evaluation']
```

- [x] **Step 5: 运行全部 runner 测试验证通过**

Run: `python -m pytest tests/test_farmland_grade_eval.py -v`
Expected: PASS（全部测试通过，包括 A0001 回归测试）

- [x] **Step 6: 提交**

```bash
git add src/ai_culti_demo/farmland_grade_eval/runner.py src/ai_culti_demo/farmland_grade_eval/__init__.py tests/test_farmland_grade_eval.py
git commit -m "feat(grade-eval): 重写 runner.py 为 Python 调用层，去除 subprocess 依赖"
```

---

## Task 5: 移植潜力分析与县域统计模块 + 对外函数

**Files:**
- Create: `src/ai_culti_demo/farmland_grade_eval/potential.py`
- Create: `src/ai_culti_demo/farmland_grade_eval/statistics.py`
- Modify: `src/ai_culti_demo/farmland_grade_eval/runner.py`（追加 3 个对外函数）
- Modify: `src/ai_culti_demo/farmland_grade_eval/__init__.py`（追加导出）
- Test: `tests/test_farmland_grade_eval.py`（追加潜力/县域测试）

**Interfaces:**
- Consumes: `evaluation.evaluate_land_quality`、`obstacle.calc_limiting_factors`、`config.EvaluationConfig`、`models.*`（来自 Task 1-2）
- Produces:
  - `potential.compute_single_parcel_potential(config, parcel, y, quality_index, grade) -> Tuple[List[PotentialItem], QualityResult]`
  - `potential.county_potential_statistics_data(config, parcels, xqmc_code, scenario) -> Optional[CountyPotentialResult]`
  - `statistics.county_statistics_data(config, parcels, xqmc_code) -> Optional[CountyStats]`
  - `runner.run_potential_analysis(parcel_code, csv_path=None) -> Dict[str, Any]`
  - `runner.run_county_statistics(xqmc_code, csv_path=None) -> Dict[str, Any]`
  - `runner.run_county_potential(xqmc_code, scenario, csv_path=None) -> Dict[str, Any]`

**model2 源码位置:** `D:\destkop\模型\模型2\potential.py`、`statistics.py`

- [x] **Step 1: 编写潜力分析与县域统计失败测试**

在 `tests/test_farmland_grade_eval.py` 末尾追加：

```python
# ========== 潜力分析与县域统计测试 ==========

class TestPotentialAnalysis:
    """单地块潜力分析测试。"""

    def test_run_potential_analysis_a0001(self):
        from ai_culti_demo.farmland_grade_eval.runner import run_potential_analysis
        result = run_potential_analysis("A0001")
        assert result["status"] == "ok"
        assert result["parcel_code"] == "A0001"
        assert "original" in result
        assert "full_potential" in result
        assert "items" in result
        assert isinstance(result["items"], list)

    def test_run_potential_analysis_invalid_parcel(self, tmp_path):
        from ai_culti_demo.farmland_grade_eval.runner import run_potential_analysis
        result = run_potential_analysis("INVALID_99999")
        assert result["status"] == "error"
        assert result["error"]["code"] == "PARCEL_NOT_FOUND"


class TestCountyStatistics:
    """县域统计测试。"""

    def test_run_county_statistics_wujiang(self):
        """武江区（xqmc=8）县域常规统计。"""
        from ai_culti_demo.farmland_grade_eval.runner import run_county_statistics
        result = run_county_statistics(8)
        assert result["status"] == "ok"
        assert result["county_code"] == 8
        assert "stats" in result
        assert result["stats"]["parcel_count"] > 0

    def test_run_county_statistics_no_data(self, tmp_path):
        from ai_culti_demo.farmland_grade_eval.runner import run_county_statistics
        result = run_county_statistics(999)
        assert result["status"] == "error"
        assert result["error"]["code"] == "NO_DATA"

    def test_run_county_potential_ideal(self):
        """武江区理想潜力（scenario=1）。"""
        from ai_culti_demo.farmland_grade_eval.runner import run_county_potential
        result = run_county_potential(8, 1)
        assert result["status"] == "ok"
        assert result["scenario"] == 1

    def test_run_county_potential_best(self):
        """武江区最佳潜力（scenario=2）。"""
        from ai_culti_demo.farmland_grade_eval.runner import run_county_potential
        result = run_county_potential(8, 2)
        assert result["status"] == "ok"
        assert result["scenario"] == 2
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_farmland_grade_eval.py::TestPotentialAnalysis tests/test_farmland_grade_eval.py::TestCountyStatistics -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_culti_demo.farmland_grade_eval.potential'`

- [x] **Step 3: 移植 potential.py（修正导入）**

创建 `src/ai_culti_demo/farmland_grade_eval/potential.py`。相比 model2 原文件：`from config import` → `from .config import`，`from models import` → `from .models import`，`from evaluation import` → `from .evaluation import`。完整内容从 `D:\destkop\模型\模型2\potential.py` 复制并修正导入行：

```python
"""潜力分析（纯计算，不输出）"""
import math
from typing import List, Tuple, Optional
from .config import EvaluationConfig
from .models import Parcel, QualityResult, PotentialItem, CountyPotentialResult
from .evaluation import evaluate_land_quality

def compute_single_parcel_potential(config: EvaluationConfig, parcel: Parcel,
                                    y: List[float], quality_index: float, grade: int
                                   ) -> Tuple[List[PotentialItem], QualityResult]:
    """
    单个地块潜力分析。
    返回：
        (逐指标潜力项列表, 全改良后的 QualityResult)
    """
    idx_pool = [10, 9, 2, 4, 3, 6, 5, 1, 7]   # 改良顺序
    c_col    = [0, 0, 2, 4, 3, 6, 5, 1, 7]    # 数值型对应c矩阵列
    potential_ind_names = [
        '灌溉能力  ', '排水能力  ', '有机质    ', '速效钾    ', '有效磷    ',
        '有效土层厚度', '土壤容重  ', '酸碱度    ', '耕层厚度  '
    ]
    is_numeric = [False, False, True, True, True, True, True, True, True]

    # 计算每个指标的障碍度因子（用于跳过无影响的指标）
    d_total = sum((1.0 - v) * config.weights[parcel.ejnyq-1][i] for i, v in enumerate(y))
    if d_total != 0.0:
        lim_factor = [(1.0 - y[i]) * config.weights[parcel.ejnyq-1][i] / d_total for i in range(12)]
    else:
        lim_factor = [0.0] * 12

    potential_items = []

    for k, i in enumerate(idx_pool):
        if lim_factor[i-1] <= 1e-6:
            continue

        # 原始值/潜力值字符串
        if is_numeric[k]:
            orig_vals = [parcel.sjd, parcel.yjz, parcel.yxl, parcel.sxj, parcel.trrz,
                         parcel.yxtchd, parcel.gchd]
            orig = orig_vals[c_col[k]-1]
            poten = config.c[parcel.ejnyq-1][c_col[k]-1]
            orig_str = f"{orig:8.3f}"
            poten_str = f"{poten:8.3f}"
        else:
            if i == 10:
                orig_str = f"{config.ggnl_names[parcel.ggnl-1].strip():8}"
            else:
                orig_str = f"{config.psnl_names[parcel.psnl-1].strip():8}"
            poten_str = "充分满足"

        # 构造改良后的指标
        new_sjd, new_yjz, new_yxl, new_sxj = parcel.sjd, parcel.yjz, parcel.yxl, parcel.sxj
        new_trrz, new_yxtchd, new_gchd = parcel.trrz, parcel.yxtchd, parcel.gchd
        new_psnl, new_ggnl = parcel.psnl, parcel.ggnl

        if i == 1:
            new_sjd = config.c[parcel.ejnyq-1][0]
        elif i == 2:
            new_yjz = config.c[parcel.ejnyq-1][1]
        elif i == 3:
            new_yxl = config.c[parcel.ejnyq-1][2]
        elif i == 4:
            new_sxj = config.c[parcel.ejnyq-1][3]
        elif i == 5:
            new_trrz = config.c[parcel.ejnyq-1][4]
        elif i == 6:
            new_yxtchd = config.c[parcel.ejnyq-1][5]
        elif i == 7:
            new_gchd = config.c[parcel.ejnyq-1][6]
        elif i == 9:
            new_psnl = 1
        elif i == 10:
            new_ggnl = 1

        # 创建临时地块对象用于评价
        temp_parcel = Parcel(
            tybh=parcel.tybh, jd=parcel.jd, wd=parcel.wd, mj=parcel.mj,
            sjd=new_sjd, yjz=new_yjz, yxl=new_yxl, sxj=new_sxj,
            trrz=new_trrz, yxtchd=new_yxtchd, gchd=new_gchd,
            jhxllz=parcel.jhxllz, jhxqlz=parcel.jhxqlz,
            ejnyq=parcel.ejnyq, xqmc=parcel.xqmc,
            zdgc=parcel.zdgc, psnl=new_psnl, ggnl=new_ggnl,
            dxbw=parcel.dxbw, zdgx=parcel.zdgx
        )
        new_result = evaluate_land_quality(config, temp_parcel)

        potential_items.append(
            PotentialItem(
                indicator_name=potential_ind_names[k],
                original_value=orig_str,
                potential_value=poten_str,
                original_quality_index=quality_index,
                potential_quality_index=new_result.quality_index,
                original_grade=grade,
                potential_grade=new_result.grade
            )
        )

    # 全改良（所有9个指标同时改良）
    full_new_parcel = Parcel(
        tybh=parcel.tybh, jd=parcel.jd, wd=parcel.wd, mj=parcel.mj,
        sjd=config.c[parcel.ejnyq-1][0],
        yjz=config.c[parcel.ejnyq-1][1],
        yxl=config.c[parcel.ejnyq-1][2],
        sxj=config.c[parcel.ejnyq-1][3],
        trrz=config.c[parcel.ejnyq-1][4],
        yxtchd=config.c[parcel.ejnyq-1][5],
        gchd=config.c[parcel.ejnyq-1][6],
        jhxllz=parcel.jhxllz, jhxqlz=parcel.jhxqlz,
        ejnyq=parcel.ejnyq, xqmc=parcel.xqmc,
        zdgc=parcel.zdgc, psnl=1, ggnl=1,
        dxbw=parcel.dxbw, zdgx=parcel.zdgx
    )
    full_result = evaluate_land_quality(config, full_new_parcel)

    return potential_items, full_result


def county_potential_statistics_data(config: EvaluationConfig, parcels: List[Parcel],
                                     xqmc_code: int, scenario: int) -> Optional[CountyPotentialResult]:
    """计算县域潜力统计数据。scenario=1 理想潜力，scenario=2 最佳潜力。"""
    county_p = [p for p in parcels if p.xqmc == xqmc_code]
    n = len(county_p)
    if n == 0:
        return None

    sum_sjd = sum_yjz = sum_yxl = sum_sxj = sum_trrz = sum_yxtchd = sum_gchd = 0.0
    sum_psnl = sum_ggnl = 0.0
    max_yjz = max_yxl = max_sxj = max_yxtchd = max_gchd = -1e30
    sum_grade_orig = 0.0
    cnt_grade_orig = [0] * 10
    mj_grade_orig = [0.0] * 10
    sum_contrib_orig = [0.0] * 12
    sum_contrib_pot = [0.0] * 12
    sum_ind_orig = [0.0] * 12
    min_ind_orig = [1e30] * 12
    max_ind_orig = [-1e30] * 12

    for p in county_p:
        ejnyq = p.ejnyq
        sum_sjd += p.sjd
        sum_yjz += p.yjz
        sum_yxl += p.yxl
        sum_sxj += p.sxj
        sum_trrz += p.trrz
        sum_yxtchd += p.yxtchd
        sum_gchd += p.gchd
        sum_psnl += float(p.psnl)
        sum_ggnl += float(p.ggnl)
        max_yjz = max(max_yjz, p.yjz)
        max_yxl = max(max_yxl, p.yxl)
        max_sxj = max(max_sxj, p.sxj)
        max_yxtchd = max(max_yxtchd, p.yxtchd)
        max_gchd = max(max_gchd, p.gchd)

        orig_result = evaluate_land_quality(config, p)
        sum_grade_orig += orig_result.grade
        contrib_orig = [orig_result.y[i] * config.weights[ejnyq-1][i] for i in range(12)]
        for j in range(12):
            sum_contrib_orig[j] += contrib_orig[j]

        if 1 <= orig_result.grade <= 10:
            cnt_grade_orig[orig_result.grade-1] += 1
            mj_grade_orig[orig_result.grade-1] += p.mj

        raw_vals = [p.sjd, p.yjz, p.yxl, p.sxj, p.trrz,
                    p.yxtchd, p.gchd, float(p.zdgc), float(p.psnl),
                    float(p.ggnl), float(p.dxbw), float(p.zdgx)]
        for j in range(12):
            sum_ind_orig[j] += raw_vals[j]
            if raw_vals[j] < min_ind_orig[j]:
                min_ind_orig[j] = raw_vals[j]
            if raw_vals[j] > max_ind_orig[j]:
                max_ind_orig[j] = raw_vals[j]

    avg_sjd = sum_sjd / n
    avg_yjz = sum_yjz / n
    avg_yxl = sum_yxl / n
    avg_sxj = sum_sxj / n
    avg_trrz = sum_trrz / n
    avg_yxtchd = sum_yxtchd / n
    avg_gchd = sum_gchd / n
    avg_psnl = sum_psnl / n
    avg_ggnl = sum_ggnl / n

    sum_mj = 0.0
    sum_ind = [0.0] * 12
    min_ind = [1e30] * 12
    max_ind = [-1e30] * 12
    cnt_grade = [0] * 10
    mj_grade = [0.0] * 10
    cnt_primary = [0] * 12
    mj_primary = [0.0] * 12
    lim_factors_all = []
    grades_list = []
    areas = []

    for p in county_p:
        mj = p.mj
        areas.append(mj)
        sum_mj += mj
        ejnyq = p.ejnyq

        new_sjd = p.sjd
        new_yjz = p.yjz
        new_yxl = p.yxl
        new_sxj = p.sxj
        new_trrz = p.trrz
        new_yxtchd = p.yxtchd
        new_gchd = p.gchd
        new_psnl = p.psnl
        new_ggnl = p.ggnl

        if scenario == 1:   # 理想潜力
            if new_yjz < avg_yjz: new_yjz = avg_yjz
            if new_yxl < avg_yxl: new_yxl = avg_yxl
            if new_sxj < avg_sxj: new_sxj = avg_sxj
            if new_yxtchd < avg_yxtchd: new_yxtchd = avg_yxtchd
            if new_gchd < avg_gchd: new_gchd = avg_gchd

            d_val = abs(avg_sjd - config.c[ejnyq-1][0])
            th_low = config.c[ejnyq-1][0] - d_val
            th_high = config.c[ejnyq-1][0] + d_val
            new_sjd = max(new_sjd, th_low)
            new_sjd = min(new_sjd, th_high)

            d_val = abs(avg_trrz - config.c[ejnyq-1][4])
            th_low = config.c[ejnyq-1][4] - d_val
            th_high = config.c[ejnyq-1][4] + d_val
            new_trrz = max(new_trrz, th_low)
            new_trrz = min(new_trrz, th_high)

            new_psnl = max(int(avg_psnl), p.psnl)
            new_ggnl = max(int(avg_ggnl), p.ggnl)

        elif scenario == 2:   # 最佳潜力
            if new_yjz < max_yjz:
                new_yjz = max(max_yjz, config.ut2[ejnyq-1][1])
            if new_yxl < max_yxl:
                new_yxl = max(max_yxl, config.ut2[ejnyq-1][2])
            if new_sxj < max_sxj:
                new_sxj = max(max_sxj, config.ut2[ejnyq-1][3])
            if new_yxtchd < max_yxtchd:
                new_yxtchd = max(max_yxtchd, config.ut2[ejnyq-1][5])
            if new_gchd < max_gchd:
                new_gchd = max(max_gchd, config.ut2[ejnyq-1][6])

            d_val = 1.0 / (2.0 * math.sqrt(config.a[ejnyq-1][0]))
            th_low = config.c[ejnyq-1][0] - d_val
            th_high = config.c[ejnyq-1][0] + d_val
            new_sjd = max(new_sjd, th_low)
            new_sjd = min(new_sjd, th_high)

            d_val = 1.0 / (2.0 * math.sqrt(config.a[ejnyq-1][4]))
            th_low = config.c[ejnyq-1][4] - d_val
            th_high = config.c[ejnyq-1][4] + d_val
            new_trrz = max(new_trrz, th_low)
            new_trrz = min(new_trrz, th_high)

            if new_psnl != 1: new_psnl = 1
            if new_ggnl != 1: new_ggnl = 1

        adj_parcel = Parcel(
            tybh=p.tybh, jd=p.jd, wd=p.wd, mj=p.mj,
            sjd=new_sjd, yjz=new_yjz, yxl=new_yxl, sxj=new_sxj,
            trrz=new_trrz, yxtchd=new_yxtchd, gchd=new_gchd,
            jhxllz=p.jhxllz, jhxqlz=p.jhxqlz,
            ejnyq=p.ejnyq, xqmc=p.xqmc,
            zdgc=p.zdgc, psnl=new_psnl, ggnl=new_ggnl,
            dxbw=p.dxbw, zdgx=p.zdgx
        )
        pot_result = evaluate_land_quality(config, adj_parcel)
        grades_list.append(pot_result.grade)

        contrib_pot = [pot_result.y[i] * config.weights[ejnyq-1][i] for i in range(12)]
        for j in range(12):
            sum_contrib_pot[j] += contrib_pot[j]

        d = [1.0 - v for v in pot_result.y]
        df = [d[i] * config.weights[ejnyq-1][i] for i in range(12)]
        total = sum(df)
        if total != 0.0:
            lf = [v / total for v in df]
        else:
            lf = [0.0] * 12
        lim_factors_all.append(lf)

        if 1 <= pot_result.grade <= 10:
            cnt_grade[pot_result.grade-1] += 1
            mj_grade[pot_result.grade-1] += mj

        raw_vals_new = [new_sjd, new_yjz, new_yxl, new_sxj, new_trrz,
                        new_yxtchd, new_gchd, float(p.zdgc), float(new_psnl),
                        float(new_ggnl), float(p.dxbw), float(p.zdgx)]
        for j in range(12):
            sum_ind[j] += raw_vals_new[j]
            if raw_vals_new[j] < min_ind[j]:
                min_ind[j] = raw_vals_new[j]
            if raw_vals_new[j] > max_ind[j]:
                max_ind[j] = raw_vals_new[j]

    avg_ind = [sum_ind[j]/n for j in range(12)]
    avg_lim = [sum(lf[j] for lf in lim_factors_all)/n for j in range(12)]
    avg_grade = sum(grades_list)/n

    for idx, lf in enumerate(lim_factors_all):
        max_val = -1.0
        max_idx = -1
        for j in range(12):
            if lf[j] > max_val:
                max_val = lf[j]
                max_idx = j
        if max_idx >= 0:
            cnt_primary[max_idx] += 1
            mj_primary[max_idx] += areas[idx]

    avg_grade_orig = sum_grade_orig / n
    avg_ind_orig = [sum_ind_orig[j]/n for j in range(12)]
    avg_contrib_orig = [sum_contrib_orig[j]/n for j in range(12)]
    avg_contrib_pot = [sum_contrib_pot[j]/n for j in range(12)]

    combined = list(zip(avg_lim, config.indicator_names))
    combined.sort(key=lambda x: x[0], reverse=True)
    sorted_avg, sorted_names = zip(*combined)

    return CountyPotentialResult(
        scenario=scenario,
        county_name=config.xqmc_names[xqmc_code-1],
        parcel_count=n,
        total_area=sum_mj,
        avg_grade_pot=avg_grade,
        avg_ind_pot=avg_ind,
        min_ind_pot=min_ind,
        max_ind_pot=max_ind,
        avg_lim_pot=avg_lim,
        sorted_avg_pot=list(sorted_avg),
        sorted_names_pot=list(sorted_names),
        cnt_grade_pot=cnt_grade,
        mj_grade_pot=mj_grade,
        cnt_primary_pot=cnt_primary,
        mj_primary_pot=mj_primary,
        avg_grade_orig=avg_grade_orig,
        avg_ind_orig=avg_ind_orig,
        avg_contrib_orig=avg_contrib_orig,
        avg_contrib_pot=avg_contrib_pot,
        cnt_grade_orig=cnt_grade_orig,
        mj_grade_orig=mj_grade_orig
    )
```

- [x] **Step 4: 移植 statistics.py（修正导入）**

创建 `src/ai_culti_demo/farmland_grade_eval/statistics.py`。相比 model2 原文件：修正导入为相对导入，内部 `from evaluation import` → `from .evaluation import`，`from obstacle import` → `from .obstacle import`：

```python
"""县域常规统计（返回数据）"""
from typing import List, Optional
from .config import EvaluationConfig
from .models import Parcel, CountyStats

def county_statistics_data(config: EvaluationConfig, parcels: List[Parcel], xqmc_code: int) -> Optional[CountyStats]:
    from .evaluation import evaluate_land_quality
    from .obstacle import calc_limiting_factors

    county_parcels = [p for p in parcels if p.xqmc == xqmc_code]
    n = len(county_parcels)
    if n == 0:
        return None

    sum_mj = 0.0
    sum_ind = [0.0]*12
    min_ind = [1e30]*12
    max_ind = [-1e30]*12
    cnt_grade = [0]*10
    mj_grade = [0.0]*10
    cnt_primary = [0]*12
    mj_primary = [0.0]*12
    lim_factors_all = []
    grades_list = []
    areas = []

    for p in county_parcels:
        mj = p.mj
        areas.append(mj)
        sum_mj += mj
        res = evaluate_land_quality(config, p)
        grades_list.append(res.grade)
        lf = calc_limiting_factors(config, p.ejnyq, res.y)
        lim_factors_all.append(lf)

        if 1 <= res.grade <= 10:
            cnt_grade[res.grade-1] += 1
            mj_grade[res.grade-1] += mj

        raw_vals = [p.sjd, p.yjz, p.yxl, p.sxj, p.trrz, p.yxtchd, p.gchd,
                    float(p.zdgc), float(p.psnl), float(p.ggnl), float(p.dxbw), float(p.zdgx)]
        for j in range(12):
            v = raw_vals[j]
            sum_ind[j] += v
            if v < min_ind[j]: min_ind[j] = v
            if v > max_ind[j]: max_ind[j] = v

    avg_ind = [sum_ind[j]/n for j in range(12)]
    avg_lim = [sum(lf[j] for lf in lim_factors_all)/n for j in range(12)]
    avg_grade = sum(grades_list)/n

    for idx, lf in enumerate(lim_factors_all):
        max_val = -1.0
        max_idx = -1
        for j in range(12):
            if lf[j] > max_val:
                max_val = lf[j]
                max_idx = j
        if max_idx >= 0:
            cnt_primary[max_idx] += 1
            mj_primary[max_idx] += areas[idx]

    sorted_avg, sorted_names = zip(*sorted(zip(avg_lim, config.indicator_names), reverse=True))
    return CountyStats(
        county_name=config.xqmc_names[xqmc_code-1],
        parcel_count=n, total_area=sum_mj, avg_grade=avg_grade,
        avg_ind=avg_ind, min_ind=min_ind, max_ind=max_ind,
        avg_lim_factors=avg_lim,
        sorted_avg_factors=list(sorted_avg), sorted_names=list(sorted_names),
        cnt_grade=cnt_grade, mj_grade=mj_grade,
        cnt_primary=cnt_primary, mj_primary=mj_primary
    )
```

- [x] **Step 5: 在 runner.py 追加 3 个对外函数**

在 `src/ai_culti_demo/farmland_grade_eval/runner.py` 文件末尾（`run_grade_evaluation` 函数之后）追加以下内容。同时在文件顶部导入区追加 `import dataclasses`（如已有则跳过）和潜力/统计模块导入：

在 runner.py 顶部导入区追加：
```python
from .potential import compute_single_parcel_potential, county_potential_statistics_data
from .statistics import county_statistics_data
```

在文件末尾追加：
```python
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
```

- [x] **Step 6: 更新 __init__.py 追加导出**

替换 `src/ai_culti_demo/farmland_grade_eval/__init__.py`：

```python
from .runner import (FarmlandGradeRunner, run_grade_evaluation,
                     run_potential_analysis, run_county_statistics, run_county_potential)

__all__ = ['FarmlandGradeRunner', 'run_grade_evaluation',
           'run_potential_analysis', 'run_county_statistics', 'run_county_potential']
```

- [x] **Step 7: 运行测试验证通过**

Run: `python -m pytest tests/test_farmland_grade_eval.py::TestPotentialAnalysis tests/test_farmland_grade_eval.py::TestCountyStatistics -v`
Expected: PASS（全部 6 个测试通过）

- [x] **Step 8: 提交**

```bash
git add src/ai_culti_demo/farmland_grade_eval/potential.py src/ai_culti_demo/farmland_grade_eval/statistics.py src/ai_culti_demo/farmland_grade_eval/runner.py src/ai_culti_demo/farmland_grade_eval/__init__.py tests/test_farmland_grade_eval.py
git commit -m "feat(grade-eval): 移植潜力分析与县域统计模块，新增 3 个对外函数"
```

---

## Task 6: 移植 conditioner 库函数

**Files:**
- Create: `src/ai_culti_demo/farmland_grade_eval/conditioner.py`
- Test: `tests/test_farmland_grade_eval.py`（追加 conditioner 测试）

**Interfaces:**
- Consumes: `config.EvaluationConfig`（来自 Task 1）
- Produces: `conditioner.calculate_soil_conditioner(config, tybh, mj, xqmc, ph_start, alex, hex_, r=1893.0, rph=5.5, fert_n=180.0, ndep=47.6, y=5109.0, s=5109.0, ph_target=6.811) -> Dict[str, float]`

**model2 源码位置:** `D:\destkop\模型\模型2\conditioner.py`

**改动说明:** 去除 `input()` 交互调用和所有 `print()` 输出；7 个原交互输入参数改为函数签名参数（带默认值）；返回值从 None（打印）改为 `Dict[str, float]`；添加文档注释标注"库函数，不接 API"。

- [x] **Step 1: 编写 conditioner 失败测试**

在 `tests/test_farmland_grade_eval.py` 末尾追加：

```python
# ========== Conditioner 库函数测试 ==========

class TestConditioner:
    """调理剂库函数测试（不接 API）。"""

    def test_calculate_soil_conditioner_returns_dict(self):
        from ai_culti_demo.farmland_grade_eval.config import EvaluationConfig
        from ai_culti_demo.farmland_grade_eval.conditioner import calculate_soil_conditioner
        config = EvaluationConfig()
        result = calculate_soil_conditioner(
            config, tybh="A0001", mj=100.0, xqmc=8,
            ph_start=4.6, alex=1.0, hex_=0.5,
        )
        assert isinstance(result, dict)
        assert "ytk_per_ha" in result
        assert "mbnt_per_ha" in result
        assert "ytk_tons" in result
        assert "mbnt_tons" in result
        assert result["ytk_per_ha"] > 0
        assert result["mbnt_per_ha"] > 0

    def test_calculate_soil_conditioner_custom_params(self):
        from ai_culti_demo.farmland_grade_eval.config import EvaluationConfig
        from ai_culti_demo.farmland_grade_eval.conditioner import calculate_soil_conditioner
        config = EvaluationConfig()
        result = calculate_soil_conditioner(
            config, tybh="A0001", mj=100.0, xqmc=8,
            ph_start=4.6, alex=1.0, hex_=0.5,
            r=2000.0, rph=5.0, fert_n=200.0, ndep=50.0,
            y=6000.0, s=6000.0, ph_target=6.5,
        )
        assert isinstance(result, dict)
        assert result["ytk_per_ha"] > 0
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_farmland_grade_eval.py::TestConditioner -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_culti_demo.farmland_grade_eval.conditioner'`

- [x] **Step 3: 移植 conditioner.py（去 input/print，改返回 dict）**

创建 `src/ai_culti_demo/farmland_grade_eval/conditioner.py`：

```python
"""土壤调理剂用量计算（库函数，不接 API）。

注意：本函数为库函数，不通过 HTTP API 暴露。
API 调理剂需求走 model-4 酸化模型，避免能力重叠。
"""
import math
from typing import Dict
from .config import EvaluationConfig

def calculate_soil_conditioner(
    config: EvaluationConfig,
    tybh: str,
    mj: float,
    xqmc: int,
    ph_start: float,
    alex: float,
    hex_: float,
    r: float = 1893.0,
    rph: float = 5.5,
    fert_n: float = 180.0,
    ndep: float = 47.6,
    y: float = 5109.0,
    s: float = 5109.0,
    ph_target: float = 6.811,
) -> Dict[str, float]:
    """计算土壤调理剂施用量。

    Args:
        config: 评价配置（含县区名称字典）。
        tybh: 地块统一代码。
        mj: 地块面积（亩）。
        xqmc: 县区编码。
        ph_start: 原始酸碱度。
        alex: 交换性铝离子。
        hex_: 交换性氢离子。
        r: 年均降水量(mm)，默认 1893.0。
        rph: 降水pH年均值，默认 5.5。
        fert_n: 氮元素施用量(kg/ha)，默认 180.0。
        ndep: 氮沉降量(kg/ha)，默认 47.6。
        y: 籽粒年产量(kg/ha·yr)，默认 5109.0。
        s: 秸秆年产量(kg/ha·yr)，默认 5109.0。
        ph_target: 目标酸碱度，默认 6.811。

    Returns:
        含 ytk_per_ha / mbnt_per_ha / ytk_tons / mbnt_tons 的字典。
    """
    a_values = [-1.0, 1.0, 1.0, 1.0]
    b_vals = [1.0, 1.0, 2.0, 2.0]
    c_vals = [30.97, 39.1, 40.08, 24.305]
    y_k = [0.0035, 0.0019, 0.0003, 0.0012]
    s_k = [0.0018, 0.0199, 0.0054, 0.0021]

    a_dep = (10.0 ** (-rph)) * r * (667.0 / 1000.0 * 1000.0 * 15.0)
    h_grain = [a_values[k]*y*y_k[k]*1000.0/100.0*b_vals[k]/c_vals[k] for k in range(4)]
    h_straw = [a_values[k]*s*s_k[k]*1000.0/100.0*b_vals[k]/c_vals[k] for k in range(4)]
    a_crop = sum(h_grain) + sum(h_straw)
    a_no3_runoff = 2.221 * math.exp(0.0049)*(fert_n+ndep) * 1000/14
    anit = (ndep - (0.16*ndep + 2.97)) * 1000/14 * 2
    a_vol = anit
    ano3_crop = 0.0
    ancy = a_no3_runoff + anit + a_vol
    a_agri = a_dep + a_crop + ancy + ano3_crop
    a_back = (6.25 * 10.0**(9 - ph_start)) / 1000.0 \
             - (6.25 * 10.0**(9 - ph_target)) / 1000.0 \
             + (2.5 * hex_ * 10.0**7) / 1000.0 \
             + (2.5 * alex * 10.0**7) / 1000.0

    ytk = (a_back + a_agri * 0.8) / 17.042 * 0.6 * mj
    mbnt = a_agri / 18.9 + alex * 590.0 * 15.0 * mj

    ytk_per_ha = ytk / mj if mj > 0 else 0.0
    mbnt_per_ha = mbnt / mj if mj > 0 else 0.0
    ytk_tons = ytk / 1000.0
    mbnt_tons = mbnt / 1000.0

    return {
        "ytk_per_ha": ytk_per_ha,
        "mbnt_per_ha": mbnt_per_ha,
        "ytk_tons": ytk_tons,
        "mbnt_tons": mbnt_tons,
    }
```

- [x] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_farmland_grade_eval.py::TestConditioner -v`
Expected: PASS（2 个测试通过）

- [x] **Step 5: 提交**

```bash
git add src/ai_culti_demo/farmland_grade_eval/conditioner.py tests/test_farmland_grade_eval.py
git commit -m "feat(grade-eval): 移植 conditioner 库函数（去 input/print，改返回 dict）"
```

---

## Task 7: 调用方字段适配

**Files:**
- Modify: `framework/agents/specialized/grade_agent.py:16,21`（docstring 更新）
- Modify: `src/ai_culti_demo/thematic_models.py:141,515`（purpose 和 reliability.message 更新）
- Modify: `framework/core_engine/adapter.py:142-150`（check_grade_eval_deployment 字段适配）
- Test: 无独立测试文件（通过现有集成测试验证不回归）

**当前状态:**
- `grade_agent.py` 第 16 行 docstring 为"耕地质量等级评价智能体（调用Fortran exe）"，第 21 行 description 为"通过Fortran exe进行耕地质量等级评价"
- `thematic_models.py` 第 141 行 purpose 为"通过Fortran exe进行耕地质量等级评价..."，第 515 行 reliability.message 为"当前结果来自实际耕地质量等级评价模型（Fortran exe）计算。"
- `adapter.py` 第 148 行 `check_grade_eval_deployment` 返回 `deployment_ok` 基于 `result`（runner.check_deployment 返回的 dict）

- [x] **Step 1: 更新 grade_agent.py docstring**

在 `framework/agents/specialized/grade_agent.py` 中：

找到第 16 行：
```python
    """耕地质量等级评价智能体（调用Fortran exe）"""
```
替换为：
```python
    """耕地质量等级评价智能体（Python 模型实现）"""
```

找到第 21 行：
```python
            description="通过Fortran exe进行耕地质量等级评价",
```
替换为：
```python
            description="通过 Python 模型进行耕地质量等级评价",
```

同时找到第 7 行注释：
```python
# 尝试导入实际exe模型实现
```
替换为：
```python
# 尝试导入实际 Python 模型实现
```

- [x] **Step 2: 更新 thematic_models.py purpose 和 reliability.message**

在 `src/ai_culti_demo/thematic_models.py` 中：

找到 `quality-grade-evaluation` 的 purpose（约第 141 行）：
```python
        "purpose": "通过Fortran exe进行耕地质量等级评价，输出12指标原始值/隶属度、综合指数、质量等级和障碍度排序。",
```
替换为：
```python
        "purpose": "通过 Python 模型进行耕地质量等级评价，输出12指标原始值/隶属度、综合指数、质量等级和障碍度排序。",
```

找到 `_run_real_grade_model` 中的 reliability.message（约第 515 行）：
```python
            "message": "当前结果来自实际耕地质量等级评价模型（Fortran exe）计算。",
```
替换为：
```python
            "message": "当前结果来自实际耕地质量等级评价模型（Python 实现）计算。",
```

找到 `_run_real_grade_model` 的 docstring（约第 477 行）：
```python
    """调用实际的耕地质量等级评价exe"""
```
替换为：
```python
    """调用实际的耕地质量等级评价 Python 模型"""
```

- [x] **Step 3: 更新 adapter.py check_grade_eval_deployment**

在 `framework/core_engine/adapter.py` 中，`check_grade_eval_deployment` 方法（第 142-150 行）当前返回 `deployment_ok` 基于 `result` 是否为真值。新 runner 的 `check_deployment()` 返回的 dict 中 `ready` 字段为部署就绪标志。

找到：
```python
    def check_grade_eval_deployment(self) -> Dict[str, Any]:
        self._ensure_import()
        self._ensure_data_import_imports()
        try:
            runner = self._FarmlandGradeRunner()
            result = runner.check_deployment()
            return {"deployment_ok": True, "detail": result} if result else {"deployment_ok": False, "detail": None}
        except Exception as e:
            return {"deployment_ok": False, "error": {"code": "DEPLOYMENT_CHECK_ERROR", "message": str(e)}}
```

替换为：
```python
    def check_grade_eval_deployment(self) -> Dict[str, Any]:
        self._ensure_import()
        self._ensure_data_import_imports()
        try:
            runner = self._FarmlandGradeRunner()
            result = runner.check_deployment()
            deployment_ok = bool(result and result.get("ready", False))
            return {"deployment_ok": deployment_ok, "detail": result}
        except Exception as e:
            return {"deployment_ok": False, "error": {"code": "DEPLOYMENT_CHECK_ERROR", "message": str(e)}}
```

- [x] **Step 4: 运行现有测试验证无回归**

Run: `python -m pytest tests/test_farmland_grade_eval.py tests/test_data_trigger.py -v`
Expected: PASS（所有测试通过，调用方适配不影响现有契约）

- [x] **Step 5: 提交**

```bash
git add framework/agents/specialized/grade_agent.py src/ai_culti_demo/thematic_models.py framework/core_engine/adapter.py
git commit -m "refactor(grade-eval): 调用方字段适配（docstring/message/部署校验字段）"
```

---

## Task 8: HTTP data/import 改 CSV

**Files:**
- Modify: `framework/upload/data_validator.py:55-66`（validate_dat → validate_grade_csv）
- Modify: `framework/upload/data_deployer.py:60-69`（deploy_dat → deploy_grade_csv）
- Modify: `framework/upload/data_trigger.py:64-75`（trigger_dat_check → trigger_grade_csv_check）
- Modify: `framework/api/routes/data_import.py:15-32,37,80-85,96-105,122`（导入和调用更新）
- Modify: `tests/test_data_trigger.py:75-80`（更新测试）
- Test: `tests/test_data_trigger.py`（更新触发器测试）

**当前状态:**
- `data_validator.py` 的 `validate_dat` 校验非空+大小，需改为校验 CSV 字段
- `data_deployer.py` 的 `deploy_dat` 部署为 `.dat`，需改为部署为 `.csv`
- `data_trigger.py` 的 `trigger_dat_check` 调用 `check_grade_eval_deployment`，函数名需更新
- `data_import.py` 路由导入和调用上述函数

**data_type 枚举值决策:** 保持 `data_type="dat"` 不变（最小化 BREAKING 变更，文件格式从 .dat 改为 CSV 已是 BREAKING）。函数内部实现改为 CSV 逻辑。

- [x] **Step 1: 更新 data_validator.py — 将 validate_dat 改为 validate_grade_csv**

在 `framework/upload/data_validator.py` 中，将 `validate_dat` 函数（第 55-66 行）替换为 `validate_grade_csv`。保留 `validate_dat` 作为别名以避免破坏现有导入（data_import.py 直接导入 `validate_dat`，将在 Step 4 同步更新）：

找到：
```python
def validate_dat(file_path: str) -> Tuple[bool, str]:
    """校验 .dat 文件非空且大小 ≤ 200MB。

    Returns:
        (ok, error_msg)
    """
    size = os.path.getsize(file_path)
    if size == 0:
        return False, ".dat 文件为空"
    if size > Config.MAX_DATA_IMPORT_SIZE:
        return False, f".dat 文件大小超过 {Config.MAX_DATA_IMPORT_SIZE // (1024 * 1024)}MB 限制"
    return True, ''
```

替换为：
```python
# 耕地质量评价 CSV 必需的 20 个字段（以 CSV 首行表头为准）
GRADE_CSV_REQUIRED_COLUMNS = [
    'SiteID', 'JD', 'WD', 'MJ', 'SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ',
    'YXTCHD', 'GCHD', 'JHXLLZ', 'JHXQLZ', 'EJNYQcode', 'XQMCcode',
    'GCZDcode', 'PSNLcode', 'GGNLcode', 'DXBWcode', 'ZDGXcode',
]


def validate_grade_csv(file_path: str) -> Tuple[bool, str]:
    """校验耕地质量评价 CSV 文件：非空、≤200MB、UTF-8、含 20 个必需字段。

    Returns:
        (ok, error_msg): ok=True 时 error_msg 为空字符串
    """
    size = os.path.getsize(file_path)
    if size == 0:
        return False, "CSV 文件为空"
    if size > Config.MAX_DATA_IMPORT_SIZE:
        return False, f"CSV 文件大小超过 {Config.MAX_DATA_IMPORT_SIZE // (1024 * 1024)}MB 限制"

    try:
        try:
            df = pd.read_csv(file_path, encoding='utf-8', nrows=1)
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(file_path, encoding='utf-8-sig', nrows=1)
            except UnicodeDecodeError:
                return False, "CSV 文件编码非 UTF-8"
    except Exception as e:
        return False, f"CSV 文件解析失败: {e}"

    missing = [c for c in GRADE_CSV_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return False, f"CSV 缺少必需字段: {missing}"
    return True, ''


# 向后兼容别名（data_import.py 仍使用 validate_dat 名称）
validate_dat = validate_grade_csv
```

- [x] **Step 2: 更新 data_deployer.py — 将 deploy_dat 改为 deploy_grade_csv**

在 `framework/upload/data_deployer.py` 中，找到 `deploy_dat` 函数（第 60-69 行）：

```python
def deploy_dat(src_path: str, target_dir: str) -> str:
    """将 .dat 部署到 target_dir/Farmlands_Quality_Level_Database.dat（固定文件名）。

    Returns:
        部署后的绝对路径
    """
    os.makedirs(target_dir, exist_ok=True)
    dst = os.path.join(target_dir, 'Farmlands_Quality_Level_Database.dat')
    shutil.copy2(src_path, dst)
    return dst
```

替换为：
```python
def deploy_grade_csv(src_path: str, target_dir: str) -> str:
    """将耕地质量评价 CSV 部署到 target_dir/Farmland_quality_Level_Database.csv（固定文件名）。

    Returns:
        部署后的绝对路径
    """
    os.makedirs(target_dir, exist_ok=True)
    dst = os.path.join(target_dir, 'Farmland_quality_Level_Database.csv')
    shutil.copy2(src_path, dst)
    return dst


# 向后兼容别名
deploy_dat = deploy_grade_csv
```

- [x] **Step 3: 更新 data_trigger.py — 将 trigger_dat_check 改为 trigger_grade_csv_check**

在 `framework/upload/data_trigger.py` 中，找到 `trigger_dat_check` 函数（第 64-75 行）：

```python
def trigger_dat_check(target_dir: str, timeout: Optional[float] = None) -> Dict[str, Any]:
    """触发 .dat 部署校验：调用 adapter.check_grade_eval_deployment。

    注意：target_dir 参数保留用于与其他触发器签名一致（API 路由层统一调用），
    但不传给 adapter —— check_grade_eval_deployment() 无参数，
    FarmlandGradeRunner 内部从配置解析 .dat 路径。

    Args:
        target_dir: .dat 部署目录（仅用于日志/上下文一致性）
        timeout: 超时秒数（None 时用 Config.DATA_IMPORT_TIMEOUT）
    """
    return _run_with_timeout(core_engine.check_grade_eval_deployment, timeout=timeout)
```

替换为：
```python
def trigger_grade_csv_check(target_dir: str, timeout: Optional[float] = None) -> Dict[str, Any]:
    """触发耕地质量评价 CSV 部署校验：调用 adapter.check_grade_eval_deployment。

    注意：target_dir 参数保留用于与其他触发器签名一致（API 路由层统一调用），
    但不传给 adapter —— check_grade_eval_deployment() 无参数，
    FarmlandGradeRunner 内部从配置解析 CSV 路径。

    Args:
        target_dir: CSV 部署目录（仅用于日志/上下文一致性）
        timeout: 超时秒数（None 时用 Config.DATA_IMPORT_TIMEOUT）
    """
    return _run_with_timeout(core_engine.check_grade_eval_deployment, timeout=timeout)


# 向后兼容别名
trigger_dat_check = trigger_grade_csv_check
```

- [x] **Step 4: 更新 data_import.py 路由导入和调用**

在 `framework/api/routes/data_import.py` 中，由于 Step 1-3 保留了向后兼容别名（`validate_dat`/`deploy_dat`/`trigger_dat_check`），路由代码无需改动函数名。但需更新文件顶部注释中的".dat"描述。

找到第 1 行注释：
```python
"""数据导入 API 路由：POST /api/v1/data/import

编排校验 → 部署 → 触发 → 审计日志的完整流程，支持 CSV / shapefile / .dat 三类数据。
仅 admin 角色可调用。触发失败时自动从备份回滚。
"""
```
替换为：
```python
"""数据导入 API 路由：POST /api/v1/data/import

编排校验 → 部署 → 触发 → 审计日志的完整流程，支持 CSV / shapefile / 耕地质量评价 CSV 三类数据。
仅 admin 角色可调用。触发失败时自动从备份回滚。
"""
```

注意：`data_type="dat"` 枚举值保持不变（`_VALID_TYPES = ('csv', 'shapefile', 'dat')`），但 `dat` 分支现在接受 CSV 文件。校验、部署、触发函数通过别名继续以 `validate_dat`/`deploy_dat`/`trigger_dat_check` 名称被调用，实际执行 CSV 逻辑。

- [x] **Step 5: 更新 test_data_trigger.py 测试**

在 `tests/test_data_trigger.py` 中，找到 `test_trigger_dat_check_success`（第 75-80 行）：

```python
def test_trigger_dat_check_success(fake_adapter):
    """dat 触发成功：调用无参 adapter 方法，target_dir 不传入。"""
    result = data_trigger.trigger_dat_check('/bin/farmland_quality_eval')
    assert result['deployment_ok'] is True
    # 验证 adapter 被调用一次（无参数）
    assert len(fake_adapter['check_grade_eval_deployment']) == 1
```

替换为：
```python
def test_trigger_dat_check_success(fake_adapter):
    """dat 触发成功：调用无参 adapter 方法，target_dir 不传入。"""
    result = data_trigger.trigger_dat_check('/bin/farmland_quality_eval')
    assert result['deployment_ok'] is True
    # 验证 adapter 被调用一次（无参数）
    assert len(fake_adapter['check_grade_eval_deployment']) == 1


def test_trigger_grade_csv_check_success(fake_adapter):
    """grade_csv 触发成功：新函数名与旧别名行为一致。"""
    result = data_trigger.trigger_grade_csv_check('/bin/farmland_quality_eval')
    assert result['deployment_ok'] is True
    assert len(fake_adapter['check_grade_eval_deployment']) == 1
```

- [x] **Step 6: 运行测试验证通过**

Run: `python -m pytest tests/test_data_trigger.py -v`
Expected: PASS（全部测试通过，包括新增的 `test_trigger_grade_csv_check_success`）

- [x] **Step 7: 提交**

```bash
git add framework/upload/data_validator.py framework/upload/data_deployer.py framework/upload/data_trigger.py framework/api/routes/data_import.py tests/test_data_trigger.py
git commit -m "feat(grade-eval): HTTP data/import 改 CSV（校验/部署/触发）"
```

---

## Task 9: 测试重写与回归验证

**Files:**
- Test: `tests/test_farmland_grade_eval.py`（已在 Task 1-6 中逐步重写，本任务做全量回归验证）
- Test: `tests/test_data_import_integration.py`（如有 dat 相关集成测试需更新）

**说明:** Task 1-6 已按 TDD 方式逐步编写了全部测试类。本任务执行全量回归验证，确保所有测试通过且覆盖 spec 要求的全部场景。

- [x] **Step 1: 运行 farmland_grade_eval 全量测试**

Run: `python -m pytest tests/test_farmland_grade_eval.py -v`
Expected: PASS — 覆盖以下测试类：
- `TestModels`（数据类实例化）
- `TestEvaluationConfig`（配置参数完整性）
- `TestDataLoader`（CSV 加载、跳过不足字段、文件缺失异常）
- `TestEvaluation`（A0001 回归 composite_index/grade、12 项隶属度、无效编码异常）
- `TestObstacle`（障碍度降序排序、A0001 首要障碍质地构型）
- `TestRunnerDeployment`（CSV 存在/缺失部署校验）
- `TestRunnerRun`（A0001 端到端、parcel_info/indicators/obstacle_degree 格式、无效地块错误）
- `TestBackwardCompatibility`（默认路径、exe_path 忽略、旧参数兼容）
- `TestPotentialAnalysis`（A0001 潜力分析、无效地块错误）
- `TestCountyStatistics`（武江区常规统计/理想潜力/最佳潜力、无数据错误）
- `TestConditioner`（库函数返回 dict、自定义参数）

- [x] **Step 2: 运行数据导入触发器测试**

Run: `python -m pytest tests/test_data_trigger.py -v`
Expected: PASS

- [x] **Step 3: 运行数据导入路由集成测试（如有）**

Run: `python -m pytest tests/test_data_import_route.py tests/test_data_import_integration.py -v`
Expected: PASS（如存在 dat 相关测试因别名机制仍通过；如有失败则更新测试适配 CSV 语义）

- [x] **Step 4: 运行全量测试套件验证无回归**

Run: `python -m pytest tests/ -v --tb=short`
Expected: PASS（所有测试通过，无回归）

- [x] **Step 5: 提交（如有测试修复）**

```bash
git add tests/
git commit -m "test(grade-eval): 全量回归验证通过"
```

---

## Task 10: 文档更新

**Files:**
- Modify: `README.md:11`（model-7 架构说明）
- Modify: `docs/api.md:681-707,766-770`（data/import 接口 .dat → CSV）
- Modify: `docs/openapi.json:6`（版本号递增）
- Modify: `bin/farmland_quality_eval/README.md`（部署说明全面更新）

- [x] **Step 1: 更新 README.md model-7 架构说明**

在 `README.md` 中，找到第 11 行：
```
  - model-7 耕地质量等级评价（Fortran exe）
```
替换为：
```
  - model-7 耕地质量等级评价（Python 实现，移植 model2，含潜力分析/县域统计/调理剂库函数）
```

同时找到第 165 行：
```
| POST | `/api/v1/data/import` | 上传部署专题模型数据（CSV/shapefile/.dat，需 admin） |
```
替换为：
```
| POST | `/api/v1/data/import` | 上传部署专题模型数据（CSV/shapefile/耕地质量评价CSV，需 admin） |
```

- [x] **Step 2: 更新 docs/api.md data/import 接口说明**

在 `docs/api.md` 中，找到第 681 行：
```
用于上传部署三类专题模型数据（CSV / shapefile / .dat），部署前自动备份现有文件，部署后自动触发对应的处理流程。
```
替换为：
```
用于上传部署三类专题模型数据（CSV / shapefile / 耕地质量评价 CSV），部署前自动备份现有文件，部署后自动触发对应的处理流程。
```

找到第 704-707 行（.dat 数据类型说明）：
```
**.dat（data_type=dat）**
- 部署到 `bin/farmland_quality_eval/Farmlands_Quality_Level_Database.dat`（固定文件名）
- 校验：非空、≤ 200MB
- 触发：`FarmlandGradeRunner.check_deployment` 部署校验
```
替换为：
```
**耕地质量评价 CSV（data_type=dat）**
- 部署到 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`（固定文件名）
- 校验：非空、≤ 200MB、UTF-8 编码、含 20 个必需字段（SiteID/JD/WD/MJ/SJD/YJZ/YXL/SXJ/TRRZ/YXTCHD/GCHD/JHXLLZ/JHXQLZ/EJNYQcode/XQMCcode/GCZDcode/PSNLcode/GGNLcode/DXBWcode/ZDGXcode）
- 触发：`FarmlandGradeRunner.check_deployment` 部署校验
```

找到第 766-770 行（curl 示例）：
```bash
# 上传 .dat 数据库
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <token>" \
  -F "data_type=dat" \
  -F "file=@/path/to/Farmlands_Quality_Level_Database.dat"
```
替换为：
```bash
# 上传耕地质量评价 CSV
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <token>" \
  -F "data_type=dat" \
  -F "file=@/path/to/Farmland_quality_Level_Database.csv"
```

同时更新第 285 行 parcel_code 说明中的"给 model-7 调 Fortran exe"：
```
| `parcel_code` | string | 否 | 地块代码（字母数字，给 model-7 调 Fortran exe），type 5 质量等级评价必需 |
```
替换为：
```
| `parcel_code` | string | 否 | 地块代码（字母数字，给 model-7 调 Python 模型），type 5 质量等级评价必需 |
```

更新第 492 行 quality-grade-evaluation 描述：
```
{"name": "quality-grade-evaluation", "description": "通过Fortran exe进行耕地质量等级评价，输出12指标原始值/隶属度、综合指数、质量等级和障碍度排序。"},
```
替换为：
```
{"name": "quality-grade-evaluation", "description": "通过 Python 模型进行耕地质量等级评价，输出12指标原始值/隶属度、综合指数、质量等级和障碍度排序。"},
```

- [x] **Step 3: 更新 docs/openapi.json 版本号**

在 `docs/openapi.json` 中，找到第 6 行：
```json
    "version": "1.4.0"
```
替换为：
```json
    "version": "1.5.0"
```

- [x] **Step 4: 重写 bin/farmland_quality_eval/README.md**

完全替换 `bin/farmland_quality_eval/README.md` 内容：

```markdown
# 耕地质量等级评价 Python 模型部署目录

本目录存放耕地质量等级和障碍度评价的 CSV 数据文件。

## 部署文件

| 文件 | 说明 |
|------|------|
| `Farmland_quality_Level_Database.csv` | 耕地质量评价指标数据库（CSV，20 字段，1193 地块） |

## 数据来源

外部数据源：`D:\destkop\模型\模型2\Farmland_quality_Level_Database.csv`

## 部署方式

CSV 文件已入库（不再被 .gitignore 排除），无需手动复制。如需更新数据，通过 HTTP API 上传：

```bash
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <token>" \
  -F "data_type=dat" \
  -F "file=@/path/to/Farmland_quality_Level_Database.csv"
```

## 调用契约

包装器 `src/ai_culti_demo/farmland_grade_eval/runner.py` 通过 Python 直接调用评价模块：

- **数据加载**：`load_parcels_from_csv` 读取 CSV（UTF-8-sig），解析为 Parcel 列表
- **评价计算**：`evaluate_land_quality` 计算隶属度、综合指数、等级
- **障碍度**：`compute_obstacle_factors` 计算障碍度因子排序
- **缓存**：类级缓存 + mtime 校验，CSV 重新部署后自动失效重载

## 启动时部署校验

系统启动时会调用 `FarmlandGradeRunner.check_deployment()` 校验：

- CSV 文件存在且非空

校验失败时返回 `status: "error"`，`error.code: "DEPLOYMENT_ERROR"`，阻止后续调用。

## 模型版本

`MODEL_VERSION = "python_v1_20260801"`

## 通过 HTTP API 部署

通过 `POST /api/v1/data/import` 接口上传 CSV 文件（data_type=dat），需 admin 权限。接口会将上传文件部署为本目录下的 `Farmland_quality_Level_Database.csv`（固定文件名），并自动触发 `FarmlandGradeRunner.check_deployment` 部署校验。

校验要求：文件非空、≤ 200MB、UTF-8 编码、含 20 个必需字段。

部署成功后接口返回 `deployed_path` 与 `backup_path`，部署前会自动备份现有 CSV 文件到 `backup/YYYYMMDD-HHMMSS/`（保留最近 3 份）。触发 `check_deployment` 失败时会自动回滚到备份。
```

- [x] **Step 5: 提交**

```bash
git add README.md docs/api.md docs/openapi.json bin/farmland_quality_eval/README.md
git commit -m "docs(grade-eval): 更新文档（model-7 架构/data-import CSV/部署说明）"
```

---

## Task 11: exe/.dat 废弃与清理

**Files:**
- Delete: `bin/farmland_quality_eval/Farmland_quality_evaluation.exe`
- Delete: `bin/farmland_quality_eval/Farmlands_Quality_Level_Database.dat`
- Verify: `.gitignore` 保持 exe/.dat 排除模式

**说明:** exe/.dat 文件已被 .gitignore 排除（不入库），本任务删除本地文件并验证无代码引用。由于这些文件不在 git 跟踪中，删除不需要 git commit。

- [x] **Step 1: 全局搜索确认无代码引用 exe/.dat**

Run: `Get-ChildItem -Recurse "d:\17417\Documents\agent_culti_demo" -File -Include *.py -Exclude *__pycache__*,*.venv* | Where-Object { $_.FullName -notmatch '\.venv|node_modules|__pycache__' } | Select-String -Pattern "Farmland_quality_evaluation\.exe|Farmlands_Quality_Level_Database\.dat|subprocess\.Popen|\.dat\b" | ForEach-Object { "$($_.Path):$($_.LineNumber): $($_.Line.Trim())" }`
Expected: 仅 .gitignore 和 bin/farmland_quality_eval/README.md（已更新）中的历史引用，无 .py 代码文件引用 exe/.dat/subprocess

- [x] **Step 2: 删除 exe 和 .dat 文件**

```powershell
Remove-Item "d:\17417\Documents\agent_culti_demo\bin\farmland_quality_eval\Farmland_quality_evaluation.exe" -Force
Remove-Item "d:\17417\Documents\agent_culti_demo\bin\farmland_quality_eval\Farmlands_Quality_Level_Database.dat" -Force
```

- [x] **Step 3: 验证 .gitignore 仍排除 exe/.dat**

确认 `.gitignore` 中的规则（Task 3 已更新）：
```
bin/farmland_quality_eval/*
!bin/farmland_quality_eval/.gitkeep
!bin/farmland_quality_eval/README.md
!bin/farmland_quality_eval/Farmland_quality_Level_Database.csv
```

`bin/farmland_quality_eval/*` 排除所有文件（含 exe/.dat），仅 CSV/README/.gitkeep 被例外允许入库。

- [x] **Step 4: 运行全量测试验证无回归**

Run: `python -m pytest tests/ -v --tb=short`
Expected: PASS（所有测试通过，exe/.dat 删除不影响 Python 模型运行）

- [x] **Step 5: 提交 .gitignore 变更（如有）**

```bash
git add .gitignore
git commit -m "chore(grade-eval): 废弃 exe/.dat，确认 .gitignore 排除模式"
```

---

## Self-Review Checklist

### Spec 覆盖

- [x] **耕地质量等级评价 Python 模型** → Task 1-4（models/config/data_loader/evaluation/obstacle/runner）
- [x] **核心评价查询 Scenario** → Task 4 Step 1 测试 `test_run_a0001_returns_ok`
- [x] **数据文件未部署 Scenario** → Task 4 Step 1 测试 `test_run_csv_missing_returns_deployment_error`
- [x] **地块代码未找到 Scenario** → Task 4 Step 1 测试 `test_run_invalid_parcel_returns_error`
- [x] **编码字段越界 Scenario** → Task 2 Step 1 测试 `test_invalid_ejnyq_raises_value_error`、`test_invalid_zdgc_raises_value_error`
- [x] **数值等价性 Scenario** → Task 2 Step 1 + Task 4 Step 1 A0001 回归测试
- [x] **向后兼容 API 签名** → Task 4 Step 1 `TestBackwardCompatibility`
- [x] **部署校验改为 CSV** → Task 4 Step 1 `TestRunnerDeployment`
- [x] **单地块潜力分析** → Task 5（potential.py + run_potential_analysis）
- [x] **县域统计与潜力情景分析** → Task 5（statistics.py + run_county_statistics/run_county_potential）
- [x] **调理剂库函数（不接 API）** → Task 6（conditioner.py）
- [x] **FarmlandGradeObstacleAgent 智能体** → Task 7（grade_agent.py docstring 适配）
- [x] **耕地质量评价 CSV 数据校验** → Task 8（validate_grade_csv）
- [x] **Data Deployment with Backup** → Task 8（deploy_grade_csv 部署为固定文件名）
- [x] **Offline Computation Trigger** → Task 8（trigger_grade_csv_check 触发 check_deployment）
- [x] **HTTP data/import BREAKING** → Task 8（data_type=dat 接受 CSV）
- [x] **调用方零改动** → Task 7（签名兼容验证）
- [x] **文档更新** → Task 10
- [x] **exe/.dat 废弃清理** → Task 11

### 类型一致性

- `FarmlandGradeRunner.__init__(exe_path, dat_path, timeout)` — Task 4 定义，Task 5/7/8 使用
- `run_grade_evaluation(parcel_code, exe_path, dat_path)` — Task 4 定义，Task 7 验证兼容
- `run_potential_analysis(parcel_code, csv_path)` — Task 5 定义，与 spec 一致
- `run_county_statistics(xqmc_code, csv_path)` — Task 5 定义，与 spec 一致
- `run_county_potential(xqmc_code, scenario, csv_path)` — Task 5 定义，与 spec 一致
- `check_deployment()` 返回 `csv_exists`/`csv_path`/`ready` — Task 4 定义，Task 7 adapter.py 使用 `ready`
- `MODEL_VERSION = "python_v1_20260801"` — Task 4 定义，Task 10 文档引用
- `DEFAULT_CSV_PATH` — Task 4 定义，Task 3 部署路径一致
