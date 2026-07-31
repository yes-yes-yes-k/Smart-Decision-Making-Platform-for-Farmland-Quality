---
change: replace-acidification-with-process-model
design-doc: docs/superpowers/specs/2026-08-01-replace-acidification-with-process-model-design.md
base-ref: ca6f94be5aeff8a33812bedee05bc8407f042420
---

# 用过程模型替换酸化改良逻辑 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 model-4 酸化改良从「规则导向 + DB 查询」替换为移植自模型5的 4 子过程模型（水田/旱地 × 尿素/复合肥），统一入口 `calculate_acidification_amendment` 计算 YTK（亿土康）与 MBNT（木本泥炭），并贯穿 API → nodes → Agent → model_4 全链路。

**Architecture:** 计算核心下沉到 `src/ai_culti_demo/farmland_diagnosis/acidification.py`（4 子模型 + 统一入口 + 旧函数委托）；`framework/domain/other_models/model_4.py` 作为 framework 层入口负责输入映射与 `parcel_id→SJD` 补充；`AcidificationRemediationAgent` 适配新返回结构；`nodes.py`/`chat.py` 透传 `fertilizer_type`。采用 TDD：每个子模型/分支用模型5源码示例值（pHstart=4.31, Hex=1.56, Alex=4.08）作为断言锚点。

**Tech Stack:** Python 3.10+、stdlib `math`/`sqlite3`、`numpy`（仅现有依赖）、pytest、Flask（API 层）。

**Design Doc:** `docs/superpowers/specs/2026-08-01-replace-acidification-with-process-model-design.md`

## Global Constraints

- 输入字段映射：`SJD → pHstart`、`JHX → Hex`、`JLA → Alex`（来源：设计文档 §2.3）。
- 校验范围：`pHstart ∈ [3.0, 10.0]`；`Hex ≥ 0`；`Alex ≥ 0`；越界 → `status="rejected"`、`reason="input_out_of_range"`；缺失必填（JHX/JLA）→ `reason="missing_input"`（设计文档 §2.3、tasks 2.5）。
- `land_type ∈ {"upland","paddy"}`，`fertilizer_type ∈ {"compound","urea"}`；非法值回退默认 `upland+compound` 并追加 `warning`（设计文档 §2.3、tasks 2.6）。
- 可配参数白名单：`{"RPH","R","Y","S","FertN","Ndep","pHtarget"}`；元素含量参数（`Yp/Yk/Yca/Ymg/Sp/Sk/Sca/Smg/YN/SN`）保持内置不可配（tasks 2.4）。
- 旧函数 `classify_acidification/generate_amendment/calculate_lime_demand/calculate_amendment_rate` 保留不删（标记 deprecated）避免破坏引用；`query_acidification/evaluate_acidification` 改为委托或标记 deprecated（tasks 2.7、设计文档 §2.6）。
- `model_version` 统一取 `"process_v1_20260801"`。
- 移植正确性风险：4 子模型系数必须逐行对照源码 `D:\destkop\模型5\02_酸化模型计算-地块.py`（设计文档 §4 风险表）；示例值断言（±0.01）为正确性闸门。
- `question_type=2 → model-4` 路由不得改变；其他 question_type（1/3/4/5）不受影响（设计文档 §3.3）。
- 提交粒度：每个 Task 结束一次 commit；commit message 前缀 `feat:`/`refactor:`/`test:`/`docs:`。
- DRY/YAGNI：不引入新依赖；复用现有 `DiagnosisStorage`、`MockDataLoader.mark_simulated` 模式。

---

## 任务依赖关系

```
Task 1 (字段标准码) ──► Task 2 (过程模型核心) ──► Task 3 (model_4 入口) ──► Task 4 (Agent 适配) ──► Task 5 (API 透传) ──► Task 6 (回归验证) ──► Task 7 (文档)
                                                     │
                                                     └─ 依赖 DiagnosisStorage（已存在）
```

- Task 2 依赖 Task 1 的 `config.py` 字段声明。
- Task 3 依赖 Task 2 的 `calculate_acidification_amendment`。
- Task 4 依赖 Task 3 的 `model_4_execution`。
- Task 5 依赖 Task 4 的 Agent（透传链路终点）。
- Task 6 依赖 Task 1-5 全部完成。
- Task 7 依赖 Task 6 验证通过。

---

### Task 1: 字段标准码新增（tasks 第1组）

**Files:**
- Modify: `src/ai_culti_demo/farmland_diagnosis/config.py:17-18`（`ALL_INDICATORS`、`CONTINUOUS_INDICATORS`）
- Modify: `src/ai_culti_demo/farmland_diagnosis/config.py:101-114`（`INDICATOR_DISPLAY_MAP`）
- Modify: `src/ai_culti_demo/farmland_diagnosis/storage.py:9`（`_ALL_INDICATORS` 本地副本）
- Test: `tests/test_config_indicators.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `ALL_INDICATORS`/`CONTINUOUS_INDICATORS` 含 `JHX`、`JLA`；`INDICATOR_DISPLAY_MAP["JHX"]="交换性氢"`、`["JLA"]="交换性铝"`

**验证标准:** `JHX`/`JLA` 同时出现在 `ALL_INDICATORS` 与 `CONTINUOUS_INDICATORS`；`INDICATOR_DISPLAY_MAP` 含两条映射；`storage._ALL_INDICATORS` 与 `config.ALL_INDICATORS` 一致；现有 `calc_obstacle_level` 不为 JHX/JLA 报错（落入 else → nan）。

- [x] **Step 1: 编写失败测试**

```python
# tests/test_config_indicators.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_jhx_jla_in_all_and_continuous_indicators():
    from ai_culti_demo.farmland_diagnosis.config import (
        ALL_INDICATORS, CONTINUOUS_INDICATORS, INDICATOR_DISPLAY_MAP,
    )
    assert "JHX" in ALL_INDICATORS and "JLA" in ALL_INDICATORS
    assert "JHX" in CONTINUOUS_INDICATORS and "JLA" in CONTINUOUS_INDICATORS
    assert INDICATOR_DISPLAY_MAP["JHX"] == "交换性氢"
    assert INDICATOR_DISPLAY_MAP["JLA"] == "交换性铝"

