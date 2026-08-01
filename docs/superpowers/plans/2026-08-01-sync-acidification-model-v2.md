---
change: sync-acidification-model-v2
design-doc: docs/superpowers/specs/2026-08-01-sync-acidification-model-v2-design.md
base-ref: 98f41e19a68a9a089cd89eb7012a4622fb691b02
---

# sync-acidification-model-v2 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将酸化过程模型（model-4）从 v1 (`process_v1_20260801`) 升级到 v2 (`process_v2_20260801`)，新增 `run_csv` 批量 CSV 计算函数与 CLI 脚本，并用 v2 源码的 393 地块数据建立回归测试。

**Architecture:** 子模型函数重构为返回 7 字段 dict（方案 A），提取 `_build_params` 复用参数装配逻辑，新增 `run_csv` 内部函数（不暴露为 HTTP API）和 `scripts/run_acidification_batch.py` CLI 脚本。版本标识在 3 个代码文件 + 2 个文档文件中同步升级。v2 的 393 地块测试数据自包含到 `tests/data/acidification_v2/`，回归测试对比 YTK/MBNT 偏差 < 0.01。

**Tech Stack:** Python 3, pandas 3.0.2, pytest 9.1.1, argparse, src layout（`ai_culti_demo` 包位于 `src/`）

## Global Constraints

- `MODEL_VERSION` 精确值：`process_v2_20260801`（所有代码与文档同步）
- 4 个子模型核心数学公式、默认参数、系数与 v2 源码 `02_酸化模型计算.py` 逐行一致，本变更 SHALL NOT 修改任何公式
- `run_csv` SHALL NOT 通过 HTTP API 暴露，仅作为内部函数和 CLI 工具
- 对外 API 输出结构不变（`calculate_acidification_amendment` 仍只暴露 `ytk/mbnt`，不暴露中间变量）
- 回归测试浮点容差：< 0.01
- CSV 编码：`utf-8-sig`（与 v2 源码一致）
- 结果保留 2 位小数（`round(x, 2)`，与 v2 源码一致）
- 测试数据自包含在 `tests/data/acidification_v2/`，不依赖外部路径

## File Structure

**修改的文件：**
- `src/ai_culti_demo/farmland_diagnosis/acidification.py` — 重构 `_finalize`（返回 7 字段）、4 个子模型函数、提取 `_build_params`、新增 `run_csv`、升级 `MODEL_VERSION`、更新 docstring
- `framework/domain/other_models/model_4.py` — 同步 3 处 fallback 的 `model_version` 字段
- `tests/test_model4_acidification.py` — 更新 2 处版本断言、新增 `run_csv` 基础测试与 393 地块回归测试
- `README.md` — 同步 1 处版本引用
- `docs/api.md` — 同步 3 处版本引用

**新建的文件：**
- `tests/data/acidification_v2/03_Data.csv` — v2 源码 393 地块输入数据（复制）
- `tests/data/acidification_v2/04_upland_compound_expected.csv` — v2 源码旱地+复合肥期望输出（复制自 `04_旱地复合肥计算结果.csv`）
- `scripts/run_acidification_batch.py` — CLI 批量计算脚本

---

## Task 1: 重构 `_finalize` 返回 7 字段（方案 A）

**Files:**
- Modify: `src/ai_culti_demo/farmland_diagnosis/acidification.py:110-178`（`_finalize` 与 4 个子模型函数）

**Interfaces:**
- Consumes: 无（重构内部函数）
- Produces: `_finalize` 新签名 `(pHstart, Hex, Alex, pHtarget, Adep, Acrop, ANcy, Aagri, ytk_coef, mbnt_a, mbnt_b) -> Dict[str, float]`，返回 7 字段 dict（keys: `Adep/Acrop/ANcy/Aagri/Aback/ytk/mbnt`）。4 个子模型函数签名不变，仍返回 dict。`calculate_acidification_amendment` 读取 `out["ytk"]`/`out["mbnt"]` 无需改动。

- [x] **Step 1: 基线测试 — 确认现有测试通过**

Run: `pytest tests/test_model4_acidification.py -v`
Expected: 所有测试 PASS（含 `test_four_submodels_calculation`、`test_submodel_selection`、`test_model_version_present` 等）

- [x] **Step 2: 重构 `_finalize` 签名与返回值**

将 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 第 110-119 行的 `_finalize` 替换为：

