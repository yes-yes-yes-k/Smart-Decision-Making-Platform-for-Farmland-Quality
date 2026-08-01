# Comet Design Handoff

- Change: sync-acidification-model-v2
- Phase: design
- Mode: compact
- Context hash: 93b7c5f4e9c734334c72272881286fd9fc7f1f2b6b1871213b54b1ea90a51cf3

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/sync-acidification-model-v2/proposal.md

- Source: openspec/changes/sync-acidification-model-v2/proposal.md
- Lines: 1-54
- SHA256: 76c9f4520e12fa59a61c99760a324405a3021aafe75a77fb852cac5c7fcc8f65

```md
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

```

## openspec/changes/sync-acidification-model-v2/design.md

- Source: openspec/changes/sync-acidification-model-v2/design.md
- Lines: 1-96
- SHA256: e8e42c5f9eac7adff12cdb254a69e64f94cc1ad304f8ede0d4ddd1adfbd3176c

[TRUNCATED]

```md
## Context

酸化模型（model-4）在 `replace-acidification-with-process-model`（已归档 2026-07-31）中从规则式石灰施用量计算替换为基于过程的酸化模型（4 子模型：paddy/upland × urea/compound），输入 pH(SJD)+交换性氢(JHX)+交换性铝(JLA)，输出 YTK/MBNT(kg/ha)，`MODEL_VERSION = process_v1_20260801`。

模型作者于 2026-08-01 发布 v2 源码（`D:\destkop\模型\模型5_酸化模型_v2_20260801`）。经逐行三方对比（v2 docx 原理文档 / v2 源码 02_酸化模型计算.py / 项目实现 acidification.py）：

- **4 子模型数学公式、默认参数、系数完全一致**（paddy_urea/paddy_compound/upland_urea/upland_compound 的 Anit/Ano3_runoff/Ano3_crop/Avol/Aback/YTK/MBNT 公式逐行相同）
- v2 新增 `run_csv(input_file, output_file, land, fertilizer)` 批量计算函数（项目未实现）
- v2 提供 393 个地块测试数据（含极端值 Alex=8.95、SJD=4.19）
- v2 docx 原理文档有 3 处笔误（Aback 公式 9-SJD 减 9-SJD 应为 9-pHtarget；复合肥 Ano3_runoff 漏写 FertN 部分和 0.3 系数；复合肥 Sp/Smg 默认值 0.18%/0.21% 与源码 0.176%/0.212% 不一致），以 v2 源码为准

当前项目 spec 明确"按需计算模式下不再需要批量评估"（`evaluate_acidification` 已 deprecated），但用户希望引入批量 CSV 计算工具用于离线分析场景，同时不暴露为 HTTP API。

## Goals / Non-Goals

**Goals:**
- 将 `MODEL_VERSION` 升级为 `process_v2_20260801`，同步版本引用
- 新增 `run_csv` 批量 CSV 计算函数（内部）+ CLI 脚本（`scripts/run_acidification_batch.py`）
- 用 v2 的 393 个地块数据新增回归测试，验证极端值场景下的正确性
- 修订 spec 反映批量工具能力（不作为 API 端点）

**Non-Goals:**
- 不修改 4 子模型核心数学公式（已与 v2 一致）
- 不改变现有 HTTP API 接口（SJD/JHX/JLA → YTK/MBNT）
- 不通过 HTTP API 暴露 run_csv（仅内部函数 + CLI）
- 不暴露中间变量（Adep/Acrop/ANcy/Aagri/Aback）到标准 API 输出（仅在 run_csv 的 CSV 输出中包含）
- 不修改其他模型（model-3/5/6/7）

## Decisions

### D1: run_csv 实现位置与签名

**决策**：在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 新增 `run_csv` 函数，签名与 v2 源码一致：

```python
def run_csv(input_file: str, output_file: str, land_type: str, fertilizer_type: str) -> pd.DataFrame:
    """批量 CSV 计算：读 CSV → 4 子模型批量计算 → 输出 CSV。"""
