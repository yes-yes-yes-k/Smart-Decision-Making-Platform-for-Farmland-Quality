## Why

酸化模型（model-4）此前已通过 `replace-acidification-with-process-model` 归档为过程模型 v1（`process_v1_20260801`）。模型作者于 2026-08-01 发布 v2 源码（`模型5_酸化模型_v2_20260801`），经逐行对比，4 个子模型的核心数学公式、默认参数、系数与项目现有实现完全一致，但 v2 新增了批量 CSV 计算函数 `run_csv`、393 个地块测试数据（含极端值）和原理公式文档。本次变更将项目同步到 v2 版本标识，用 v2 数据做回归验证，并引入批量 CSV 计算能力（仅内部函数 + CLI 脚本，不暴露为 HTTP API），以支持离线批量评估场景。

## What Changes

- 将 `MODEL_VERSION` 从 `process_v1_20260801` 升级为 `process_v2_20260801`，同步更新 `model_4_execution` 入口和 acidification_agent 的版本引用
- 在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 新增 `run_csv(input_file, output_file, land_type, fertilizer_type)` 函数：读 CSV（含 SJD/pH、Hex、Alex 列）→ 批量调用 4 个子模型 → 输出 CSV（含中间变量 Adep/Acrop/ANcy/Aagri/Aback + YTK/MBNT），与 v2 源码语义一致
- 在 `scripts/` 下新增 CLI 脚本（如 `run_acidification_batch.py`），支持命令行执行批量 CSV 计算：`python scripts/run_acidification_batch.py --input <csv> --output <csv> --land <paddy|upland> --fertilizer <urea|compound>`
- 用 v2 的 393 个地块数据（`03_Data.csv` 输入 + `04_旱地复合肥计算结果.csv` 期望值）新增回归测试 `test_acidification_v2_regression`，验证项目实现在大数据集（含极端值 Alex=8.95、SJD=4.19）上与 v2 源码输出偏差 < 0.01
- 修订 `farmland-acidification-improvement-model` spec：将"按需计算模式下不再需要批量评估"语义调整为"提供批量 CSV 计算工具（内部函数 + CLI 脚本），但不作为 HTTP API 端点"；新增批量计算需求；更新 `model_version` 标识为 `process_v2_20260801`
- 更新 `acidification.py` 模块 docstring 中的源码路径引用（从 `02_酸化模型计算-地块.py` 更新为 `02_酸化模型计算.py` v2 版本）

### 非目标

- 不修改 4 个子模型（paddy_urea/paddy_compound/upland_urea/upland_compound）的核心数学公式（已与 v2 逐行一致）
- 不改变现有 HTTP API 接口（SJD/JHX/JLA 输入，YTK/MBNT 输出），run_csv 不通过 API 暴露
- 不修改其他模型（model-3/5/6/7）及其 agent
- 不暴露中间产酸量分解（Adep/Acrop/ANcy/Aagri/Aback）到标准 API 输出（仅在 run_csv 的 CSV 输出中包含，用于离线分析）

## Capabilities

### New Capabilities

无。run_csv 批量计算能力作为现有 `farmland-acidification-improvement-model` 的扩展，不构成独立能力。

### Modified Capabilities

- `farmland-acidification-improvement-model`: 修订"按需计算模式下不再需要批量评估"语义为"提供批量 CSV 计算工具（内部函数 + CLI），不作为 API 端点"；新增批量 CSV 计算需求（run_csv 函数 + CLI 脚本）；更新 `model_version` 标识为 `process_v2_20260801`；新增 v2 回归测试验证需求

## Impact

### 受影响代码

- `src/ai_culti_demo/farmland_diagnosis/acidification.py`：MODEL_VERSION 升级 + 新增 `run_csv` 函数 + docstring 更新
- `framework/domain/other_models/model_4.py`：版本引用同步（`process_v1_20260801` → `process_v2_20260801`，含 3 处 fallback 返回值）
- `framework/agents/specialized/acidification_agent.py`：无代码改动（版本号由 model_4_execution 透传），但需验证 model_version 字段正确流转
- `tests/test_model4_acidification.py`：更新 `EXPECTED` 中的 `model_version` 断言 + 新增 v2 回归测试函数
- `scripts/run_acidification_batch.py`：新增 CLI 脚本

### 受影响 spec

- `openspec/specs/farmland-acidification-improvement-model/spec.md`：修订批量评估语义 + 版本标识 + 新增批量计算需求

### 受影响依赖

- 新增测试数据文件：`tests/data/acidification_v2/03_Data.csv`（393 地块输入）+ `tests/data/acidification_v2/04_upland_compound_expected.csv`（期望输出）
- v2 源码引用路径更新（仅 docstring，不引入新依赖）

### 不受影响

- HTTP API 路由层（`framework/api/routes/chat.py`）：无改动
- 其他模型（model-3/5/6/7）及其 agent
- 前端、openapi.json、api.md（因 run_csv 不暴露为 API）