```python
def _finalize(pHstart: float, Hex: float, Alex: float, pHtarget: float,
              Adep: float, Acrop: float, ANcy: float, Aagri: float,
              ytk_coef: float, mbnt_a: float, mbnt_b: float) -> Dict[str, float]:
    """计算 Aback 与 YTK/MBNT，返回完整 7 字段 dict。

    返回字段：Adep, Acrop, ANcy, Aagri, Aback, ytk, mbnt。
    中间变量由调用方（4 个子模型）计算后传入，本函数只负责 Aback/YTK/MBNT 收尾。
    """
    Aback = (6.25 * (10 ** (9 - pHstart))
             - 6.25 * (10 ** (9 - pHtarget))
             + 2.5 * Hex * 1e7
             + 2.5 * Alex * 1e7) / 1000.0
    ytk = (Aback + 0.8 * Aagri) / 17.042 * ytk_coef
    mbnt = mbnt_a * Aagri / 1.89 + Alex * 590 * 15 * mbnt_b
    return {"Adep": Adep, "Acrop": Acrop, "ANcy": ANcy, "Aagri": Aagri,
            "Aback": Aback, "ytk": ytk, "mbnt": mbnt}
```

- [x] **Step 3: 适配 `_paddy_urea` 传入 4 个中间变量**

将第 125-135 行的 `_paddy_urea` 替换为（仅改 `_finalize` 调用行，公式不变）：

```python
def _paddy_urea(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.221 * math.exp(0.0048 * (p["FertN"] + p["Ndep"])) * 1000 / 14
    Ano3_runoff = (p["Ndep"] - (0.16 * p["Ndep"] + 2.97)) * 1000 / 14 * 2
    Ano3_crop = 0.0
    Avol = (p["Ndep"] - (0.16 * p["Ndep"] + 2.97)) * 1000 / 14 * 2
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"],
                     Adep, Acrop, ANcy, Aagri,
                     ytk_coef=0.6, mbnt_a=0.1, mbnt_b=1.0)
```

- [x] **Step 4: 适配 `_paddy_compound` 传入 4 个中间变量**

将第 138-150 行的 `_paddy_compound` 替换为：

```python
def _paddy_compound(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.221 * math.exp(0.0048 * (p["FertN"] + p["Ndep"])) * 1000 / 14
    Ano3_crop = -(p["Y"] * p["YN"] + p["S"] * p["SN"]) * 1000 / 100 / 14 * 0.3
    Ano3_runoff = ((p["FertN"] - (0.16 * p["FertN"] + 2.97)) * 1000 / 14 * 2 * 0.3
                   + (p["Ndep"] - (0.16 * p["Ndep"] + 2.97)) * 1000 / 14 * 2)
    Avol = ((0.16 * p["FertN"] + 2.97) * 1000 / 14 * 0.3
            + (0.16 * p["Ndep"] + 2.97) * 1000 / 14)
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"],
                     Adep, Acrop, ANcy, Aagri,
                     ytk_coef=0.6, mbnt_a=0.15, mbnt_b=1.0)
```

- [x] **Step 5: 适配 `_upland_urea` 传入 4 个中间变量**

将第 153-163 行的 `_upland_urea` 替换为：

```python
def _upland_urea(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.7 * math.exp(0.0088 * (p["FertN"] + p["Ndep"])) * 1000 / 14
    Ano3_runoff = (p["Ndep"] - (0.17 * p["Ndep"] - 4.95)) * 1000 / 14 * 2
    Ano3_crop = 0.0
    Avol = (0.17 * p["Ndep"] - 4.95) * 1000 / 14
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"],
                     Adep, Acrop, ANcy, Aagri,
                     ytk_coef=0.77, mbnt_a=0.1, mbnt_b=0.2)
```

- [x] **Step 6: 适配 `_upland_compound` 传入 4 个中间变量**

将第 166-178 行的 `_upland_compound` 替换为：

```python
def _upland_compound(pHstart, Hex, Alex, p):
    Adep = _adep(p["RPH"], p["R"])
    Acrop = _hcrop(p["Y"], p["S"], p)
    Anit = 2.7 * math.exp(0.0088 * (p["FertN"] + p["Ndep"])) * 1000 / 14
    Ano3_crop = -(p["Y"] * p["YN"] + p["S"] * p["SN"]) * 1000 / 100 / 14 * 0.3
    Ano3_runoff = ((p["FertN"] - (0.17 * p["FertN"] - 4.95)) * 1000 / 14 * 2 * 0.3
                   + (p["Ndep"] - (0.17 * p["Ndep"] - 4.95)) * 1000 / 14 * 2)
    Avol = ((0.17 * p["FertN"] - 4.95) * 1000 / 14 * 0.3
            + (0.17 * p["Ndep"] - 4.95) * 1000 / 14)
    ANcy = Anit + Ano3_runoff + Ano3_crop + Avol
    Aagri = Adep + Acrop + ANcy
    return _finalize(pHstart, Hex, Alex, p["pHtarget"],
                     Adep, Acrop, ANcy, Aagri,
                     ytk_coef=0.7, mbnt_a=0.1, mbnt_b=0.3)
```

- [x] **Step 7: 运行测试确认无回归**