```

**理由**：与 v2 源码语义一致，便于对照验证；放在 acidification.py 与 `calculate_acidification_amendment` 同模块，内聚性强。

**替代方案**：放在 `scripts/` 下作为独立工具脚本。否决，因为 scripts 应只做 CLI 封装，核心逻辑应在 domain 层。

### D2: run_csv 输出列设计

**决策**：输出 CSV 包含输入列（TYBH/SJD/Hex/Alex）+ 中间变量列（Adep/Acrop/ANcy/Aagri/Aback）+ 结果列（YTK/MBNT），与 v2 源码 04 csv 输出格式一致。

**理由**：与 v2 源码完全对齐，便于回归测试直接对比；中间变量对离线分析有价值。

**权衡**：这与 spec "不暴露中间产酸量分解" 略有张力，但 spec 原意是 API 输出不暴露，run_csv 是离线工具，可在 CSV 中包含。spec 会明确区分"API 输出"与"批量工具 CSV 输出"。

### D3: 缺失值处理策略

**决策**：与 v2 源码一致，对含 NaN 的行输出 7 个 None（Adep/Acrop/ANcy/Aagri/Aback/YTK/MBNT 全为空），不抛异常。

**理由**：v2 源码 `run_csv` 第 82 行 `[[None]*7 if pd.isna(v).any() else ...]` 即此行为；保持一致以通过回归测试。

### D4: 越界值处理策略

**决策**：`run_csv` 不做越界校验（[3.0, 10.0] 等），直接计算。越界校验仅在 `calculate_acidification_amendment` 单次入口生效。

**理由**：v2 源码 `run_csv` 不做越界校验，直接调用子模型函数；393 地块数据含 SJD=4.19（低于 3.0？不，4.19 > 3.0）等值，均能正常计算。回归测试需要与 v2 输出完全一致，故 run_csv 不加额外校验。

**权衡**：若用户通过 run_csv 处理含越界值的 CSV，不会被告知。但 run_csv 是离线工具，用户应自行检查输入数据质量。CLI 脚本会在文档中提示。

### D5: CLI 脚本设计

**决策**：`scripts/run_acidification_batch.py` 使用 argparse，参数：
- `--input`（必填）：输入 CSV 路径
- `--output`（必填）：输出 CSV 路径
- `--land`（必填）：paddy | upland
- `--fertilizer`（必填）：urea | compound

**理由**：与 v2 源码 `run_csv` 的 land/fertilizer 参数对齐；必填避免默认值歧义。

### D6: 回归测试数据放置

**决策**：v2 测试数据复制到 `tests/data/acidification_v2/`：
- `03_Data.csv`（393 地块输入）
- `04_upland_compound_expected.csv`（期望输出，旱地+复合肥场景）

```

Full source: openspec/changes/sync-acidification-model-v2/design.md

## openspec/changes/sync-acidification-model-v2/tasks.md

- Source: openspec/changes/sync-acidification-model-v2/tasks.md
- Lines: 1-50
- SHA256: 54a23d36c5de9d2137714c998a943d7826efed712f1f167f0da71753c6c3c4d7

