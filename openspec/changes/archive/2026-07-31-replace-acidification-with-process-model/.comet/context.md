# Comet Design Handoff

- Change: replace-acidification-with-process-model
- Phase: design
- Mode: compact
- Context hash: 3c6f72193cb7f4a5590c0cbf4295b6b33fc8251b13149d4030a462b90e92084b

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/replace-acidification-with-process-model/proposal.md

- Source: openspec/changes/replace-acidification-with-process-model/proposal.md
- Lines: 1-35
- SHA256: 7fbe8a109184f0fb8387cd11dfb152d94bfa7c534c708ae70d142a34ebf8d80d

```md
## Why

现有酸化改良模型基于 GB/T 42817-2023 规则导向的石灰剂量计算，仅使用 pH 和有机质两个输入，缺乏对土壤酸化过程的精确建模。模型提供方已交付基于过程的酸化计算模型（含4个子模型：水田/旱地 × 尿素/复合肥），使用土壤三普数据（pH、交换性氢、交换性铝）计算改良剂需求量（亿土康YTK/木本泥炭MBNT），能更精确地指导酸化改良。

## What Changes

- **BREAKING** 完全替换 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 中的 GB/T 42817-2023 规则导向石灰剂量计算逻辑，改为基于过程的酸化计算模型
- **BREAKING** 酸化改良输出从「石灰施用量(kg/亩)」改为「亿土康YTK(kg/ha) + 木本泥炭MBNT(kg/ha)」
- 新增交换性氢(JHX)、交换性铝(JLA)字段标准码到 `farmland_diagnosis/config.py`
- `framework/domain/other_models/model_4.py` 从占位实现替换为真实过程模型调用入口
- `framework/agents/specialized/acidification_agent.py` 适配新参数（fertilizer_type、land_type、JHX、JLA）
- `framework/agents/nodes.py` 透传 fertilizer_type 参数
- `framework/api/routes/chat.py` 接受 fertilizer_type 顶层参数
- 架构从 DB 持久化查询改为按需计算（类似 model-6 fertility ML）
- API 新增 `fertilizer_type` 参数（可选，默认 `compound` 复合肥；可选 `urea` 尿素）
- ~15 个过程模型默认参数（RPH/R/Y/S/元素含量/FertN/Ndep/pHtarget 等）部分可配，通过 API 可选参数覆盖

## Capabilities

### New Capabilities

（无新增 capability — 全部在已有 capability 上修改）

### Modified Capabilities

- `farmland-acidification-improvement-model`: 完全替换酸化因子提取、酸化程度分区、改良方案生成、在线查询和输出格式5项需求。输入从 pH+有机质 改为 pH+交换性氢+交换性铝；计算从规则导向改为过程模型（4子模型）；输出从石灰施用量改为 YTK/MBNT；架构从 DB 查询改为按需计算。

## Impact

- **核心代码**：`src/ai_culti_demo/farmland_diagnosis/acidification.py`（完全重写）、`config.py`（新增字段码）
- **框架层**：`framework/domain/other_models/model_4.py`（替换占位）、`framework/agents/specialized/acidification_agent.py`（适配新参数）、`framework/agents/nodes.py`（透传 fertilizer_type）
- **API 层**：`framework/api/routes/chat.py`（接受 fertilizer_type 参数）
- **API 契约**：question_type=2 的响应字段从 `lime_demand`/`amendment_type`/`amendment_rate` 改为 `ytk`/`mbnt`
- **数据库**：现有 acidification_results 表数据不再使用（按需计算不依赖 DB），但保留表结构不删除
- **文档**：openapi.json、api.md、README.md 需同步更新

```

## openspec/changes/replace-acidification-with-process-model/design.md

- Source: openspec/changes/replace-acidification-with-process-model/design.md
- Lines: 1-104
- SHA256: 114b1f6c8762d2ee60292c5fc126a6af8b9460bf3e690e5b30eb7e95b48a7249

[TRUNCATED]