Run: `pytest tests/test_model4_acidification.py -v`
Expected: 所有测试 PASS（`calculate_acidification_amendment` 读取 `out["ytk"]`/`out["mbnt"]`，7 字段 dict 仍含这两个 key，无破坏）

- [x] **Step 8: Commit**

```bash
git add src/ai_culti_demo/farmland_diagnosis/acidification.py
git commit -m "refactor(acidification): _finalize 返回 7 字段 dict，4 子模型传入中间变量

方案 A 重构：_finalize 签名扩展为接收 Adep/Acrop/ANcy/Aagri，
返回完整 7 字段 dict（含中间变量），为 run_csv 批量计算输出中间变量做准备。
公式与系数不变，现有测试全部通过。"
```

---

## Task 2: 提取 `_build_params` 参数装配函数

**Files:**
- Modify: `src/ai_culti_demo/farmland_diagnosis/acidification.py`（新增 `_build_params`，重构 `calculate_acidification_amendment` 第 231-234 行）

**Interfaces:**
- Consumes: Task 1 的 4 个子模型函数（无变化）
- Produces: `_build_params(land_type: str, fertilizer_type: str) -> Dict[str, float]`，返回默认参数 dict 副本（不含可配覆盖）。`calculate_acidification_amendment` 与后续 Task 4 的 `run_csv` 均复用此函数。

- [x] **Step 1: 基线测试 — 确认现有测试通过**

Run: `pytest tests/test_model4_acidification.py -v`
Expected: 所有测试 PASS

- [x] **Step 2: 新增 `_build_params` 函数**

在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 的 `_SUB_MODEL_MAP` 定义之前（第 180 行附近，`_upland_compound` 函数之后）插入：

```python
def _build_params(land_type: str, fertilizer_type: str) -> Dict[str, float]:
    """组装默认参数（不含可配覆盖）。

    land_type: "paddy" 或 "upland"
    fertilizer_type: "urea" 或 "compound"
    返回：含基础默认参数 + 复合肥额外参数（若 compound）的 dict 副本。
    """
    base: Dict[str, float] = dict(_UPLAND_DEFAULTS) if land_type == "upland" else dict(_PADDY_DEFAULTS)
    if fertilizer_type == "compound":
        base.update(_UPLAND_COMPOUND_EXTRA if land_type == "upland" else _PADDY_COMPOUND_EXTRA)
    return base
```

- [x] **Step 3: 重构 `calculate_acidification_amendment` 复用 `_build_params`**

将 `calculate_acidification_amendment` 中第 231-234 行（`# 4. 组装默认参数` 注释下方的 3 行）：

```python
    base: Dict[str, float] = dict(_UPLAND_DEFAULTS) if lt == "upland" else dict(_PADDY_DEFAULTS)
    if ft == "compound":
        base.update(_UPLAND_COMPOUND_EXTRA if lt == "upland" else _PADDY_COMPOUND_EXTRA)
```

替换为：

```python
    base = _build_params(lt, ft)
```

- [x] **Step 4: 运行测试确认无回归**

Run: `pytest tests/test_model4_acidification.py -v`
Expected: 所有测试 PASS（参数装配逻辑等价，`test_optional_param_override` 验证可配覆盖仍生效）

- [x] **Step 5: Commit**

```bash
git add src/ai_culti_demo/farmland_diagnosis/acidification.py
git commit -m "refactor(acidification): 提取 _build_params 复用参数装配逻辑

calculate_acidification_amendment 与 run_csv 共享默认参数组装，
消除重复代码。行为不变，现有测试全部通过。"
```

---

## Task 3: 版本标识升级与文档同步

**Files:**
- Modify: `src/ai_culti_demo/farmland_diagnosis/acidification.py:2-6,29`（docstring + MODEL_VERSION）
- Modify: `framework/domain/other_models/model_4.py:38,49,74`（3 处 fallback model_version）
- Modify: `tests/test_model4_acidification.py:90,101`（2 处版本断言）
- Modify: `README.md:259`（1 处版本引用）
- Modify: `docs/api.md:399,438,464`（3 处版本引用）

**Interfaces:**
- Consumes: 无
- Produces: `MODEL_VERSION = "process_v2_20260801"`（全局常量，所有下游通过 `calculate_acidification_amendment` 返回的 `model_version` 字段获得新版本）

- [x] **Step 1: 更新测试断言为 v2（使测试先失败）**

在 `tests/test_model4_acidification.py` 中：

第 90 行，将：
```python
    assert r.get("model_version") == "process_v1_20260801"
```
改为：
```python
    assert r.get("model_version") == "process_v2_20260801"
```

第 101 行，将：
```python
    assert r["model_version"] == "process_v1_20260801"
```
改为：
```python
    assert r["model_version"] == "process_v2_20260801"
```

