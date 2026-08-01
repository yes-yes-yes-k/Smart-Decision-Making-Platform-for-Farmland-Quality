---
comet_change: replace-grade-eval-with-python-model
role: technical-design
canonical_spec: openspec
---

# Design Doc: replace-grade-eval-with-python-model

## 1. 上下文与目标

### 1.1 背景

model-7（耕地质量等级评价）当前通过 `FarmlandGradeRunner` 调用 `subprocess.Popen` 启动 Fortran exe（`Farmland_quality_evaluation.exe`，~911KB），读取二进制 `.dat`（~199KB，1193 地块），以 GBK 编码通信，解析文本输出为结构化 dict。

三处调用方：
- `framework/agents/specialized/grade_agent.py`（`FarmlandGradeAgent`）
- `src/ai_culti_demo/thematic_models.py`（`_run_real_grade_model`）
- `framework/core_engine/adapter.py`（`check_grade_eval_deployment`）

模型作者提供完整 Python 实现（model2 源码），仅依赖标准库，含核心评价、潜力分析、县域统计、调理剂计算。本次将 model2 移植为项目内 Python 模块，去除 exe/.dat 依赖。

### 1.2 目标

1. 纯 Python 实现完全替换 exe + .dat
2. 移植 model2 完整系统（核心评价 + 潜力分析 + 县域统计 + 调理剂库函数）
3. `run_grade_evaluation` 签名向后兼容，三处调用方零改动
4. 核心评价输出与 exe 历史输出数值等价（容差 < 0.01）
5. HTTP `/api/v1/data/import` 从 .dat 改为 CSV

### 1.3 非目标

- 不修改 model-3/4/5/6
- 不将 conditioner 接入 API（model-4 处理）
- 不移植 main.py/reports.py（交互式 CLI 不在 API 范围）

## 2. 详细实现设计

### 2.1 模块移植（D1）

将 model2 的 8 个模块移植到 `src/ai_culti_demo/farmland_grade_eval/`，修正为包内相对导入：

| 文件 | 内容 | 导入修正 |
|------|------|----------|
| `models.py` | Parcel, QualityResult, ObstacleItem, PotentialItem, CountyStats, CountyPotentialResult | 无外部导入 |
| `config.py` | EvaluationConfig（隶属函数参数 a/c/ut1/ut2、概念型隶属度、权重、等级阈值、名称字典） | 无外部导入 |
| `data_loader.py` | load_parcels_from_csv（UTF-8-sig CSV → List[Parcel]） | `from .models import Parcel` |
| `evaluation.py` | membership_numeric + evaluate_land_quality | `from .config import EvaluationConfig`、`from .models import Parcel, QualityResult` |
| `obstacle.py` | calc_limiting_factors + compute_obstacle_factors | `from .config import EvaluationConfig`、`from .models import ObstacleItem` |
| `potential.py` | compute_single_parcel_potential + county_potential_statistics_data | `from .config import`、`from .models import`、`from .evaluation import` |
| `statistics.py` | county_statistics_data | `from .config import`、`from .models import` |
| `conditioner.py` | calculate_soil_conditioner（去 input()，参数签名传入） | `from .config import EvaluationConfig` |

原 model2 用绝对导入（`from config import ...`），移植后统一改为 `from .config import ...` 相对导入。

### 2.2 runner.py 重写（D2 + D3）

#### 签名兼容

```python
MODEL_VERSION = "python_v1_20260801"
DEFAULT_CSV_PATH = "bin/farmland_quality_eval/Farmland_quality_Level_Database.csv"

class FarmlandGradeRunner:
    _parcels_cache = None       # 类级缓存
    _csv_path_cached = None
    _csv_mtime_cached = None

    def __init__(self, exe_path: str = None, dat_path: str = None, timeout: int = 30):
        # dat_path 语义改为 csv_path；exe_path 忽略；timeout 保留但不使用
        self.csv_path = dat_path or DEFAULT_CSV_PATH
        self.exe_path = exe_path  # 忽略，仅保留
        self.timeout = timeout    # 保留，不再用于 subprocess
```