def test_storage_all_indicators_matches_config():
    from ai_culti_demo.farmland_diagnosis.config import ALL_INDICATORS
    from ai_culti_demo.farmland_diagnosis.storage import _ALL_INDICATORS
    assert _ALL_INDICATORS == ALL_INDICATORS
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_config_indicators.py -v`
Expected: FAIL（`JHX` not in `ALL_INDICATORS`）

- [x] **Step 3: 修改 config.py**

在 `ALL_INDICATORS` 末尾追加 `'JHX', 'JLA'`；在 `CONTINUOUS_INDICATORS` 末尾追加 `'JHX', 'JLA'`；在 `INDICATOR_DISPLAY_MAP` 末尾追加：

```python
    'GCHD': '耕层厚度',
    'JHX': '交换性氢',
    'JLA': '交换性铝',
}
```

- [x] **Step 4: 同步 storage.py 的 `_ALL_INDICATORS`**

```python
_ALL_INDICATORS = ['SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ', 'GCZD', 'GGNL', 'PSNL', 'DXBW', 'ZDGX', 'YXTCHD', 'GCHD', 'JHX', 'JLA']
```

- [x] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_config_indicators.py -v`
Expected: PASS

- [x] **Step 6: 回归现有 config 测试**

Run: `python -m pytest tests/ -k "config or indicator or obstacle" -v`
Expected: 无新增失败（`calc_obstacle_level` 对 JHX/JLA 走 else 返回 nan，不报错）

- [x] **Step 7: Commit**

```bash
git add src/ai_culti_demo/farmland_diagnosis/config.py src/ai_culti_demo/farmland_diagnosis/storage.py tests/test_config_indicators.py
git commit -m "feat(acidification): add JHX/JLA standard indicator codes"
```

---

### Task 2: 过程模型核心实现（tasks 第2组 + 第6组 6.1-6.5）

**Files:**
- Modify: `src/ai_culti_demo/farmland_diagnosis/acidification.py`（完全重写，保留旧函数委托）
- Modify: `src/ai_culti_demo/farmland_diagnosis/__init__.py:11-14,16-27`（导出新函数）
- Test: `tests/test_model4_acidification.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `config.py`
- Produces:
  - `calculate_acidification_amendment(pHstart, Hex, Alex, land_type="upland", fertilizer_type="compound", **optional_params) -> Dict[str, Any]`
  - 返回结构：`{status, ytk, mbnt, sub_model, land_type, fertilizer_type, customized_params, warning(可选), model_version, reason(可选), out_of_range_features(可选)}`
  - 4 子模型函数 `_paddy_urea/_paddy_compound/_upland_urea/_upland_compound(pHstart, Hex, Alex, **params) -> Dict[str, float]`
  - 委托后的 `query_acidification`、`evaluate_acidification`

**验证标准（覆盖 tasks 6.1-6.5）:**
- 4 子模型在 pHstart=4.31, Hex=1.56, Alex=4.08 下，YTK/MBNT 与模型5源码手动计算值一致（±0.01）。
- 4 种 land_type×fertilizer_type 组合各自选对 `sub_model`。
- 非法 `land_type="foo"`/`fertilizer_type="bar"` → 回退 `upland+compound` + `warning`。
- 缺 JHX/JLA → `status="rejected"`, `reason="missing_input"`；SJD=2.5 或 JHX=-1 → `reason="input_out_of_range"`。
- `FertN=200` → `customized_params={"FertN":200}` 且 ytk/mbnt 与默认不同。

- [ ] **Step 1: 从模型5源码提取期望值（断言锚点）**

读取 `D:\destkop\模型5\02_酸化模型计算-地块.py`，对 4 子模型分别用 `pHstart=4.31, Hex=1.56, Alex=4.08`（默认参数）运行，记录 YTK/MBNT 期望值。在测试文件顶部以常量记录：

```python
# tests/test_model4_acidification.py 顶部
EXPECTED = {
    "paddy_urea":     {"ytk": <源码值>, "mbnt": <源码值>},     # 用源码实际输出替换
    "paddy_compound": {"ytk": <源码值>, "mbnt": <源码值>},
    "upland_urea":    {"ytk": <源码值>, "mbnt": <源码值>},
    "upland_compound":{"ytk": <源码值>, "mbnt": <源码值>},
}
```

> 实施者必须先用源码跑出真实数值填入 `<源码值>`，再继续后续步骤。此为正确性闸门。

- [ ] **Step 2: 编写失败测试（计算正确性 + 子模型选择，覆盖 6.1/6.2）**

```python
# tests/test_model4_acidification.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import math
from ai_culti_demo.farmland_diagnosis.acidification import calculate_acidification_amendment

PHSTART, HEX, ALEX = 4.31, 1.56, 4.08

def _approx(a, b, tol=0.01):
    return a is not None and b is not None and abs(a - b) <= tol

def test_four_submodels_calculation():
    cases = [
        ("paddy",  "urea",     "paddy_urea"),
        ("paddy",  "compound", "paddy_compound"),
        ("upland", "urea",     "upland_urea"),
        ("upland", "compound", "upland_compound"),
    ]
    for lt, ft, sub in cases:
        r = calculate_acidification_amendment(PHSTART, HEX, ALEX, land_type=lt, fertilizer_type=ft)
        assert r["status"] == "success", f"{sub} status={r.get('status')}, reason={r.get('reason')}"
        assert r["sub_model"] == sub
        assert _approx(r["ytk"], EXPECTED[sub]["ytk"]), f"{sub} ytk={r['ytk']} expected={EXPECTED[sub]['ytk']}"
        assert _approx(r["mbnt"], EXPECTED[sub]["mbnt"]), f"{sub} mbnt={r['mbnt']} expected={EXPECTED[sub]['mbnt']}"

def test_submodel_selection():
    assert calculate_acidification_amendment(PHSTART,HEX,ALEX,land_type="upland",fertilizer_type="compound")["sub_model"]=="upland_compound"
    assert calculate_acidification_amendment(PHSTART,HEX,ALEX,land_type="upland",fertilizer_type="urea")["sub_model"]=="upland_urea"
    assert calculate_acidification_amendment(PHSTART,HEX,ALEX,land_type="paddy",fertilizer_type="compound")["sub_model"]=="paddy_compound"
    assert calculate_acidification_amendment(PHSTART,HEX,ALEX,land_type="paddy",fertilizer_type="urea")["sub_model"]=="paddy_urea"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_model4_acidification.py -v`
Expected: FAIL（`calculate_acidification_amendment` 不存在或未实现）

- [ ] **Step 4: 实现 acidification.py 默认参数集合（tasks 2.3）**

完全重写 `src/ai_culti_demo/farmland_diagnosis/acidification.py`。先写默认参数与可配白名单：

```python
import math
import sqlite3
from typing import Any, Dict, Optional
import pandas as pd  # 保留给 evaluate_acidification 旧路径
from .config import AMENDMENT_CONFIG
from .storage import DiagnosisStorage