- [x] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_model4_acidification.py::test_model_version_present tests/test_model4_acidification.py::test_model4_execution_direct_inputs -v`
Expected: 两个测试 FAIL（代码仍返回 `process_v1_20260801`）

- [x] **Step 3: 升级 `acidification.py` 的 `MODEL_VERSION`**

在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 第 29 行，将：
```python
MODEL_VERSION = "process_v1_20260801"
```
改为：
```python
MODEL_VERSION = "process_v2_20260801"
```

- [x] **Step 4: 更新 `acidification.py` 模块 docstring 源码路径引用**

在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 第 2-6 行，将：
```python
"""酸化改良过程模型。

本模块用过程模型（移植自模型5源码
D:\\destkop\\模型5\\模型5\\02_酸化模型计算-地块.py）替换旧的酸化改良经验逻辑。
```
改为：
```python
"""酸化改良过程模型。

本模块用过程模型（移植自模型5 v2 源码
D:\\destkop\\模型5_酸化模型_v2_20260801\\模型5_酸化模型_v2_20260801\\02_酸化模型计算.py）
替换旧的酸化改良经验逻辑。原理文档 01_产酸过程计算公式.docx 有笔误，以源码为准。
```

- [x] **Step 5: 同步 `model_4.py` 的 3 处 fallback `model_version`**

在 `framework/domain/other_models/model_4.py` 中，将 3 处 `"process_v1_20260801"` 改为 `"process_v2_20260801"`：

第 38 行（model_unavailable fallback）：
```python
                "model_version": "process_v2_20260801", "customized_params": {}}
```

第 49 行（cannot_get_ph fallback）：
```python
                        "model_version": "process_v2_20260801", "customized_params": {},
```

第 74 行（默认 fallback）：
```python
        "model_version": res.get("model_version", "process_v2_20260801"),
```

- [x] **Step 6: 运行测试确认版本断言通过**

Run: `pytest tests/test_model4_acidification.py -v`
Expected: 所有测试 PASS（含 `test_model_version_present`、`test_model4_execution_direct_inputs`）

- [x] **Step 7: 同步 `README.md` 版本引用**

在 `README.md` 第 259 行，将：
```
模型版本 `process_v1_20260801`。
```
改为：
```
模型版本 `process_v2_20260801`。
```

- [x] **Step 8: 同步 `docs/api.md` 的 3 处版本引用**

在 `docs/api.md` 中，将 3 处 `process_v1_20260801` 改为 `process_v2_20260801`：

第 399 行：
```
| `acidification_detail.metadata.model_version` | string | 过程模型版本号（`process_v2_20260801`） |
```

第 438 行：
```
                                "model_version": "process_v2_20260801",
```

第 464 行：
```
            "model_version": "process_v2_20260801",
```

- [x] **Step 9: 全局搜索确认无遗漏的 v1 引用**

Run: `Select-String -Path "d:\17417\Documents\agent_culti_demo\src\ai_culti_demo\farmland_diagnosis\acidification.py","d:\17417\Documents\agent_culti_demo\framework\domain\other_models\model_4.py","d:\17417\Documents\agent_culti_demo\tests\test_model4_acidification.py","d:\17417\Documents\agent_culti_demo\README.md","d:\17417\Documents\agent_culti_demo\docs\api.md" -Pattern "process_v1_20260801" -SimpleMatch`
Expected: 无输出（所有 v1 引用已清除）

- [x] **Step 10: Commit**

```bash
git add src/ai_culti_demo/farmland_diagnosis/acidification.py framework/domain/other_models/model_4.py tests/test_model4_acidification.py README.md docs/api.md
git commit -m "feat(acidification): MODEL_VERSION 升级为 process_v2_20260801