#### check_deployment

```python
def check_deployment(self) -> Dict[str, Any]:
    csv_exists = os.path.exists(self.csv_path) and os.path.getsize(self.csv_path) > 0
    return {
        "csv_exists": csv_exists,
        "csv_path": self.csv_path,
        "ready": csv_exists,
    }
```

不再校验 exe/.dat。adapter.py 的 `check_grade_eval_deployment` 调用此方法，返回字段兼容（`deployment_ok` 基于 `ready`）。

#### 数据加载与缓存（类级缓存 + mtime 校验）

```python
def _load_parcels(self) -> List[Parcel]:
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
```

CSV 重新部署后 mtime 变化，自动失效重载。waitress 多线程下类变量竞争由 GIL 保证单条赋值原子，最坏情况重复加载一次。

#### run 方法

```python
def run(self, parcel_code: str) -> Dict[str, Any]:
    deployment = self.check_deployment()
    if not deployment["ready"]:
        return {"status": "error", "error": {"code": "DEPLOYMENT_ERROR",
                "message": f"CSV 数据文件缺失: {self.csv_path}"}}

    parcels = self._load_parcels()
    parcel = next((p for p in parcels if p.tybh.strip() == parcel_code), None)
    if parcel is None:
        return {"status": "error", "error": {"code": "PARCEL_NOT_FOUND",
                "message": f"未找到地块代码: {parcel_code}"}}

    config = EvaluationConfig()
    try:
        result = evaluate_land_quality(config, parcel)
        obstacles = compute_obstacle_factors(config, parcel.ejnyq, result.y)
    except ValueError as e:
        return {"status": "error", "error": {"code": "INVALID_ENCODING", "message": str(e)}}

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
```

#### indicators 组装

```python
# 数值型：(name, code, 取值函数, 格式化); 概念型：(name, code, 取值函数, None)
_INDICATOR_MAP = [
    ("酸碱度", "SJD", lambda p: p.sjd),
    ("有机质含量", "YJZ", lambda p: p.yjz),
    ("有效磷含量", "YXL", lambda p: p.yxl),
    ("速效钾含量", "SXJ", lambda p: p.sxj),
    ("土壤容重", "TRRZ", lambda p: p.trrz),
    ("有效土层厚度", "YXTCHD", lambda p: p.yxtchd),
    ("耕层厚度", "GCHD", lambda p: p.gchd),
]

def _build_indicators(self, parcel, config) -> list:
    indicators = []
    # 7 个数值型
    for name, code, fn in self._INDICATOR_MAP:
        indicators.append({"name": name, "code": code, "raw_value": f"{fn(parcel):.3f}"})
    # 5 个概念型
    concept_map = [
        ("耕层质地", "GCZD", config.zdgc_names, parcel.zdgc),
        ("排水能力", "PSNL", config.psnl_names, parcel.psnl),
        ("灌溉能力", "GGNL", config.ggnl_names, parcel.ggnl),
        ("地形部位", "DXBW", config.dxbw_names, parcel.dxbw),
        ("质地构型", "ZDGX", config.zdgx_names, parcel.zdgx),
    ]
    for name, code, names, idx in concept_map:
        indicators.append({"name": name, "code": code, "raw_value": names[idx-1].strip()})
    return indicators
```

raw_value 格式与 exe 输出对齐：数值型 `"{:.3f}"`（如 "4.600"），概念型为名称字符串（如 "黏壤土"）。

#### obstacle_degree 组装

```python
def _build_obstacle_degree(self, obstacles) -> list:
    return [{"rank": i+1, "indicator": o.name.strip(), "degree": o.factor, "level": o.degree.strip()}
            for i, o in enumerate(obstacles)]
```

`compute_obstacle_factors` 已按 factor 降序排序，rank 自然递增。