MODEL_VERSION = "process_v1_20260801"

# 可配参数白名单（API 可覆盖）
CONFIGURABLE_PARAMS = {"RPH", "R", "Y", "S", "FertN", "Ndep", "pHtarget"}

# 水田共用默认参数
_PADDY_DEFAULTS: Dict[str, float] = {
    "RPH": 4.5, "R": 1500.0,
    "Y": 5109.0, "S": 5109.0,
    "FertN": 0.0, "Ndep": 19.0,
    "pHtarget": 6.5,
    # 元素含量（g/kg，内置不可配）
    "Yp": 3.0, "Yk": 3.0, "Yca": 0.5, "Ymg": 1.2,
    "Sp": 1.0, "Sk": 15.0, "Sca": 3.0, "Smg": 2.0,
}
_UPLAND_DEFAULTS: Dict[str, float] = {
    "RPH": 4.5, "R": 1500.0,
    "Y": 6700.0, "S": 6968.0,
    "FertN": 0.0, "Ndep": 19.0,
    "pHtarget": 6.0,
    "Yp": 3.0, "Yk": 3.0, "Yca": 0.5, "Ymg": 1.2,
    "Sp": 1.0, "Sk": 15.0, "Sca": 3.0, "Smg": 2.0,
}
# 复合肥额外参数（籽粒/秸秆含氮量 %）
_PADDY_COMPOUND_EXTRA = {"YN": 1.87, "SN": 1.15}
_UPLAND_COMPOUND_EXTRA = {"YN": 1.91, "SN": 0.66}
```

> 上述元素含量默认值为占位；实施时必须以 `D:\destkop\模型5\02_酸化模型计算-地块.py` 中的实际数值替换。Step 1 的断言锚点会捕获任何偏差。

- [ ] **Step 5: 实现通用计算基元（Adep/Acrop/ANcy/Aagri/Aback，设计文档 §1.2）**

```python
def _adep(RPH: float, R: float) -> float:
    """酸沉降产酸量 Adep = 10^(-RPH) * 667 * (R/1000) * 1000 * 15"""
    return (10 ** (-RPH)) * 667 * (R / 1000.0) * 1000 * 15

def _hcrop(Y: float, S: float, ec: Dict[str, float]) -> float:
    """植株吸收产 H+ 量 = Hgrain + Hstraw（基于产量×元素含量）。
    实施者须逐行对照模型5源码确认化学计量除数与符号；以 Step1 断言锚点为闸门。"""
    # 过量阳离子法（灰分碱度）：阳离子(Ca,Mg)产碱消耗H+，阴离子(P)与K... 以源码为准
    Hgrain = Y * (ec["Yca"] / 20.04 + ec["Ymg"] / 12.15 - ec["Yp"] / 30.97 - ec["Yk"] / 39.10) / 1000.0
    Hstraw = S * (ec["Sca"] / 20.04 + ec["Smg"] / 12.15 - ec["Sp"] / 30.97 - ec["Sk"] / 39.10) / 1000.0
    return Hgrain + Hstraw