```md
## Context

现有酸化改良模型（系统 model-4 / AcidificationRemediationAgent）基于 GB/T 42817-2023 规则导向的石灰剂量计算，仅使用 pH（SJD）和有机质（YJZ）两个输入。模型提供方已交付基于过程的酸化计算模型（D:\destkop\模型5），包含4个子模型（水田/旱地 × 尿素/复合肥），使用土壤三普数据（pHstart、交换性氢Hex、交换性铝Alex）和~15个默认参数计算改良剂需求量（亿土康YTK/木本泥炭MBNT）。

当前架构：
- `src/ai_culti_demo/farmland_diagnosis/acidification.py`：规则导向计算（calculate_lime_demand/generate_amendment）+ DB 查询（query_acidification）
- `framework/agents/specialized/acidification_agent.py`（model-4）：尝试调用 query_acidification，失败时回退到 mock
- `framework/domain/other_models/model_4.py`：占位实现
- question_type=2 → model-4（路由不变）

约束：
- 字段标准码体系中无交换性氢/铝定义（config.py 的 ALL_INDICATORS 不含 JHX/JLA）
- API 层（chat.py）已透传 parcel_id/parcel_code/land_type，需新增 fertilizer_type
- nodes.py 已透传 land_type，需新增 fertilizer_type

## Goals / Non-Goals

**Goals:**
- 完全替换 GB/T 42817-2023 规则逻辑为基于过程酸化计算模型
- 支持4个子模型选择（land_type × fertilizer_type）
- 新增交换性氢(JHX)/交换性铝(JLA)字段标准码
- 按需计算架构（API 参数 → 直接计算 YTK/MBNT，不依赖 DB 预计算）
- ~15 个默认参数部分可配（通过 API 可选参数覆盖）
- 仅输出 YTK/MBNT，不暴露中间产酸量分解

**Non-Goals:**
- 不修改 question_type 路由架构（type 2 → model-4 不变）
- 不修改其他模型（model-1/2/3/5/6/7）
- 不删除现有 acidification_results 表（保留结构，不再使用）
- 不暴露 Adep/Acrop/ANcy/Aagri/Aback 中间产酸量
- 不实现批量预计算和 DB 持久化（按需计算即可）

## Decisions

### D1: 架构方向 — 按需计算（非 DB 持久化）

**选择**：API 参数直接计算 YTK/MBNT，不依赖 DB 预计算。

**理由**：
- 新模型仅需3个三普输入（pHstart/Hex/Alex）+ 默认参数，计算量小（纯数学公式，无 ML 推理）
- Hex/Alex 不在现有 evaluation_results 表 schema 中，DB 预计算需要先扩展 schema 再批量导入
- 与 model-6（fertility ML）一致的按需计算模式
- 用户已确认选择「按需计算（推荐）」

**替代方案（已否决）**：保留 DB 持久化 — 需扩展 schema、批量预计算、维护数据一致性，复杂度高且收益低。

### D2: 字段标准码命名 — JHX / JLA

**选择**：
- JHX = 交换性氢（Exchangeable Hydrogen）
- JLA = 交换性铝（Exchangeable Aluminum）

**理由**：
- 遵循现有命名规则（拼音首字母缩写：J=交换性，HX=氢，LA=铝）
- 与 config.py 中 SJD/YJZ 等命名风格一致
- 需添加到 ALL_INDICATORS 和 CONTINUOUS_INDICATORS

### D3: 模型入口 — framework/domain/other_models/model_4.py

**选择**：`model_4.py` 作为统一入口函数 `model_4_execution()`，内部调用 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 的过程计算函数。

**理由**：
- 与 model_6.py 模式一致（framework 层入口 → 调用 src 层实现）
- acidification_agent.py 通过 model_4_execution 获取结果，保持调用链统一

### D4: 参数传递 — fertilizer_type 作为 API 顶层参数

**选择**：
- `fertilizer_type`：API 顶层可选参数，默认 `compound`（复合肥），可选 `urea`（尿素）
- `land_type`：已有参数，默认 `upland`（旱地），可选 `paddy`（水田）
- 两者组合选择4个子模型之一

**理由**：
- 与 land_type 透传机制一致（chat.py → nodes.py → agent → model）
- 用户已确认「API 参数+默认复合肥」

### D5: 部分可配参数 — 3个三普输入必填 + ~15个默认参数可选覆盖

**选择**：
- 必填输入：pHstart(=SJD)、Hex(=JHX)、Alex(=JLA)

```