```md
## 1. 版本标识升级

- [ ] 1.1 在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 将 `MODEL_VERSION` 从 `process_v1_20260801` 升级为 `process_v2_20260801`
- [ ] 1.2 在 `framework/domain/other_models/model_4.py` 同步 3 处 fallback 返回值中的 `model_version` 字段（`process_v1_20260801` → `process_v2_20260801`，含 model_unavailable 和 cannot_get_ph 两处）
- [ ] 1.3 更新 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 模块 docstring 中的源码路径引用（从 `02_酸化模型计算-地块.py` 更新为 `02_酸化模型计算.py` v2 版本，注明"原理文档 01_产酸过程计算公式.docx 有笔误，以源码为准"）

## 2. run_csv 批量计算函数实现

- [ ] 2.1 在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 新增 `run_csv(input_file, output_file, land_type, fertilizer_type) -> pd.DataFrame` 函数，签名与 v2 源码一致
- [ ] 2.2 实现 CSV 读取逻辑：支持 `SJD` 或 `pH` 列名（`p = "SJD" if "SJD" in df else "pH"`），校验必填列（SJD/pH、Hex、Alex），缺失抛 `ValueError`
- [ ] 2.3 实现批量计算逻辑：构建子模型映射 `{("paddy","urea"):_paddy_urea, ...}`，对每行数据调用对应子模型（含 NaN 行输出 7 个 None，不抛异常）
- [ ] 2.4 实现 CSV 输出逻辑：输出列包含输入列（TYBH/SJD/Hex/Alex）+ 中间变量列（Adep/Acrop/ANcy/Aagri/Aback）+ 结果列（YTK/MBNT），结果保留 2 位小数（`round(x,2)`），编码 `utf-8-sig`
- [ ] 2.5 run_csv 内部调用项目现有的 `_paddy_urea`/`_paddy_compound`/`_upland_urea`/`_upland_compound` 子模型函数（不重复实现公式），传入默认参数组装逻辑（复用 `_PADDY_DEFAULTS`/`_UPLAND_DEFAULTS`/`_PADDY_COMPOUND_EXTRA`/`_UPLAND_COMPOUND_EXTRA`）

## 3. CLI 脚本实现

- [ ] 3.1 新建 `scripts/run_acidification_batch.py`，使用 argparse 定义 4 个必填参数：`--input`、`--output`、`--land`（paddy|upland）、`--fertilizer`（urea|compound）
- [ ] 3.2 在 CLI 脚本中调用 `ai_culti_demo.farmland_diagnosis.acidification.run_csv`，处理异常（ValueError 友好提示，退出码 1）
- [ ] 3.3 CLI 脚本成功时输出处理行数，退出码 0；在 docstring 中提示"输入数据质量由用户自行检查，run_csv 不做越界校验"

## 4. v2 测试数据准备

- [ ] 4.1 创建目录 `tests/data/acidification_v2/`
- [ ] 4.2 复制 v2 源码目录的 `03_Data.csv` 到 `tests/data/acidification_v2/03_Data.csv`（393 地块输入数据）
- [ ] 4.3 复制 v2 源码目录的 `04_旱地复合肥计算结果.csv` 到 `tests/data/acidification_v2/04_upland_compound_expected.csv`（期望输出，旱地+复合肥场景）

## 5. 回归测试实现

- [ ] 5.1 在 `tests/test_model4_acidification.py` 新增 `test_acidification_v2_regression` 测试函数：读取 `tests/data/acidification_v2/03_Data.csv` 和 `04_upland_compound_expected.csv`
- [ ] 5.2 测试调用 `run_csv` 以 `land_type="upland"`、`fertilizer_type="compound"` 执行批量计算，对比 393 个地块的 `YTK`/`MBNT` 与期望值偏差 < 0.01
- [ ] 5.3 测试覆盖极端值场景：验证输入数据中 `Alex=8.95`、`SJD=4.19`、`Hex=1.62` 等极端值行能正常计算（不单独断言，通过全量对比覆盖）

## 6. 现有测试更新

- [ ] 6.1 更新 `tests/test_model4_acidification.py` 中 `test_model_version_present` 的断言：`process_v1_20260801` → `process_v2_20260801`
- [ ] 6.2 更新 `tests/test_model4_acidification.py` 中 `test_model4_execution_direct_inputs` 的 `model_version` 断言：`process_v1_20260801` → `process_v2_20260801`
- [ ] 6.3 运行现有 `test_model4_acidification.py` 全部测试，确认无回归（除版本号断言外，其他测试逻辑不变）

## 7. 文档与 spec 同步

- [ ] 7.1 确认 delta spec `openspec/changes/sync-acidification-model-v2/specs/farmland-acidification-improvement-model/spec.md` 内容完整（已在 open 阶段创建）
- [ ] 7.2 检查 `framework/agents/specialized/acidification_agent.py` 的 `model_version` 字段透传是否正确（无代码改动，仅验证）
- [ ] 7.3 检查是否需要更新 `README.md` 或 `api.md` 中关于酸化模型版本的描述（run_csv 不暴露为 API，通常无需更新 api.md；README 若有版本提及则同步）

## 8. 集成验证

- [ ] 8.1 运行 `python scripts/run_acidification_batch.py --input tests/data/acidification_v2/03_Data.csv --output tests/data/acidification_v2/_test_output.csv --land upland --fertilizer compound`，确认 CLI 脚本工作正常
- [ ] 8.2 对比 CLI 脚本输出与 `04_upland_compound_expected.csv`，确认完全一致
- [ ] 8.3 运行完整测试套件 `pytest tests/test_model4_acidification.py -v`，确认所有测试通过
- [ ] 8.4 运行酸化相关 agent 测试（`tests/test_agent_specialized.py` 等），确认 model_version 透传无回归

```

## openspec/changes/sync-acidification-model-v2/specs/farmland-acidification-improvement-model/spec.md

- Source: openspec/changes/sync-acidification-model-v2/specs/farmland-acidification-improvement-model/spec.md
- Lines: 1-58
- SHA256: 05627eed4d0c337deded626f240df453b33282520325fe3c98c677c843e80173