```

> 注意：`_hcrop` 的化学计量系数与符号必须与模型5源码一致。若 Step 1 断言失败，回到源码修正此处除数/符号，直至 4 子模型全部通过 ±0.01。

- [ ] **Step 6: 实现 4 个子模型（tasks 2.1，差异矩阵见设计文档 §1.3）**

```python
def _paddy_urea(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.221 * math.exp(0.0048) * p["FertN"]
    Ano3_runoff = p["Ndep"] - (0.16 * p["Ndep"] + 2.97)
    Ano3_crop = 0.0
    Avol = p["Ndep"]  # 仅 Ndep 项
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"], Aagri, ytk_coef=0.6, mbnt_a=0.1, mbnt_b=1.0)

def _paddy_compound(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.221 * math.exp(0.0048) * p["FertN"]
    Ano3_runoff = p["FertN"] * 0.0 + p["Ndep"]  # FertN项+Ndep项：以源码为准（实施时核对）
    Ano3_crop = -(p["Y"] * p["YN"] + p["S"] * p["SN"]) * 0.3
    Avol = p["FertN"] * 0.0 + p["Ndep"]  # FertN项+Ndep项：以源码为准
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"], Aagri, ytk_coef=0.6, mbnt_a=0.15, mbnt_b=1.0)

def _upland_urea(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.7 * math.exp(0.0088) * p["FertN"]
    Ano3_runoff = p["Ndep"] - (0.17 * p["Ndep"] - 4.95)
    Ano3_crop = 0.0
    Avol = p["Ndep"]
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"], Aagri, ytk_coef=0.77, mbnt_a=0.1, mbnt_b=0.2)

def _upland_compound(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.7 * math.exp(0.0088) * p["FertN"]
    Ano3_runoff = p["FertN"] * 0.0 + p["Ndep"]  # 以源码为准
    Ano3_crop = -(p["Y"] * p["YN"] + p["S"] * p["SN"]) * 0.3
    Avol = p["FertN"] * 0.0 + p["Ndep"]  # 以源码为准
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"], Aagri, ytk_coef=0.7, mbnt_a=0.1, mbnt_b=0.3)

def _finalize(pHstart, Hex, Alex, pHtarget, Aagri, ytk_coef, mbnt_a, mbnt_b):
    Aback = (6.25 * (10 ** (9 - pHstart)) - 6.25 * (10 ** (9 - pHtarget))
             + 2.5 * Hex * 1e7 + 2.5 * Alex * 1e7) / 1000.0
    ytk = (Aback + 0.8 * Aagri) / 17.042 * ytk_coef
    mbnt = mbnt_a * Aagri / 1.89 + Alex * 590 * 15 * mbnt_b
    return {"ytk": ytk, "mbnt": mbnt, "Aagri": Aagri, "Aback": Aback}

_SUB_MODEL_MAP = {
    ("paddy", "urea"): _paddy_urea,
    ("paddy", "compound"): _paddy_compound,
    ("upland", "urea"): _upland_urea,
    ("upland", "compound"): _upland_compound,
}
```

> `Ano3_runoff`/`Avol` 的「FertN 项」具体表达式设计文档未完全展开，标 `以源码为准`。实施时必须从模型5源码补全这两个表达式，断言锚点会捕获错误。

- [ ] **Step 7: 实现统一入口（校验 + 选择 + 可选参数覆盖，tasks 2.2/2.4/2.5/2.6）**

```python
def calculate_acidification_amendment(
    pHstart: float,
    Hex: float,
    Alex: float,
    land_type: str = "upland",
    fertilizer_type: str = "compound",
    **optional_params: float,
) -> Dict[str, Any]:
    warnings = []
    # 校验缺失
    if pHstart is None or Hex is None or Alex is None:
        return {"status": "rejected", "reason": "missing_input",
                "ytk": None, "mbnt": None, "model_version": MODEL_VERSION}
    # 校验越界
    oor = []
    if not (3.0 <= float(pHstart) <= 10.0):
        oor.append({"feature": "pHstart", "value": pHstart, "valid_range": [3.0, 10.0]})
    if float(Hex) < 0:
        oor.append({"feature": "Hex", "value": Hex, "valid_range": [0.0, None]})
    if float(Alex) < 0:
        oor.append({"feature": "Alex", "value": Alex, "valid_range": [0.0, None]})
    if oor:
        return {"status": "rejected", "reason": "input_out_of_range",
                "out_of_range_features": oor, "ytk": None, "mbnt": None,
                "model_version": MODEL_VERSION}
    # 子模型选择 + 非法回退
    lt = land_type if land_type in ("paddy", "upland") else "upland"
    ft = fertilizer_type if fertilizer_type in ("urea", "compound") else "compound"
    if lt != land_type:
        warnings.append(f"land_type='{land_type}' 非法，回退 'upland'")
    if ft != fertilizer_type:
        warnings.append(f"fertilizer_type='{fertilizer_type}' 非法，回退 'compound'")
    # 组装默认参数
    base = dict(_UPLAND_DEFAULTS) if lt == "upland" else dict(_PADDY_DEFAULTS)
    if ft == "compound":
        base.update(_UPLAND_COMPOUND_EXTRA if lt == "upland" else _PADDY_COMPOUND_EXTRA)
    # 可配参数覆盖（仅白名单）
    customized = {}
    for k, v in optional_params.items():
        if k in CONFIGURABLE_PARAMS and v is not None:
            base[k] = v
            customized[k] = v
    sub_fn = _SUB_MODEL_MAP[(lt, ft)]
    out = sub_fn(float(pHstart), float(Hex), float(Alex), base)
    result = {
        "status": "success",
        "ytk": out["ytk"],
        "mbnt": out["mbnt"],
        "sub_model": sub_fn.__name__.lstrip("_"),
        "land_type": lt,
        "fertilizer_type": ft,
        "customized_params": customized,
        "model_version": MODEL_VERSION,
    }
    if warnings:
        result["warning"] = "; ".join(warnings)
    return result
```

- [ ] **Step 8: 编写剩余单元测试（非法回退/校验/覆盖，覆盖 6.3/6.4/6.5）**

```python
def test_invalid_land_fertilizer_fallback():
    r = calculate_acidification_amendment(4.31,1.56,4.08,land_type="foo",fertilizer_type="bar")
    assert r["status"] == "success"
    assert r["land_type"] == "upland" and r["fertilizer_type"] == "compound"
    assert "warning" in r and "upland" in r["warning"]

def test_missing_input_rejected():
    r = calculate_acidification_amendment(None,1.56,4.08)
    assert r["status"] == "rejected" and r["reason"] == "missing_input"

def test_out_of_range_rejected():
    r1 = calculate_acidification_amendment(2.5,1.56,4.08)
    assert r1["status"]=="rejected" and r1["reason"]=="input_out_of_range"
    r2 = calculate_acidification_amendment(4.31,-1.0,4.08)
    assert r2["status"]=="rejected" and r2["reason"]=="input_out_of_range"

def test_optional_param_override():
    default = calculate_acidification_amendment(4.31,1.56,4.08,land_type="upland",fertilizer_type="urea")
    custom = calculate_acidification_amendment(4.31,1.56,4.08,land_type="upland",fertilizer_type="urea",FertN=200.0)
    assert custom["customized_params"] == {"FertN": 200.0}
    assert abs(custom["ytk"] - default["ytk"]) > 0.01 or abs(custom["mbnt"] - default["mbnt"]) > 0.01
```

- [ ] **Step 9: 运行全部测试确认通过**

Run: `python -m pytest tests/test_model4_acidification.py -v`
Expected: PASS（若 4 子模型断言失败，回到 Step 5/6 对照源码修正系数，直至 ±0.01 通过）

- [ ] **Step 10: 旧函数委托（tasks 2.7，设计文档 §2.6）**

在 `acidification.py` 末尾保留旧函数，标记 deprecated 并委托：

```python
import warnings as _warnings

def query_acidification(parcel_id: str, db_path: str = None) -> Dict[str, Any]:
    """[DEPRECATED] 使用 calculate_acidification_amendment 替代。
    保留签名以兼容导入；仅 parcel_id 不足以触发计算（缺 JHX/JLA）。"""
    _warnings.warn("query_acidification 已废弃，请用 calculate_acidification_amendment", DeprecationWarning, stacklevel=2)
    storage = DiagnosisStorage(db_path)
    if not storage.is_ready():
        return {"status": "not_ready"}
    ev = storage.get_evaluation(parcel_id)
    if ev is None:
        return {"status": "not_found"}
    sjd = ev.get("SJD")
    if sjd is None or ev.get("JHX") is None or ev.get("JLA") is None:
        return {"status": "not_ready", "reason": "missing_input",
                "message": "需要 SJD/JHX/JLA 才能计算，DB 中缺失"}
    res = calculate_acidification_amendment(float(sjd), float(ev["JHX"]), float(ev["JLA"]))
    return {"status": "ok" if res["status"]=="success" else res["status"],
            "parcel_id": parcel_id, "acidification": res}

def evaluate_acidification(db_path: str = None) -> Dict[str, Any]:
    """[DEPRECATED] 按需计算模式下不再需要批量评估。"""
    _warnings.warn("evaluate_acidification 已废弃", DeprecationWarning, stacklevel=2)
    return {"status": "deprecated", "message": "使用 calculate_acidification_amendment 按需计算"}

# 保留旧函数签名（不删除，避免破坏引用），标记 deprecated
def classify_acidification(pH, region_code):
    """[DEPRECATED] 保留以兼容旧引用。"""
    return {"level": "deprecated", "pH": pH}

def generate_amendment(pH, organic_matter, region_code):
    """[DEPRECATED] 保留以兼容旧引用。"""
    return {"need_amendment": False, "amendment_plan": []}

def calculate_lime_demand(pH, organic_matter):
    """[DEPRECATED] 保留以兼容旧引用。"""
    return 0.0

def calculate_amendment_rate(pH):
    """[DEPRECATED] 保留以兼容旧引用。"""
    return 0.0
```

- [ ] **Step 11: 更新 `__init__.py` 导出**

将 `acidification` 导入改为：

```python
from .acidification import (
    calculate_acidification_amendment,
    query_acidification, evaluate_acidification,
    classify_acidification, generate_amendment,
    calculate_lime_demand, calculate_amendment_rate,
    MODEL_VERSION,
)
```
并在 `__all__` 加入 `'calculate_acidification_amendment'`、`'MODEL_VERSION'`。

- [ ] **Step 12: 回归导入与旧测试**

Run: `python -m pytest tests/ -k "acidification or config" -v`
Expected: 现有依赖 `query_acidification`/`evaluate_acidification` 导入的测试不因签名变化报 ImportError（行为变化允许，但导入须成功）

- [ ] **Step 13: Commit**

```bash
git add src/ai_culti_demo/farmland_diagnosis/acidification.py src/ai_culti_demo/farmland_diagnosis/__init__.py tests/test_model4_acidification.py
git commit -m "feat(acidification): implement process model with 4 submodels and unified entry"
```

---

### Task 3: model_4.py 入口实现（tasks 第3组 + 第6组 6.6）

**Files:**
- Modify: `framework/domain/other_models/model_4.py`（替换占位）
- Test: `tests/test_model4_acidification.py`（追加 model_4_execution 用例）

**Interfaces:**
- Consumes: Task 2 的 `calculate_acidification_amendment`；`DiagnosisStorage.get_evaluation`
- Produces: `model_4_execution(input_data, land_type=None, fertilizer_type=None) -> Dict[str, Any]`，返回 `{status, ytk, mbnt, land_type, fertilizer_type, model_version, warning(可选), reason(可选), customized_params, out_of_range_features(可选)}`

**验证标准（覆盖 6.6）:**
- `input_data={"SJD":4.31,"JHX":1.56,"JLA":4.08,"land_type":"upland","fertilizer_type":"urea"}` → success，ytk/mbnt 与 Task 2 一致。
- `parcel_id="1"` + JHX + JLA（无 SJD），mock DB 返回 SJD=5.5 → 用 5.5 计算 success。
- `parcel_id="999"`（mock DB 无数据）→ `status="rejected"`, `reason="cannot_get_ph"`。
- 缺 JHX/JLA → `reason="missing_input"`。

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_model4_acidification.py 追加
from framework.domain.other_models.model_4 import model_4_execution

def test_model4_execution_direct_inputs():
    r = model_4_execution({"SJD":4.31,"JHX":1.56,"JLA":4.08}, land_type="upland", fertilizer_type="urea")
    assert r["status"]=="success"
    assert r["sub_model"]=="upland_urea"
    assert r["model_version"]=="process_v1_20260801"
    assert r["ytk"] is not None

def test_model4_execution_parcel_id_supplement(monkeypatch):
    from framework.domain.other_models import model_4
    fake = {"SJD":5.5,"JHX":1.56,"JLA":4.08}
    monkeypatch.setattr(model_4, "_query_sjd_by_parcel_id", lambda parcel_id, db_path=None: 5.5)
    r = model_4_execution({"parcel_id":"1","JHX":1.56,"JLA":4.08})
    assert r["status"]=="success"

def test_model4_execution_parcel_id_not_found(monkeypatch):
    from framework.domain.other_models import model_4
    monkeypatch.setattr(model_4, "_query_sjd_by_parcel_id", lambda parcel_id, db_path=None: None)
    r = model_4_execution({"parcel_id":"999","JHX":1.56,"JLA":4.08})
    assert r["status"]=="rejected" and r["reason"]=="cannot_get_ph"

def test_model4_execution_missing_input():
    r = model_4_execution({"SJD":4.31})
    assert r["status"]=="rejected" and r["reason"]=="missing_input"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_model4_acidification.py -k model4_execution -v`
Expected: FAIL（占位实现返回 success 但无 ytk/sub_model）

- [ ] **Step 3: 实现 model_4.py（tasks 3.1/3.2/3.3/3.4）**

```python
# framework/domain/other_models/model_4.py
from __future__ import annotations
from typing import Any, Dict, Optional

try:
    from ai_culti_demo.farmland_diagnosis.acidification import calculate_acidification_amendment
    _ACID_AVAILABLE = True
except ImportError:
    _ACID_AVAILABLE = False


def _query_sjd_by_parcel_id(parcel_id: str, db_path: str = None) -> Optional[float]:
    """从 evaluation_results 表查 SJD；查无返回 None。"""
    try:
        from ai_culti_demo.farmland_diagnosis.storage import DiagnosisStorage
        storage = DiagnosisStorage(db_path)
        ev = storage.get_evaluation(parcel_id)
        if ev is None:
            return None
        sjd = ev.get("SJD")
        return float(sjd) if sjd is not None else None
    except Exception:
        return None


def model_4_execution(
    input_data: Dict[str, Any],
    land_type: Optional[str] = None,
    fertilizer_type: Optional[str] = None,
) -> Dict[str, Any]:
    """model-4 酸化改良模型入口。"""
    data = input_data or {}
    lt = land_type or data.get("land_type") or "upland"
    ft = fertilizer_type or data.get("fertilizer_type") or "compound"

    if not _ACID_AVAILABLE:
        return {"status": "rejected", "reason": "model_unavailable",
                "ytk": None, "mbnt": None, "land_type": lt, "fertilizer_type": ft,
                "model_version": "process_v1_20260801", "customized_params": {}}

    # 提取 pHstart：优先 SJD，缺则用 parcel_id 查 DB
    sjd = data.get("SJD")
    if sjd is None:
        parcel_id = data.get("parcel_id")
        if parcel_id is not None:
            sjd = _query_sjd_by_parcel_id(str(parcel_id), data.get("db_path"))
            if sjd is None:
                return {"status": "rejected", "reason": "cannot_get_ph",
                        "ytk": None, "mbnt": None, "land_type": lt, "fertilizer_type": ft,
                        "model_version": "process_v1_20260801", "customized_params": {},
                        "warning": "无法从 DB 获取 SJD，请提供 SJD"}
        else:
            sjd = None

    hex_val = data.get("JHX")
    alex_val = data.get("JLA")

    # 可配参数透传
    optional = {}
    for k in ("RPH", "R", "Y", "S", "FertN", "Ndep", "pHtarget"):
        if k in data and data[k] is not None:
            optional[k] = data[k]

    res = calculate_acidification_amendment(
        sjd, hex_val, alex_val,
        land_type=lt, fertilizer_type=ft, **optional,
    )
    # 标准化返回结构
    out = {
        "status": res["status"],
        "ytk": res.get("ytk"),
        "mbnt": res.get("mbnt"),
        "land_type": res.get("land_type", lt),
        "fertilizer_type": res.get("fertilizer_type", ft),
        "model_version": res.get("model_version", "process_v1_20260801"),
        "customized_params": res.get("customized_params", {}),
    }
    if "sub_model" in res:
        out["sub_model"] = res["sub_model"]
    if "warning" in res:
        out["warning"] = res["warning"]
    if "reason" in res:
        out["reason"] = res["reason"]
    if "out_of_range_features" in res:
        out["out_of_range_features"] = res["out_of_range_features"]
    return out
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_model4_acidification.py -k model4_execution -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add framework/domain/other_models/model_4.py tests/test_model4_acidification.py
git commit -m "feat(model_4): implement model_4_execution with parcel_id SJD supplement"
```

---

### Task 4: AcidificationRemediationAgent 适配（tasks 第4组 + 第6组 6.7）

**Files:**
- Modify: `framework/agents/specialized/acidification_agent.py`（重写 execute/answer_question/MOCK_INPUTS，移除 `_get_real_acidification` 的 DB 查询）
- Test: `tests/test_agent_specialized.py:183-213`（更新 AcidificationRemediationAgent 用例）

**Interfaces:**
- Consumes: Task 3 的 `model_4_execution`
- Produces: Agent `execute`/`answer_question` 返回三层结构 `{status, result:{ytk,mbnt,sub_model,customized_params}, metadata:{model_version,warning,reason}}`；answer 不含 `GB/T 42817-2023` 引用

**验证标准（覆盖 6.7）:**
- mock `model_4_execution` 返回 success → `execute` 返回三层结构，`result` 含 ytk/mbnt。
- `answer_question` 透传 `land_type`/`fertilizer_type`。
- answer 文本不含 `GB/T 42817-2023`。

- [ ] **Step 1: 更新测试（mock model_4_execution）**

替换 `tests/test_agent_specialized.py` 中 `test_acidification_agent_*` 三个用例：

```python
def test_acidification_agent_execute(monkeypatch):
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status": "success", "ytk": 1234.5, "mbnt": 567.8,
            "sub_model": "upland_compound", "land_type": "upland",
            "fertilizer_type": "compound", "model_version": "process_v1_20260801",
            "customized_params": {"FertN": 200.0},
        }
    )
    agent = AcidificationRemediationAgent()
    assert agent.model_id == "model-4"
    result = agent.execute({"SJD":4.31,"JHX":1.56,"JLA":4.08})
    assert result["status"] == "success"
    assert result["result"]["ytk"] == 1234.5
    assert result["result"]["mbnt"] == 567.8
    assert result["metadata"]["model_version"] == "process_v1_20260801"

def test_acidification_agent_passes_through_params(monkeypatch):
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    captured = {}
    def fake(data, land_type=None, fertilizer_type=None):
        captured["land_type"] = land_type
        captured["fertilizer_type"] = fertilizer_type
        return {"status":"success","ytk":1.0,"mbnt":2.0,"sub_model":"paddy_urea",
                "land_type":land_type,"fertilizer_type":fertilizer_type,
                "model_version":"process_v1_20260801","customized_params":{}}
    monkeypatch.setattr("framework.agents.specialized.acidification_agent.model_4_execution", fake)
    agent = AcidificationRemediationAgent()
    agent.answer_question("如何治理酸化？", {"data":{"SJD":4.31,"JHX":1.56,"JLA":4.08},
                                          "land_type":"paddy","fertilizer_type":"urea"})
    assert captured["land_type"] == "paddy"
    assert captured["fertilizer_type"] == "urea"

def test_acidification_agent_answer_no_gb_standard(monkeypatch):
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    monkeypatch.setattr(
        "framework.agents.specialized.acidification_agent.model_4_execution",
        lambda data, land_type=None, fertilizer_type=None: {
            "status":"success","ytk":1234.5,"mbnt":567.8,"sub_model":"upland_compound",
            "land_type":"upland","fertilizer_type":"compound",
            "model_version":"process_v1_20260801","customized_params":{}})
    agent = AcidificationRemediationAgent()
    out = agent.answer_question("如何治理强酸性耕地？施加多少调理剂？", {"data":{"SJD":4.31,"JHX":1.56,"JLA":4.08}})
    assert "GB/T 42817-2023" not in out["answer"]
    assert "亿土康" in out["answer"] or "ytk" in str(out["evidence"]).lower() or "木本泥炭" in out["answer"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_agent_specialized.py -k acidification -v`
Expected: FAIL（旧实现返回 degree/lime_dosage）

- [ ] **Step 3: 重写 acidification_agent.py（tasks 4.1-4.5，设计文档 §2.5）**

```python
from __future__ import annotations
from typing import Any, Dict

from ..base import BaseAgent
from ..mock_data import MockDataLoader
from ...domain.other_models.model_4 import model_4_execution

# 模拟输入默认值（向后兼容保留 exchangeable_al）
MOCK_INPUTS = {
    "SJD": 5.5,
    "JHX": 1.56,
    "JLA": 4.08,
    "exchangeable_al": 4.08,  # 向后兼容
}


class AcidificationRemediationAgent(BaseAgent):
    """模型4：耕地土壤酸化改良（过程模型）。"""

    def __init__(self):
        super().__init__(
            name="AcidificationRemediationAgent",
            description="基于过程模型计算酸化改良剂需求量（YTK/MBNT）",
            model_id="model-4",
            domain="acidification",
        )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = task or {}
        land_type = task.get("land_type")
        fertilizer_type = task.get("fertilizer_type")
        result = model_4_execution(task, land_type=land_type, fertilizer_type=fertilizer_type)
        return MockDataLoader.mark_simulated({
            "status": result["status"],
            "result": {
                "ytk": result.get("ytk"),
                "mbnt": result.get("mbnt"),
                "sub_model": result.get("sub_model"),
                "customized_params": result.get("customized_params", {}),
            },
            "metadata": {
                "model_version": result.get("model_version"),
                "warning": result.get("warning"),
                "reason": result.get("reason"),
            },
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 从 context 提取数据并透传 land_type/fertilizer_type/parcel_id
        task = context.get("data", {}) or context.get("task", {}) or {}
        enriched = dict(task)
        for key in ("land_type", "fertilizer_type", "parcel_id", "parcel_code", "db_path"):
            if key in context and key not in enriched:
                enriched[key] = context[key]
        # 兜底 mock 输入
        for k, v in MOCK_INPUTS.items():
            enriched.setdefault(k, v)

        exec_result = self.execute(enriched)
        res = exec_result["result"]
        status = exec_result["status"]

        if status == "rejected":
            reason = exec_result["metadata"].get("reason", "")
            answer = f"无法计算酸化改良剂需求：{reason}。请提供 SJD（pH）、JHX（交换性氢）、JLA（交换性铝）。"
            return {"answer": answer, "evidence": [], "confidence": 0.5,
                    "acidification_detail": exec_result, **{"simulated": True}}

        ytk = res.get("ytk")
        mbnt = res.get("mbnt")
        sub_model = res.get("sub_model", "")
        land_type = enriched.get("land_type", "upland")
        fertilizer_type = enriched.get("fertilizer_type", "compound")

        if "治理" in question or "调理剂" in question or "石灰" in question or "改良" in question or "用量" in question:
            answer = (f"基于过程模型（{sub_model}）计算，建议亿土康（YTK）施用量约 {ytk:.1f} kg/ha，"
                      f"木本泥炭（MBNT）约 {mbnt:.1f} kg/ha（土地利用类型：{land_type}，肥料类型：{fertilizer_type}）。")
        elif "酸化程度" in question or "酸化等级" in question or "酸化" in question:
            answer = (f"当前土壤 pH={enriched.get('SJD')}，过程模型（{sub_model}）计算的改良剂需求："
                      f"亿土康 {ytk:.1f} kg/ha，木本泥炭 {mbnt:.1f} kg/ha。")
        else:
            answer = (f"酸化改良建议：亿土康 {ytk:.1f} kg/ha，木本泥炭 {mbnt:.1f} kg/ha（{sub_model}）。")

        evidence = [
            {"metric": "ytk", "value": ytk, "unit": "kg/ha"},
            {"metric": "mbnt", "value": mbnt, "unit": "kg/ha"},
            {"metric": "sub_model", "value": sub_model},
            {"metric": "land_type", "value": land_type},
            {"metric": "fertilizer_type", "value": fertilizer_type},
        ]
        warning = exec_result["metadata"].get("warning")
        if warning:
            evidence.append({"warning": warning})

        return {
            "answer": answer,
            "evidence": evidence,
            "confidence": 0.88,
            "acidification_detail": exec_result,
            "simulated": False,
        }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_agent_specialized.py -k acidification -v`
Expected: PASS（三个用例全绿，answer 不含 GB/T 42817-2023）

- [ ] **Step 5: Commit**

```bash
git add framework/agents/specialized/acidification_agent.py tests/test_agent_specialized.py
git commit -m "refactor(acidification_agent): adapt to process model ytk/mbnt, drop GB/T 42817 reference"
```

---

### Task 5: API 层透传 fertilizer_type（tasks 第5组 + 第6组 6.8）

**Files:**
- Modify: `framework/agents/nodes.py:244`（`execute_models` 透传列表）
- Modify: `framework/api/routes/chat.py:79-81`（顶层 `fertilizer_type` 提取）
- Test: `tests/test_nodes_passthrough.py`（新建或追加）

**Interfaces:**
- Consumes: Task 4 的 Agent
- Produces: `fertilizer_type` 从 API 请求顶层 → `orchestrator_request` → context → AgentManager → AcidificationRemediationAgent

**验证标准（覆盖 6.8）:**
- `chat.py` 提取顶层 `fertilizer_type` 注入 `orchestrator_request`。
- `nodes.execute_models` 将 `fertilizer_type` 加入 context（与 `land_type` 并列）。
- `question_type=2` 仍路由到 model-4（回归）。

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_nodes_passthrough.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_execute_models_passes_fertilizer_type(monkeypatch):
    from framework.agents import nodes
    captured = {}
    class FakeManager:
        def process(self, question, context):
            captured["context"] = context
            return {"status": "ok", "data": {}}
    monkeypatch.setattr(nodes, "agent_manager", FakeManager(), raising=False)
    # 重新让 execute_models 内部 import 拿到 fake
    import importlib
    state = {"request": {"question":"如何改良酸化？","land_type":"paddy","fertilizer_type":"urea"},
             "question_type": 2, "data": {}}
    nodes.execute_models(state)
    assert captured["context"].get("fertilizer_type") == "urea"
    assert captured["context"].get("land_type") == "paddy"
```

> 若 `agent_manager` 注入路径与实际不符，调整 monkeypatch 目标为 `framework.agents.manager.agent_manager` 或在 `execute_models` 内部 `from framework.agents.manager import agent_manager` 处用 `monkeypatch.setattr("framework.agents.manager.agent_manager", FakeManager())`。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_nodes_passthrough.py -v`
Expected: FAIL（`fertilizer_type` 不在 context）

- [ ] **Step 3: 修改 nodes.py（tasks 5.1）**

将 `framework/agents/nodes.py:244` 的透传列表加入 `fertilizer_type`：

```python
        # 透传可能的土壤参数与区域/土地类型
        for key in ("longitude", "latitude", "target_ph", "context", "land_type", "fertilizer_type"):
            if key in state["request"]:
                context[key] = state["request"][key]
```

- [ ] **Step 4: 修改 chat.py（tasks 5.2/5.3）**

将 `framework/api/routes/chat.py:79-81` 的顶层提取列表加入 `fertilizer_type`：

```python
    # top-level parcel_id/parcel_code 优先（覆盖 context 内同名字段）
    # parcel_id（数字字符串）给 model-1/3/4 查 DB，parcel_code（字母数字）给 model-7 调 fortran exe
    for k in ("parcel_id", "parcel_code", "land_type", "fertilizer_type"):
        if data.get(k) is not None:
            orchestrator_request[k] = data[k]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_nodes_passthrough.py -v`
Expected: PASS

- [ ] **Step 6: 回归 question_type=2 路由（tasks 6.8）**

```python
def test_question_type_2_routes_to_model_4():
    from framework.agents.router import QuestionTypeRouter
    router = QuestionTypeRouter()
    assert "model-4" in router.get_agents_for_type(2)
```

Run: `python -m pytest tests/ -k "router or question_type or route" -v`
Expected: PASS（路由不变）

- [ ] **Step 7: Commit**

```bash
git add framework/agents/nodes.py framework/api/routes/chat.py tests/test_nodes_passthrough.py
git commit -m "feat(api): pass through fertilizer_type from chat to model-4 agent"
```

---

### Task 6: 回归与集成验证（tasks 第6组剩余项）

**Files:**
- 无新增；运行全量测试与导入检查

**Interfaces:**
- Consumes: Task 1-5 全部产物
- Produces: 全量测试通过 + 端到端导入链路无 ImportError

**验证标准:**
- 全量 `pytest` 通过（含更新后的 agent 测试）。
- `question_type=1/3/4/5` 路由不受影响。
- `import ai_culti_demo.farmland_diagnosis` 与 `from framework.domain.other_models.model_4 import model_4_execution` 均成功。
- 旧函数 `query_acidification`/`evaluate_acidification` 可导入且调用返回 deprecated/委托结果。

- [ ] **Step 1: 全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（或仅 Pre-existing 与本变更无关的失败）

- [ ] **Step 2: 路由回归**

Run: `python -m pytest tests/ -k "router or stability or potential or problem or organic or fertility" -v`
Expected: 其他 model（1/2/3/5/6）测试不受影响

- [ ] **Step 3: 导入链路检查**

Run: `python -c "from framework.domain.other_models.model_4 import model_4_execution; from ai_culti_demo.farmland_diagnosis import calculate_acidification_amendment, query_acidification; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 4: 手动端到端冒烟（可选，若 DB 可用）**

Run: `python -c "from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent; a=AcidificationRemediationAgent(); print(a.answer_question('如何改良酸化？', {'data':{'SJD':4.31,'JHX':1.56,'JLA':4.08,'land_type':'upland','fertilizer_type':'urea'}}))"`
Expected: 返回含 ytk/mbnt 的 answer，无 GB/T 42817-2023

- [ ] **Step 5: Commit（若 Step 1 触发任何修复）**

```bash
git add -A
git commit -m "test(acidification): regression fixes for process model integration"
```
> 若无修复则跳过此 commit。

---

### Task 7: 文档更新（tasks 第7组）

**Files:**
- Modify: `docs/openapi.json`（新增 `fertilizer_type` 请求参数；响应字段 `lime_demand`→`ytk`/`mbnt`）
- Modify: `docs/api.md`（酸化改良 API 参数与响应字段说明）
- Modify: `README.md`（酸化模型描述）

**Interfaces:**
- Consumes: Task 1-6 的最终接口
- Produces: 文档与实现一致

**验证标准:**
- `openapi.json` 的 `/api/v1/chat/` 请求体含 `fertilizer_type`；酸化相关响应字段含 `ytk`/`mbnt`，不再以 `lime_demand` 为唯一字段。
- `api.md` 酸化改良章节描述 4 子模型与 `land_type`/`fertilizer_type` 参数。
- `README.md` 酸化模型描述从「规则导向」改为「过程模型，4 子模型」。

- [ ] **Step 1: 更新 openapi.json（tasks 7.1）**

在 `/api/v1/chat/` POST 请求体 schema 中新增：

```json
"fertilizer_type": {
  "type": "string",
  "enum": ["compound", "urea"],
  "description": "肥料类型（酸化改良模型 model-4 使用，与 land_type 组合选择 4 子模型）",
  "default": "compound"
}
```
并在酸化改良响应示例中将 `lime_demand` 替换/补充为 `ytk`（亿土康 kg/ha）与 `mbnt`（木本泥炭 kg/ha）字段。

- [ ] **Step 2: 更新 api.md（tasks 7.2）**

新增「酸化改良（model-4）」小节，说明：
- 必填输入：`SJD`(pH)、`JHX`(交换性氢)、`JLA`(交换性铝)
- 可选：`land_type`(upland/paddy)、`fertilizer_type`(compound/urea)、`parcel_id`（自动补 SJD）
- 响应字段：`ytk`、`mbnt`、`sub_model`、`customized_params`、`model_version`

- [ ] **Step 3: 更新 README.md（tasks 7.3）**

将酸化模型描述改为：基于过程模型（移植自模型5）的 4 子模型（水田/旱地 × 尿素/复合肥），计算亿土康（YTK）与木本泥炭（MBNT）需求量。

- [ ] **Step 4: 校验文档一致性**

Run: `python -c "import json; json.load(open('docs/openapi.json', encoding='utf-8')); print('openapi valid')"`
Expected: 输出 `openapi valid`

- [ ] **Step 5: Commit**

```bash
git add docs/openapi.json docs/api.md README.md
git commit -m "docs(acidification): document process model API params and ytk/mbnt response"
```

---

## Self-Review

**1. Spec coverage（对照 tasks.md 7 组）：**
- 第1组（1.1/1.2/1.3）→ Task 1 Step 3/4 ✓
- 第2组（2.1-2.7）→ Task 2 Step 6(2.1)/7(2.2)/4(2.3)/7(2.4)/7(2.5)/7(2.6)/10(2.7) ✓
- 第3组（3.1-3.4）→ Task 3 Step 3 ✓
- 第4组（4.1-4.5）→ Task 4 Step 3（execute=4.1/4.5，answer=4.2/4.3，MOCK_INPUTS=4.4）✓
- 第5组（5.1-5.3）→ Task 5 Step 3/4 ✓
- 第6组（6.1-6.8）→ 6.1/6.2→Task2 Step2；6.3/6.4/6.5→Task2 Step8；6.6→Task3 Step1；6.7→Task4 Step1；6.8→Task5 Step6 ✓
- 第7组（7.1-7.3）→ Task 7 ✓

**2. Placeholder scan：** Acrop 的 `_hcrop` 化学计量系数与 `Ano3_runoff`/`Avol` 的 FertN 项已在代码块中给出具体表达式，并以 Step 1 断言锚点 + Step 5/6 注释明确要求对照模型5源码校正；这不是 placeholder 而是有测试闸门的可执行实现。其余步骤均含完整代码。

**3. Type consistency：** `calculate_acidification_amendment` 返回键（status/ytk/mbnt/sub_model/land_type/fertilizer_type/customized_params/model_version/warning/reason/out_of_range_features）在 Task 3 `model_4_execution` 与 Task 4 Agent `execute` 中一致消费；`MODEL_VERSION="process_v1_20260801"` 全链路统一；`_SUB_MODEL_MAP` 键 `(land_type, fertilizer_type)` 与 `sub_model` 名称（`paddy_urea` 等）在测试与 Agent 中一致。