同步 acidification.py / model_4.py / 测试断言 / README / api.md 中的
版本标识与 docstring 源码路径引用。v2 与 v1 公式一致，仅版本号变更。"
```

---

## Task 4: `run_csv` 函数实现（含测试数据准备）

**Files:**
- Create: `tests/data/acidification_v2/03_Data.csv`（复制自 v2 源码）
- Create: `tests/data/acidification_v2/04_upland_compound_expected.csv`（复制自 v2 源码）
- Modify: `src/ai_culti_demo/farmland_diagnosis/acidification.py`（新增 `run_csv` 函数）
- Modify: `tests/test_model4_acidification.py`（新增 `V2_DATA_DIR` 常量与 `test_run_csv_basic` 测试）

**Interfaces:**
- Consumes: Task 1 的 4 个子模型函数（返回 7 字段 dict）、Task 2 的 `_build_params`、现有 `_SUB_MODEL_MAP`
- Produces: `run_csv(input_file: str, output_file: str, land_type: str, fertilizer_type: str) -> pd.DataFrame`。读取 CSV → 批量计算 → 写出 CSV → 返回 DataFrame。输出列含输入列 + `Adep/Acrop/ANcy/Aagri/Aback/YTK/MBNT`，NaN 行输出 7 个 None，不做越界校验。

- [x] **Step 1: 创建测试数据目录并复制 v2 数据文件**

Run:
```bash
New-Item -ItemType Directory -Path "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2" -Force
Copy-Item "D:\destkop\模型\模型5_酸化模型_v2_20260801\模型5_酸化模型_v2_20260801\03_Data.csv" "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\03_Data.csv"
Copy-Item "D:\destkop\模型\模型5_酸化模型_v2_20260801\模型5_酸化模型_v2_20260801\04_旱地复合肥计算结果.csv" "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\04_upland_compound_expected.csv"
```

- [x] **Step 2: 验证复制的测试数据完整性**

Run:
```bash
python -c "import pandas as pd; df=pd.read_csv(r'd:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\03_Data.csv', encoding='utf-8-sig'); print('input rows:', len(df), 'cols:', list(df.columns)); exp=pd.read_csv(r'd:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\04_upland_compound_expected.csv', encoding='utf-8-sig'); print('expected rows:', len(exp), 'cols:', list(exp.columns))"
```
Expected: input rows: 393, cols: `['TYBH', 'SJD', 'Hex', 'Alex']`；expected rows: 393, cols: `['TYBH', 'SJD', 'Hex', 'Alex', 'Adep', 'Acrop', 'ANcy', 'Aagri', 'Aback', 'YTK', 'MBNT']`

- [x] **Step 3: 在测试文件中新增 `V2_DATA_DIR` 常量与 pandas/pytest 导入**

在 `tests/test_model4_acidification.py` 顶部导入区（第 8-11 行附近），将：
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import math
from ai_culti_demo.farmland_diagnosis.acidification import calculate_acidification_amendment
```
改为：
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import math
import pandas as pd
import pytest
from ai_culti_demo.farmland_diagnosis.acidification import calculate_acidification_amendment

V2_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "acidification_v2")
```

- [x] **Step 4: 编写失败的 `run_csv` 基础测试**

在 `tests/test_model4_acidification.py` 末尾（`test_model4_execution_missing_input` 之后）追加：

```python
# --- Task 4: run_csv 批量计算基础测试 ---
def test_run_csv_basic(tmp_path):
    """run_csv 基本功能：列结构、行数、结果非空、输出文件写入。"""
    from ai_culti_demo.farmland_diagnosis.acidification import run_csv
    input_csv = os.path.join(V2_DATA_DIR, "03_Data.csv")
    output_csv = str(tmp_path / "_test_basic_output.csv")
    df = run_csv(input_csv, output_csv, "upland", "compound")
    # 列结构：输入列 + 中间变量列 + 结果列
    expected_cols = {"TYBH", "SJD", "Hex", "Alex",
                     "Adep", "Acrop", "ANcy", "Aagri", "Aback", "YTK", "MBNT"}
    assert expected_cols <= set(df.columns), f"缺失列：{expected_cols - set(df.columns)}"
    # 行数
    assert len(df) == 393
    # 结果列非空（输入无 NaN）
    assert df["YTK"].notna().all(), "YTK 含意外 NaN"
    assert df["MBNT"].notna().all(), "MBNT 含意外 NaN"
    # 输出文件已写入
    assert os.path.exists(output_csv)


def test_run_csv_invalid_land_type(tmp_path):
    """非法 land_type 抛 ValueError。"""
    from ai_culti_demo.farmland_diagnosis.acidification import run_csv
    input_csv = os.path.join(V2_DATA_DIR, "03_Data.csv")
    output_csv = str(tmp_path / "_test_invalid.csv")
    with pytest.raises(ValueError, match="土地类型"):
        run_csv(input_csv, output_csv, "invalid", "compound")


def test_run_csv_missing_columns(tmp_path):
    """缺少必填列抛 ValueError。"""
    from ai_culti_demo.farmland_diagnosis.acidification import run_csv
    input_csv = str(tmp_path / "_bad_input.csv")
    pd.DataFrame({"TYBH": [1], "SJD": [5.5]}).to_csv(input_csv, index=False, encoding="utf-8-sig")
    output_csv = str(tmp_path / "_bad_output.csv")
    with pytest.raises(ValueError, match="CSV必须包含"):
        run_csv(input_csv, output_csv, "upland", "compound")
```

- [x] **Step 5: 运行测试确认失败（run_csv 未定义）**

Run: `pytest tests/test_model4_acidification.py::test_run_csv_basic -v`
Expected: FAIL with `ImportError: cannot import name 'run_csv'`

- [x] **Step 6: 实现 `run_csv` 函数**

在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 的 `calculate_acidification_amendment` 函数之后（旧函数兼容层注释 `# ===...` 之前，约第 258 行）插入：