Full source: openspec/changes/replace-acidification-with-process-model/design.md

## openspec/changes/replace-acidification-with-process-model/tasks.md

- Source: openspec/changes/replace-acidification-with-process-model/tasks.md
- Lines: 1-53
- SHA256: 9717213828df8968c53f89745ae3f41486d82d7b4057f3692cb055735f4a93ef

```md
## 1. 字段标准码新增

- [ ] 1.1 在 `src/ai_culti_demo/farmland_diagnosis/config.py` 的 `ALL_INDICATORS` 列表新增 `JHX`（交换性氢）和 `JLA`（交换性铝）
- [ ] 1.2 在 `CONTINUOUS_INDICATORS` 列表新增 `JHX` 和 `JLA`（两者均为连续指标）
- [ ] 1.3 在 `INDICATOR_DISPLAY_MAP` 新增 `'JHX': '交换性氢'` 和 `'JLA': '交换性铝'` 映射

## 2. 过程模型核心实现

- [ ] 2.1 在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 实现4个过程子模型函数：`paddy_urea`、`paddy_compound`、`upland_urea`、`upland_compound`（移植自模型5源码 02_酸化模型计算-地块.py）
- [ ] 2.2 实现统一入口函数 `calculate_acidification_amendment(pHstart, Hex, Alex, land_type, fertilizer_type, **optional_params)` → 返回 `{ytk, mbnt, sub_model, ...}`
- [ ] 2.3 定义4个子模型的默认参数集合（DEFAULT_PARAMS），包含 RPH/R/Y/S/元素含量/FertN/Ndep/pHtarget 等~15个参数
- [ ] 2.4 实现可选参数覆盖逻辑：API 传入的可选参数（RPH/R/Y/S/FertN/Ndep/pHtarget）覆盖默认值，元素含量参数（Yp/Yk/Yca/Ymg/Sp/Sk/Sca/Smg/YN/SN）保持内置
- [ ] 2.5 实现输入校验：SJD 范围 [3.0, 10.0]、JHX/JLA 非负；越界返回 `status="rejected"` + 越界字段列表
- [ ] 2.6 实现子模型选择逻辑：land_type × fertilizer_type → 4子模型之一；非法值回退默认（upland + compound）并追加 warning
- [ ] 2.7 保留旧函数 `classify_acidification`/`generate_amendment`/`calculate_lime_demand` 标记为 deprecated（不删除，避免破坏其他引用），但 `query_acidification`/`evaluate_acidification` 改为委托新模型或标记 deprecated

## 3. model_4.py 入口实现

- [ ] 3.1 在 `framework/domain/other_models/model_4.py` 实现 `model_4_execution(input_data, land_type=None, fertilizer_type=None)` 入口函数
- [ ] 3.2 `model_4_execution` 内部调用 `calculate_acidification_amendment`，处理输入映射（SJD→pHstart、JHX→Hex、JLA→Alex）
- [ ] 3.3 `model_4_execution` 返回标准化结构：`{status, ytk, mbnt, land_type, fertilizer_type, model_version, warning, customized_params}`
- [ ] 3.4 支持 parcel_id 补充 SJD：若 input_data 包含 parcel_id 但无 SJD，从 evaluation_results 表查询 SJD

## 4. AcidificationRemediationAgent 适配

- [ ] 4.1 更新 `framework/agents/specialized/acidification_agent.py` 的 `execute` 方法，调用 `model_4_execution` 而非旧 `query_acidification`
- [ ] 4.2 更新 `answer_question` 方法，从 context 提取 `fertilizer_type` 并透传给 `model_4_execution`
- [ ] 4.3 更新 answer 生成逻辑：使用 ytk/mbnt 替代 lime_demand/amendment_rate，移除 GB/T 42817-2023 引用
- [ ] 4.4 更新 MOCK_INPUTS：新增 `jhx`（交换性氢）和 `jla`（交换性铝）默认值，保留 `exchangeable_al` 用于向后兼容
- [ ] 4.5 移除 `_get_real_acidification` 中的 DB 查询逻辑，改为直接调用 `model_4_execution`

## 5. API 层透传

- [ ] 5.1 在 `framework/agents/nodes.py` 的 `execute_models` 函数中，将 `fertilizer_type` 加入透传参数列表（与 `land_type` 并列）
- [ ] 5.2 在 `framework/api/routes/chat.py` 的 `chat` 函数中，从请求体提取 `fertilizer_type` 并注入 `orchestrator_request`
- [ ] 5.3 确保 `fertilizer_type` 在 context 中流转到 AcidificationRemediationAgent（与 land_type 流转路径一致）

## 6. 测试

- [ ] 6.1 新增 `tests/test_model4_acidification.py`：测试4个子模型的计算正确性（使用模型5源码示例值 pHstart=4.31, Hex=1.56, Alex=4.08 验证 YTK/MBNT 输出）
- [ ] 6.2 测试子模型选择：land_type × fertilizer_type 的4种组合各选对子模型
- [ ] 6.3 测试非法参数回退：land_type="foo" / fertilizer_type="bar" → 回退默认 + warning
- [ ] 6.4 测试输入校验：缺少 JHX/JLA → rejected；SJD 越界 → rejected
- [ ] 6.5 测试可选参数覆盖：传入 FertN=200 → 计算结果与默认不同 + customized_params 标注
- [ ] 6.6 测试 parcel_id 补充 SJD：提供 parcel_id + JHX + JLA（无 SJD）→ 从 DB 查 SJD 并计算
- [ ] 6.7 更新 `tests/test_agent_specialized.py` 中 AcidificationRemediationAgent 的 mock，适配新参数和返回结构
- [ ] 6.8 验证 question_type=2 路由仍指向 model-4（回归测试）

## 7. 文档更新

- [ ] 7.1 更新 `docs/openapi.json`：新增 `fertilizer_type` 请求参数；更新响应字段（lime_demand → ytk/mbnt）
- [ ] 7.2 更新 `docs/api.md`：酸化改良 API 参数说明和响应字段说明
- [ ] 7.3 更新 `README.md`：酸化模型描述（从规则导向改为过程模型，4子模型）

```