```md
## ADDED Requirements

### Requirement: 模型3 v2 版本标识
系统 SHALL 将酸化过程模型的 `model_version` 标识更新为 `process_v2_20260801`，反映与模型作者 2026-08-01 发布的 v2 源码（`模型5_酸化模型_v2_20260801`）同步。所有计算结果（单次 API 调用、批量 CSV 计算）SHALL 返回该版本标识。4 个子模型的核心数学公式、默认参数、系数与 v2 源码逐行一致，无公式变更。

#### Scenario: 单次计算返回 v2 版本
- **WHEN** 系统通过 `calculate_acidification_amendment` 执行单次酸化模型计算
- **THEN** 结果中的 `model_version` 字段 SHALL 为 `process_v2_20260801`

#### Scenario: 批量计算返回 v2 版本
- **WHEN** 系统通过 `run_csv` 执行批量 CSV 计算
- **THEN** 输出的每行结果 SHALL 包含 `model_version = process_v2_20260801`（通过 CLI 脚本元数据或单独版本文件体现，CSV 行内可选）

#### Scenario: model_4_execution 入口透传 v2 版本
- **WHEN** 调用 `model_4_execution` 入口（含 fallback 场景 model_unavailable）
- **THEN** 返回的 `model_version` 字段 SHALL 为 `process_v2_20260801`

### Requirement: 模型3 批量 CSV 计算工具
系统 SHALL 提供批量 CSV 计算能力，包含内部函数 `run_csv` 和 CLI 脚本 `scripts/run_acidification_batch.py`，支持从 CSV 文件读取多个地块数据，批量执行酸化模型计算，输出包含中间变量和结果变量的 CSV 文件。该能力 SHALL NOT 通过 HTTP API 暴露，仅用于离线批量分析场景。

#### Scenario: run_csv 函数批量计算成功
- **WHEN** 调用 `run_csv(input_file, output_file, land_type, fertilizer_type)`，输入 CSV 包含 `SJD`（或 `pH`）、`Hex`、`Alex` 列，`land_type` 为 `paddy` 或 `upland`，`fertilizer_type` 为 `urea` 或 `compound`
- **THEN** 系统 SHALL 读取输入 CSV，对每行数据执行对应的 4 个子模型之一（paddy_urea/paddy_compound/upland_urea/upland_compound），输出 CSV 包含输入列 + 中间变量列（`Adep`/`Acrop`/`ANcy`/`Aagri`/`Aback`）+ 结果列（`YTK`/`MBNT`），返回填充后的 DataFrame

#### Scenario: CLI 脚本批量计算成功
- **WHEN** 用户执行 `python scripts/run_acidification_batch.py --input <input.csv> --output <output.csv> --land <paddy|upland> --fertilizer <urea|compound>`
- **THEN** 系统 SHALL 执行批量计算并写入输出 CSV，退出码 0 表示成功，控制台输出处理行数

#### Scenario: 输入 CSV 缺少必填列
- **WHEN** 输入 CSV 不包含 `SJD`（或 `pH`）、`Hex`、`Alex` 中的任一列
- **THEN** 系统 SHALL 抛出 `ValueError` 提示缺失的列名（"CSV必须包含pH或SJD、Hex、Alex列"），不执行计算

#### Scenario: 非法 land_type 或 fertilizer_type
- **WHEN** `run_csv` 接收 `land_type` 非 `paddy`/`upland`，或 `fertilizer_type` 非 `urea`/`compound`
- **THEN** 系统 SHALL 抛出 `ValueError`（"土地类型只能为水田或旱地，肥料类型只能为尿素或复合肥"）

#### Scenario: 含 NaN 行的处理
- **WHEN** 输入 CSV 某行的 `SJD`/`Hex`/`Alex` 任一值为 NaN
- **THEN** 系统 SHALL 在输出 CSV 对应行的 7 个计算列（`Adep`/`Acrop`/`ANcy`/`Aagri`/`Aback`/`YTK`/`MBNT`）填入 None，不抛异常，继续处理其他行

#### Scenario: 批量计算不通过 API 暴露
- **WHEN** 调用方尝试通过 HTTP API 触发批量 CSV 计算
- **THEN** 系统 SHALL NOT 提供批量计算端点（`run_csv` 仅作为内部函数和 CLI 工具存在，`chat.py` 路由层无改动）

### Requirement: 模型3 v2 回归测试验证
系统 SHALL 通过 v2 源码提供的 393 个地块测试数据验证项目实现的正确性，确保在大数据集（含极端值如 `Alex=8.95`、`SJD=4.19`）上与 v2 源码输出偏差 < 0.01。测试数据 SHALL 自包含在 `tests/data/acidification_v2/` 目录下，不依赖外部路径。

#### Scenario: 393 地块回归测试通过
- **WHEN** 运行 `test_acidification_v2_regression` 测试，使用 `tests/data/acidification_v2/03_Data.csv`（393 地块输入）和 `tests/data/acidification_v2/04_upland_compound_expected.csv`（期望输出，旱地+复合肥场景）
- **THEN** 所有 393 个地块的 `YTK`/`MBNT` 计算结果 SHALL 与期望值偏差 < 0.01

#### Scenario: 极端值正常处理
- **WHEN** 输入数据包含极端值（如 `Alex=8.95`、`SJD=4.19`、`Hex=1.62`）
- **THEN** 系统 SHALL 正常计算（不抛异常），结果与 v2 源码输出一致

#### Scenario: 中间变量一致性
- **WHEN** 运行回归测试并对比 `Adep`/`Acrop`/`ANcy`/`Aagri`/`Aback` 中间变量
- **THEN** 所有 393 个地块的中间变量 SHALL 与 v2 源码输出偏差 < 0.01（可选验证，回归测试默认验证 YTK/MBNT）

```