```python
def run_csv(input_file: str, output_file: str,
            land_type: str, fertilizer_type: str) -> "pd.DataFrame":
    """批量 CSV 计算：读 CSV → 4 子模型批量计算 → 输出 CSV。

    与 v2 源码 02_酸化模型计算.py 语义一致：
    - 输入 CSV 需包含 SJD（或 pH）、Hex、Alex 列
    - 输出 CSV 含输入列 + 中间变量列（Adep/Acrop/ANcy/Aagri/Aback）+ 结果列（YTK/MBNT）
    - NaN 行输出 7 个 None，不抛异常
    - 不做越界校验（仅单次入口 calculate_acidification_amendment 做）

    Args:
        input_file: 输入 CSV 路径（utf-8-sig 编码）
        output_file: 输出 CSV 路径
        land_type: "paddy" 或 "upland"
        fertilizer_type: "urea" 或 "compound"

    Returns:
        填充计算列后的 DataFrame
    """
    if land_type not in ("paddy", "upland") or fertilizer_type not in ("urea", "compound"):
        raise ValueError("土地类型只能为水田或旱地，肥料类型只能为尿素或复合肥")

    df = pd.read_csv(input_file, encoding="utf-8-sig")
    p_col = "SJD" if "SJD" in df else "pH"
    if not {p_col, "Hex", "Alex"} <= set(df):
        raise ValueError("CSV必须包含pH或SJD、Hex、Alex列")

    sub_fn = _SUB_MODEL_MAP[(land_type, fertilizer_type)]
    params = _build_params(land_type, fertilizer_type)
    cols = ["Adep", "Acrop", "ANcy", "Aagri", "Aback", "YTK", "MBNT"]

    def _compute_row(v):
        if pd.isna(v).any():
            return [None] * 7
        out = sub_fn(*map(float, v), params)
        return [round(out["Adep"], 2), round(out["Acrop"], 2), round(out["ANcy"], 2),
                round(out["Aagri"], 2), round(out["Aback"], 2),
                round(out["ytk"], 2), round(out["mbnt"], 2)]

    df[cols] = [_compute_row(v) for v in df[[p_col, "Hex", "Alex"]].to_numpy()]
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    return df
```

- [x] **Step 7: 运行 `run_csv` 基础测试确认通过**

Run: `pytest tests/test_model4_acidification.py::test_run_csv_basic tests/test_model4_acidification.py::test_run_csv_invalid_land_type tests/test_model4_acidification.py::test_run_csv_missing_columns -v`
Expected: 三个测试 PASS

- [x] **Step 8: 运行完整测试套件确认无回归**

Run: `pytest tests/test_model4_acidification.py -v`
Expected: 所有测试 PASS

- [x] **Step 9: Commit**

```bash
git add tests/data/acidification_v2/03_Data.csv tests/data/acidification_v2/04_upland_compound_expected.csv src/ai_culti_demo/farmland_diagnosis/acidification.py tests/test_model4_acidification.py
git commit -m "feat(acidification): 新增 run_csv 批量 CSV 计算函数与 v2 测试数据

run_csv 复用 4 个子模型与 _build_params，支持 SJD/pH 列名兼容、
NaN 行输出 None、utf-8-sig 编码、结果保留 2 位小数，与 v2 源码语义一致。
不做越界校验（仅单次 API 入口做），不通过 HTTP API 暴露。
含 393 地块测试数据与基础契约测试。"
```

---

## Task 5: 393 地块回归测试

**Files:**
- Modify: `tests/test_model4_acidification.py`（新增 `test_acidification_v2_regression`）

**Interfaces:**
- Consumes: Task 4 的 `run_csv` 函数、`V2_DATA_DIR` 常量、`tests/data/acidification_v2/` 数据文件
- Produces: `test_acidification_v2_regression` 测试，验证 393 地块 YTK/MBNT 与 v2 源码期望输出偏差 < 0.01

- [x] **Step 1: 编写回归测试**

在 `tests/test_model4_acidification.py` 末尾（`test_run_csv_missing_columns` 之后）追加：

```python
# --- Task 5: v2 源码 393 地块回归测试 ---
def test_acidification_v2_regression(tmp_path):
    """v2 源码 393 地块回归测试（旱地+复合肥场景）。

    对比 run_csv 输出与 v2 源码 04_旱地复合肥计算结果.csv 的 YTK/MBNT，
    允许浮点偏差 < 0.01。极端值（Alex=8.95、SJD=4.19、Hex=1.62）通过
    全量对比自动覆盖。
    """
    from ai_culti_demo.farmland_diagnosis.acidification import run_csv

    input_csv = os.path.join(V2_DATA_DIR, "03_Data.csv")
    expected_csv = os.path.join(V2_DATA_DIR, "04_upland_compound_expected.csv")
    output_csv = str(tmp_path / "_test_regression_output.csv")

    df = run_csv(input_csv, output_csv, "upland", "compound")
    expected = pd.read_csv(expected_csv, encoding="utf-8-sig")

    # 对比 YTK/MBNT（允许浮点误差 < 0.01）
    for col in ["YTK", "MBNT"]:
        actual = df[col].astype(float)
        exp = expected[col].astype(float)
        max_diff = (actual - exp).abs().max()
        assert max_diff < 0.01, (
            f"{col} 不一致：最大偏差 {max_diff}，"
            f"首行 actual={actual.iloc[0]} expected={exp.iloc[0]}"
        )
```