## openspec/changes/replace-acidification-with-process-model/specs/farmland-acidification-improvement-model/spec.md

- Source: openspec/changes/replace-acidification-with-process-model/specs/farmland-acidification-improvement-model/spec.md
- Lines: 1-68
- SHA256: e9ec5de84626784bdc09f2322846948cec6f774ec513841530ccdf4599a0509a

```md
## MODIFIED Requirements

### Requirement: 模型3 酸化因子提取
系统 SHALL 从请求参数中提取过程酸化模型所需的三普输入数据（pHstart 对应 SJD、交换性氢对应 JHX、交换性铝对应 JLA），以及子模型选择参数（land_type、fertilizer_type），为后续过程计算提供基础数据。

#### Scenario: 提取三普输入与子模型参数
- **WHEN** 系统收到酸化改良请求，且包含 SJD（pH）、JHX（交换性氢）、JLA（交换性铝）字段
- **THEN** 系统 SHALL 提取 pHstart=SJD、Hex=JHX、Alex=JLA，并读取 land_type（默认 upland）和 fertilizer_type（默认 compound）用于子模型选择

#### Scenario: 缺少必填输入
- **WHEN** 系统收到酸化改良请求，但缺少 JHX（交换性氢）或 JLA（交换性铝）
- **THEN** 系统 SHALL 返回 status="rejected" 和缺少必填字段的错误提示

### Requirement: 模型3 酸化程度分区
系统 SHALL 根据 land_type（水田 paddy / 旱地 upland）和 fertilizer_type（尿素 urea / 复合肥 compound）的组合，从4个过程子模型中选择唯一一个执行酸化计算。子模型映射：paddy_urea、paddy_compound、upland_urea、upland_compound。

#### Scenario: 水田复合肥（默认）
- **WHEN** land_type="paddy" 且 fertilizer_type="compound"（或 fertilizer_type 未传，默认 compound）
- **THEN** 系统 SHALL 选择 paddy_compound 子模型执行计算

#### Scenario: 旱地尿素
- **WHEN** land_type="upland"（或未传，默认 upland）且 fertilizer_type="urea"
- **THEN** 系统 SHALL 选择 upland_urea 子模型执行计算

#### Scenario: 非法参数回退
- **WHEN** land_type 或 fertilizer_type 为非法值（非 upland/paddy 或非 urea/compound）
- **THEN** 系统 SHALL 回退到默认值（upland + compound）并在 warning 中追加参数非法提示

### Requirement: 模型3 改良方案生成
系统 SHALL 使用选定的过程子模型，基于 pHstart、Hex、Alex 和~15个默认参数（RPH/R/Y/S/元素含量/FertN/Ndep/pHtarget 等），计算改良剂需求量：亿土康 YTK（kg/ha）和木本泥炭 MBNT（kg/ha）。部分默认参数（RPH/R/Y/S/FertN/Ndep/pHtarget）SHALL 支持通过 API 可选参数覆盖。

#### Scenario: 默认参数计算
- **WHEN** 系统使用默认参数执行过程模型计算，且 pHstart/Hex/Alex 均在合理范围内
- **THEN** 系统 SHALL 返回 YTK（亿土康 kg/ha）和 MBNT（木本泥炭 kg/ha）的数值结果

#### Scenario: 自定义参数覆盖
- **WHEN** API 请求中包含可选参数（如 FertN=200、pHtarget=6.0）
- **THEN** 系统 SHALL 使用传入值覆盖默认参数执行计算，并在结果中标注哪些参数被自定义

#### Scenario: 输入值越界
- **WHEN** pHstart 超出 [3.0, 10.0] 范围，或 Hex/Alex 为负值
- **THEN** 系统 SHALL 返回 status="rejected" 和越界字段列表

### Requirement: 模型3 酸化改良在线查询
系统 SHALL 提供按需计算接口，API 请求参数直接触发过程模型计算并返回结果，不依赖 DB 预计算。若请求包含 parcel_id，系统 MAY 从 evaluation_results 表查询 SJD 值作为 pHstart 补充输入，但 JHX/JLA 必须由请求显式提供。

#### Scenario: 按需计算
- **WHEN** 调用方以 SJD/JHX/JLA 参数发起请求
- **THEN** 系统 SHALL 直接执行过程模型计算并返回 YTK/MBNT，无需 DB 查询

#### Scenario: parcel_id 补充 SJD
- **WHEN** 调用方提供 parcel_id 但未提供 SJD，且 evaluation_results 表中存在该地块的 SJD 值
- **THEN** 系统 SHALL 从 DB 查询 SJD 作为 pHstart，与请求中的 JHX/JLA 一起执行计算

#### Scenario: parcel_id 查无数据
- **WHEN** 调用方提供 parcel_id 但 evaluation_results 表中无该地块，且请求未提供 SJD
- **THEN** 系统 SHALL 返回 status="rejected" 和"无法获取 pH 值，请提供 SJD 参数"的提示

### Requirement: 模型3 改良方案输出格式
系统 SHALL 以标准化格式输出改良方案，包含改良剂需求量（YTK/MBNT）、子模型标识和参数信息。不暴露中间产酸量分解（Adep/Acrop/ANcy/Aagri/Aback）。

#### Scenario: 标准化输出
- **WHEN** 系统成功完成过程模型计算
- **THEN** 输出 SHALL 包含：status（success/rejected）、ytk（亿土康 kg/ha）、mbnt（木本泥炭 kg/ha）、land_type、fertilizer_type、model_version、warning（可选）

#### Scenario: 错误输出
- **WHEN** 系统因输入缺失或越界无法完成计算
- **THEN** 输出 SHALL 包含：status="rejected"、reason（missing_input / input_out_of_range / invalid_parameter）、缺失或越界字段列表

```