#### parcel_info 组装

```python
def _build_parcel_info(self, parcel, config) -> dict:
    return {
        "地块代码": parcel.tybh,
        "经度": str(parcel.jd),
        "纬度": str(parcel.wd),
        "县区名称": config.xqmc_names[parcel.xqmc-1].strip(),
        "二级农业区名称": config.ejnyq_names[parcel.ejnyq-1].strip(),
    }
```

### 2.3 潜力分析与县域统计函数（D5）

```python
def run_potential_analysis(parcel_code: str, csv_path: str = None) -> Dict[str, Any]:
    runner = FarmlandGradeRunner(dat_path=csv_path)
    # ... 加载地块 ...
    config = EvaluationConfig()
    result = evaluate_land_quality(config, parcel)
    items, full_result = compute_single_parcel_potential(config, parcel, result.y, result.quality_index, result.grade)
    return {
        "status": "ok", "parcel_code": parcel_code,
        "original": {"quality_index": result.quality_index, "grade": result.grade},
        "full_potential": {"quality_index": full_result.quality_index, "grade": full_result.grade},
        "items": [dataclasses.asdict(item) for item in items],
    }

def run_county_statistics(xqmc_code: int, csv_path: str = None) -> Dict[str, Any]:
    # ... 加载 parcels, config ...
    stats = county_statistics_data(config, parcels, xqmc_code)
    if stats is None:
        return {"status": "error", "error": {"code": "NO_DATA", "message": f"县区 {xqmc_code} 无地块数据"}}
    return {"status": "ok", "county_code": xqmc_code, "stats": dataclasses.asdict(stats)}

def run_county_potential(xqmc_code: int, scenario: int, csv_path: str = None) -> Dict[str, Any]:
    # ... 加载 parcels, config ...
    result = county_potential_statistics_data(config, parcels, xqmc_code, scenario)
    if result is None:
        return {"status": "error", "error": {"code": "NO_DATA", "message": f"县区 {xqmc_code} 无地块数据"}}
    return {"status": "ok", "county_code": xqmc_code, "scenario": scenario, "result": dataclasses.asdict(result)}
```

### 2.4 conditioner 库函数（D4）

移植 `conditioner.py`，去除 `input()` 调用，参数全部由签名传入。返回 YTK/MBNT 单位施用量和总施用量 dict（不打印）：

```python
def calculate_soil_conditioner(config, tybh, mj, xqmc, ph_start, alex, hex_) -> Dict[str, float]:
    """库函数：计算土壤调理剂施用量。不接 API；API 调理剂需求走 model-4 酸化模型。"""
    # ... 计算 ytk_per_ha, mbnt_per_ha, ytk_tons, mbnt_tons ...
    return {"ytk_per_ha": ytk_per_ha, "mbnt_per_ha": mbnt_per_ha, "ytk_tons": ytk_tons, "mbnt_tons": mbnt_tons}
```

### 2.5 HTTP data/import 改 CSV（D6）

`framework/upload/data_trigger.py` 的 `data_type=dat` 分支改为：
- 接受 CSV 文件
- 校验：非空、≤200MB、UTF-8、含 20 个必需表头字段（SiteID, JD, WD, MJ, SJD, YJZ, YXL, SXJ, TRRZ, YXTCHD, GCHD, JHXLLZ, JHXQLZ, EJNYQcode, XQMCcode, GCZDcode, PSNLcode, GGNLcode, DXBWcode, ZDGXcode）
- 部署为 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`（固定文件名）
- 部署后触发 `FarmlandGradeRunner.check_deployment()`
- 沿用 backup/ 回滚机制

### 2.6 __init__.py 导出

```python
from .runner import (FarmlandGradeRunner, run_grade_evaluation,
                     run_potential_analysis, run_county_statistics, run_county_potential)
__all__ = ['FarmlandGradeRunner', 'run_grade_evaluation',
           'run_potential_analysis', 'run_county_statistics', 'run_county_potential']