- [x] **Step 2: 运行回归测试**

Run: `pytest tests/test_model4_acidification.py::test_acidification_v2_regression -v`
Expected: PASS（393 地块 YTK/MBNT 偏差 < 0.01）。若 FAIL，检查 `_finalize` 重构是否改变了 ytk/mbnt 计算（公式应不变），或 `_build_params` 是否漏掉复合肥额外参数。

- [x] **Step 3: 运行完整测试套件确认无回归**

Run: `pytest tests/test_model4_acidification.py -v`
Expected: 所有测试 PASS

- [x] **Step 4: Commit**

```bash
git add tests/test_model4_acidification.py
git commit -m "test(acidification): 新增 v2 源码 393 地块回归测试

用 v2 源码 03_Data.csv（393 地块）与 04_旱地复合肥计算结果.csv
验证 run_csv 输出 YTK/MBNT 偏差 < 0.01，覆盖极端值（Alex=8.95、SJD=4.19）。"
```

---

## Task 6: CLI 脚本实现

**Files:**
- Create: `scripts/run_acidification_batch.py`

**Interfaces:**
- Consumes: Task 4 的 `run_csv(input_file, output_file, land_type, fertilizer_type) -> pd.DataFrame`
- Produces: 可独立执行的 CLI 脚本，4 个必填参数 `--input/--output/--land/--fertilizer`，成功退出码 0，ValueError 退出码 1

- [x] **Step 1: 创建 CLI 脚本**

创建 `scripts/run_acidification_batch.py`：

```python
"""批量酸化模型 CSV 计算工具（CLI）。

用法：
    python scripts/run_acidification_batch.py --input <input.csv> --output <output.csv> \
        --land <paddy|upland> --fertilizer <urea|compound>

注意：run_csv 不做输入数据越界校验，请自行检查输入数据质量。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("PYTHONPATH", str(PROJECT_ROOT / "src"))

from ai_culti_demo.farmland_diagnosis.acidification import run_csv


def main():
    parser = argparse.ArgumentParser(description="酸化模型批量 CSV 计算工具")
    parser.add_argument("--input", required=True, help="输入 CSV 路径（需含 SJD/pH、Hex、Alex 列）")
    parser.add_argument("--output", required=True, help="输出 CSV 路径")
    parser.add_argument("--land", required=True, choices=["paddy", "upland"], help="土地类型")
    parser.add_argument("--fertilizer", required=True, choices=["urea", "compound"], help="肥料类型")
    args = parser.parse_args()

    try:
        df = run_csv(args.input, args.output, args.land, args.fertilizer)
        print(f"批量计算完成：共处理 {len(df)} 行，输出写入 {args.output}")
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [x] **Step 2: 运行 CLI 脚本验证成功路径**

Run:
```bash
python "d:\17417\Documents\agent_culti_demo\scripts\run_acidification_batch.py" --input "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\03_Data.csv" --output "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\_cli_test_output.csv" --land upland --fertilizer compound
```
Expected: 退出码 0，控制台输出 `批量计算完成：共处理 393 行，输出写入 ...`

- [x] **Step 3: 验证 CLI 输出与期望一致**

Run:
```bash
python -c "import pandas as pd; a=pd.read_csv(r'd:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\_cli_test_output.csv', encoding='utf-8-sig'); e=pd.read_csv(r'd:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\04_upland_compound_expected.csv', encoding='utf-8-sig'); print('YTK max diff:', (a['YTK'].astype(float)-e['YTK'].astype(float)).abs().max()); print('MBNT max diff:', (a['MBNT'].astype(float)-e['MBNT'].astype(float)).abs().max())"
```
Expected: YTK max diff < 0.01, MBNT max diff < 0.01

- [x] **Step 4: 验证 CLI 错误路径（非法 land_type）**

Run:
```bash
python "d:\17417\Documents\agent_culti_demo\scripts\run_acidification_batch.py" --input "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\03_Data.csv" --output "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\_cli_bad.csv" --land invalid --fertilizer compound; echo "exit=$LASTEXITCODE"
```
Expected: 控制台输出 `错误：土地类型只能为水田或旱地，肥料类型只能为尿素或复合肥`（到 stderr），退出码 1

- [x] **Step 5: 清理 CLI 测试产物**

Run:
```bash
Remove-Item "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\_cli_test_output.csv" -ErrorAction SilentlyContinue; Remove-Item "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\_cli_bad.csv" -ErrorAction SilentlyContinue
```

- [x] **Step 6: Commit**

```bash
git add scripts/run_acidification_batch.py
git commit -m "feat(acidification): 新增 run_acidification_batch.py CLI 脚本