```

## 3. 调用方适配

### grade_agent.py
- 签名兼容，零改动
- docstring 从"通过Fortran exe进行耕地质量等级评价"改为"通过 Python 模型进行耕地质量等级评价"

### thematic_models.py
- `_run_real_grade_model` 签名兼容，零改动
- reliability.message 从"当前结果来自实际耕地质量等级评价模型（Fortran exe）计算"改为"当前结果来自实际耕地质量等级评价模型（Python 实现）计算"

### adapter.py
- `check_grade_eval_deployment` 调用 `check_deployment()`，返回字段从 `exe_exists`/`dat_exists` 改为 `csv_exists`，`deployment_ok` 基于 `ready`

## 4. 测试策略

### 4.1 A0001 回归测试

```python
def test_a0001_regression_composite_index():
    result = run_grade_evaluation("A0001")
    assert result["status"] == "ok"
    assert abs(result["composite_index"] - 0.6728) < 0.01
    assert result["quality_grade"] == "10等"

def test_a0001_regression_obstacle_degree():
    result = run_grade_evaluation("A0001")
    obstacles = result["obstacle_degree"]
    assert len(obstacles) == 12
    assert obstacles[0]["indicator"] == "质地构型"
    assert abs(obstacles[0]["degree"] - 0.169) < 0.01
    assert obstacles[0]["level"] == "中度障碍"
    # ranks 1-12 递增
    assert [o["rank"] for o in obstacles] == list(range(1, 13))

def test_a0001_indicators_format():
    result = run_grade_evaluation("A0001")
    indicators = result["indicators"]
    assert len(indicators) == 12
    assert indicators[0] == {"name": "酸碱度", "code": "SJD", "raw_value": "4.600"}
```

### 4.2 其他测试

- 部署校验：CSV 存在/缺失
- 向后兼容：传 exe_path/dat_path 不报错
- 缓存：mtime 变化后重载
- 潜力分析：run_potential_analysis("A0001") 返回合理结果
- 县域统计：run_county_statistics(8) / run_county_potential(8, 1) 返回合理结果
- 编码越界：INVALID_ENCODING 错误返回
- conditioner 库函数：calculate_soil_conditioner 返回 YTK/MBNT

## 5. 技术风险与缓解

| 风险 | 缓解 |
|------|------|
| Python 与 exe 数值不等价 | A0001 回归对比；model2 与 exe 基于同一 GB/T 33469-2016 标准 |
| 类级缓存线程竞争 | GIL 保证单条赋值原子；最坏重复加载一次 |
| CSV 经纬度精度差异 | 仅影响 parcel_info 显示，不影响质量指数计算 |
| conditioner 与 model-4 混淆 | 不接 API + 文档标注 |
| HTTP data/import BREAKING | 文档明确标注；demo 项目无在线迁移需求 |

## 6. Spec Patch

修改 `specs/thematic-data-import/spec.md` 的"耕地质量评价 CSV 数据校验"requirement，20 个必需字段名改为实际 CSV 表头名：
`SiteID, JD, WD, MJ, SJD, YJZ, YXL, SXJ, TRRZ, YXTCHD, GCHD, JHXLLZ, JHXQLZ, EJNYQcode, XQMCcode, GCZDcode, PSNLcode, GGNLcode, DXBWcode, ZDGXcode`

## 7. 实现顺序建议

1. 模块移植（2.1）—— 8 个模块 + 相对导入
2. runner.py 重写（2.2）—— 核心调用层 + 缓存 + 字段组装
3. 数据文件部署（CSV 复制 + .gitignore）
4. 潜力分析与县域统计函数（2.3）
5. conditioner 库函数（2.4）
6. 调用方适配（第 3 节）
7. HTTP data/import 改 CSV（2.5）
8. 测试（第 4 节）
9. 文档更新
10. exe/.dat 废弃清理