argparse 定义 4 个必填参数（--input/--output/--land/--fertilizer），
调用 run_csv 批量计算，成功输出行数退出码 0，ValueError 友好提示退出码 1。
路径设置复用项目现有 scripts 模式（PROJECT_ROOT + src）。"
```

---

## Task 7: 集成验证与 spec/agent 检查

**Files:**
- 无代码改动（纯验证）；若发现问题则回退到对应 Task 修复

**Interfaces:**
- Consumes: Task 1-6 的全部产出
- Produces: 集成验证通过的确认；delta spec 与 agent 透传验证记录

- [x] **Step 1: CLI 端到端验证**

Run:
```bash
python "d:\17417\Documents\agent_culti_demo\scripts\run_acidification_batch.py" --input "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\03_Data.csv" --output "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\_integration_output.csv" --land upland --fertilizer compound
```
Expected: 退出码 0，输出 `批量计算完成：共处理 393 行...`

- [x] **Step 2: 对比 CLI 输出与期望 CSV 完全一致**

Run:
```bash
python -c "import pandas as pd; a=pd.read_csv(r'd:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\_integration_output.csv', encoding='utf-8-sig'); e=pd.read_csv(r'd:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\04_upland_compound_expected.csv', encoding='utf-8-sig'); assert len(a)==len(e)==393; assert (a['YTK'].astype(float)-e['YTK'].astype(float)).abs().max()<0.01; assert (a['MBNT'].astype(float)-e['MBNT'].astype(float)).abs().max()<0.01; print('CLI 输出与期望一致：393 行 YTK/MBNT 偏差 < 0.01')"
```
Expected: 输出 `CLI 输出与期望一致：393 行 YTK/MBNT 偏差 < 0.01`

- [x] **Step 3: 清理集成测试产物**

Run:
```bash
Remove-Item "d:\17417\Documents\agent_culti_demo\tests\data\acidification_v2\_integration_output.csv" -ErrorAction SilentlyContinue
```

- [x] **Step 4: 运行酸化模型完整测试套件**

Run: `pytest tests/test_model4_acidification.py -v`
Expected: 所有测试 PASS（含原有测试 + `test_run_csv_*` + `test_acidification_v2_regression`）

- [x] **Step 5: 运行酸化相关 agent 测试确认 model_version 透传无回归**

Run: `pytest tests/test_agent_specialized.py -v -k "acidification or model_4 or model4"`
Expected: 所有相关测试 PASS（`acidification_agent.py` 通过 `result.get("model_version")` 透传，无硬编码版本号，升级后自动返回 v2）

- [x] **Step 6: 验证 delta spec 完整性**

Run: `Read d:\17417\Documents\agent_culti_demo\openspec\changes\sync-acidification-model-v2\specs\farmland-acidification-improvement-model\spec.md`
Expected: 文件存在，包含 3 个 Requirement（v2 版本标识、批量 CSV 计算工具、v2 回归测试验证），与 design doc 一致。无需改动。

- [x] **Step 7: 验证 `acidification_agent.py` 无硬编码版本号**

Run: `Select-String -Path "d:\17417\Documents\agent_culti_demo\framework\agents\specialized\acidification_agent.py" -Pattern "process_v" -SimpleMatch`
Expected: 无输出（agent 通过 `result.get("model_version")` 透传，无硬编码 v1/v2，升级后自动返回 v2，无需改动）

- [x] **Step 8: 运行更广泛的测试套件确认无跨模块回归**

Run: `pytest tests/test_farmland_diagnosis.py tests/test_thematic_models.py tests/test_execute_models_pipeline.py -v`
Expected: 所有测试 PASS（酸化模型升级不影响其他模型与诊断流程）

- [x] **Step 9: 若上述任一步骤发现问题，回退对应 Task 修复后重新验证**

若 Step 4-8 任一失败，定位失败原因，回退到 Task 1-6 对应步骤修复，重新运行失败步骤。全部通过后方可进入归档。

---

## 实现顺序说明

按设计文档 §5 建议顺序排列：Task 1（子模型重构）→ Task 2（参数提取）→ Task 3（版本升级）→ Task 4（run_csv + 数据）→ Task 5（回归测试）→ Task 6（CLI）→ Task 7（集成验证）。

每个 Task 产出可独立测试的交付物，Task 间存在线性依赖：Task 4 依赖 Task 1（7 字段 dict）和 Task 2（`_build_params`）；Task 5 依赖 Task 4（`run_csv` + 数据）；Task 6 依赖 Task 4（`run_csv`）；Task 7 依赖全部。
