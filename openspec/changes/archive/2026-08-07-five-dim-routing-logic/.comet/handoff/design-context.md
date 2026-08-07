# Comet Design Handoff

- Change: five-dim-routing-logic
- Phase: design
- Mode: compact
- Context hash: 8f8103e9aa1b44df465ce6096834cb37b22213d46e0a8524c8513558dfa52c70

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/five-dim-routing-logic/proposal.md

- Source: openspec/changes/five-dim-routing-logic/proposal.md
- Lines: 1-29
- SHA256: 3761e6c574aa974f99122b09a564e6b6994a273290b52618e124b19c885f6a97

```md
## Why

五维路由（业务任务、分析尺度、数据类型、预期输出、模型依赖）在 v1 中仅为「关键词排他规则 + 五维元数据声明」：`_extract_five_dim_context` 提取了分析尺度和数据类型，`ProfessionalCapability` 声明了 `analysis_scale`/`data_type` 字段，但 `apply_exclusive_rules` 的 `context` 参数完全未参与路由判定。spec 要求"五维路由判定 SHALL 逐级缩小候选 Agent 集合"，当前实现不满足该要求。本次变更让五维特征真正参与路由判定，完善 v1 版本。

## What Changes

- 新增**业务任务关键词表**，从问题文本独立提取业务任务标签（障碍诊断/酸化改良/有机质培肥/稳定性评价/质量等级评价）
- 新增**预期输出关键词表**，从问题文本独立提取预期输出标签（评价结果/处方用量/诊断报告）
- 扩展 `ExclusiveRule` 数据结构，支持以分析尺度/数据类型/业务任务/预期输出作为判别条件（当前仅支持问题文本关键词子串匹配）
- 更新 `apply_exclusive_rules`，让 `context` 参数（含 scale/data_type）真正参与路由判定
- 更新 `_extract_five_dim_context`，增加业务任务和预期输出的提取
- 扩展排他规则覆盖两组新增判别场景：地块评价 vs 地块诊断（model-1/5）、处方用量区分（model-2/3）
- 保持 `boundary_pending` 降级机制：维度无法消解歧义时仍返回降级状态

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `routing-exclusive-rules`: 更新「五维路由特征判定」需求，从"元数据声明与上下文预留"升级为"五维特征全量参与判定"；扩展排他规则判别条件支持分析尺度/数据类型/业务任务/预期输出维度

## Impact

- **代码**：`framework/agents/exclusive_rules.py`（扩展规则结构与判定逻辑）、`framework/agents/routing.py`（维度提取与集成）、`framework/agents/nodes.py`（`_extract_five_dim_context` 扩展）、`framework/agents/capabilities.py`（维度字段确认）
- **测试**：`tests/test_exclusive_rules.py`（新增维度判别测试）、`tests/test_question_type_keywords.py`（新增五维路由场景测试）
- **API**：不修改 API 响应结构，`routing_status`/`boundary_pending` 机制不变

```

## openspec/changes/five-dim-routing-logic/design.md

- Source: openspec/changes/five-dim-routing-logic/design.md
- Lines: 1-61
- SHA256: dfe814bc8d47e3ab38f112a57079e19bf6cf164edc6f0e395be4cfd2585b2ac7

```md
## Context

五维路由在 v1 中（archived change `add-routing-exclusive-rules`）实现为「关键词排他规则 + 五维元数据声明」：`_extract_five_dim_context` 提取了 `scale`（省/县/片区/地块）和 `data_type`（指标数据/评价结果/处方用量），`ProfessionalCapability` 声明了 `analysis_scale`/`data_type` 字段，但 `apply_exclusive_rules` 的 `context` 参数完全未参与路由判定——该参数仅为兼容调用签名而保留。

当前 `apply_exclusive_rules` 仅使用问题文本关键词子串匹配（`EXCLUSIVE_CONDITION_KEYWORDS`），覆盖四组条件：现状评价、酸化调理剂、稳定性风险、质量等级评价。排他规则的 `ExclusiveRule` 结构有 `discriminator` 字段（声明判别维度）但判定逻辑不读取该字段，也不读取 `context` 中的维度值。

v1 设计文档明确记录：「后续如需让分析尺度/数据类型真正影响路由，需退回设计阶段扩展排他规则与测试」。本次变更即完成该升级。

## Goals / Non-Goals

**Goals:**
- 让五维特征（业务任务、分析尺度、数据类型、预期输出、模型依赖）真正参与路由判定
- 新增业务任务关键词表和预期输出关键词表，从问题文本独立提取维度标签
- 扩展 `ExclusiveRule` 判定逻辑，支持以分析尺度/数据类型/业务任务/预期输出作为判别条件
- 让 `apply_exclusive_rules` 的 `context` 参数真正参与路由判定
- 覆盖两组新增判别场景：地块评价 vs 地块诊断（model-1/5）、处方用量区分（model-2/3）
- 保持 `boundary_pending` 降级机制

**Non-Goals:**
- 不改变现有 `question_type` 关键词/向量路由的基础逻辑（作为兜底）
- 不引入机器学习模型做维度提取
- 不修改 API 响应结构
- 不新增独立的模型依赖判定步骤（模型依赖通过排他规则 pair 声明间接参与）

## Decisions

### 决策 A：维度提取扩展
在 `_extract_five_dim_context` 中新增业务任务和预期输出的提取：
- **业务任务**：新增 `BUSINESS_TASK_KEYWORDS` 关键词表，从问题文本提取（如"诊断/毛病"→障碍诊断，"治酸/调理剂"→酸化改良，"有机肥/培肥"→有机质培肥，"稳定性/退化"→稳定性评价，"等级/评价"→质量等级评价）
- **预期输出**：新增 `EXPECTED_OUTPUT_KEYWORDS` 关键词表，从问题文本提取（如"等级/指数"→评价结果，"施多少/每亩"→处方用量，"诊断/问题"→诊断报告）
- 分析尺度和数据类型沿用现有提取逻辑
- **理由**：用户确认业务任务和预期输出均通过新增关键词表提取，不从 data_type 推导

### 决策 B：排他规则判别条件扩展
扩展 `ExclusiveRule` 结构，增加 `dimension_conditions` 字段支持多维度判别：
- 现有 `condition`（问题文本关键词）保留，新增 `dimension_conditions: Dict[str, str]`（如 `{"scale": "地块", "data_type": "评价结果"}`）
- 判定逻辑：一条规则匹配当且仅当 `condition` 匹配（如有）**且**所有 `dimension_conditions` 匹配 context 中对应维度值
- 无 `condition` 的规则仅依赖维度条件；无 `dimension_conditions` 的规则仅依赖关键词（向后兼容）
- **理由**：用户确认扩展排他规则判别条件，维度作为 additional discriminators

### 决策 C：排他规则覆盖新增场景
在 `EXCLUSIVE_RULES` 中新增维度驱动的规则：
- model-1/5：`scale=地块 + data_type=评价结果 + 业务任务=质量等级评价` → model-5
- model-1/5：`scale=地块 + 业务任务=障碍诊断` → model-1
- model-2/3：`data_type=处方用量 + 业务任务=酸化改良` → model-2
- model-2/3：`data_type=处方用量 + 业务任务=有机质培肥` → model-3
- **理由**：用户确认需要地块评价 vs 地块诊断和处方用量区分两组场景

### 决策 D：模型依赖间接参与
模型依赖维度通过排他规则的 `pair` 声明间接参与——规则匹配过程本身就是模型依赖的体现。不新增独立判定步骤。
- **理由**：用户确认通过排他规则间接参与

### 决策 E：boundary_pending 保持
当维度条件无法消解歧义（多条规则命中不同 target，或维度信息不足以区分易混淆对）时，仍返回 `routing_status: "boundary_pending"`。
- **理由**：用户确认保持现有 boundary_pending 降级策略

## Risks / Trade-offs

- **[维度提取精度]** → 关键词表覆盖度有限，可能漏判或误判。缓解：测试集覆盖正例反例 ≥20 条/组
- **[规则冲突复杂度]** → 新增维度条件后规则间可能产生新的冲突路径。缓解：保持 `matched_targets > 1 → boundary_pending` 的冲突处理逻辑
- **[向后兼容]** → 现有纯关键词规则需保持行为不变。缓解：无 `dimension_conditions` 的规则仅依赖关键词，向后兼容

```

## openspec/changes/five-dim-routing-logic/tasks.md

- Source: openspec/changes/five-dim-routing-logic/tasks.md
- Lines: 1-28
- SHA256: 582214b7f7b462861e5ec4cffa78ed6a8a33eb0fa3e91b6287d5c3b0097689a1

```md
## 1. 维度提取扩展

- [ ] 1.1 在 `framework/agents/nodes.py` 的 `_extract_five_dim_context` 中新增业务任务提取：定义 `BUSINESS_TASK_KEYWORDS` 关键词表（障碍诊断/酸化改良/有机质培肥/稳定性评价/质量等级评价），从问题文本提取 `business_task` 标签写入 context
- [ ] 1.2 在 `framework/agents/nodes.py` 的 `_extract_five_dim_context` 中新增预期输出提取：定义 `EXPECTED_OUTPUT_KEYWORDS` 关键词表（评价结果/处方用量/诊断报告），从问题文本提取 `expected_output` 标签写入 context
- [ ] 1.3 确认 `_extract_five_dim_context` 返回的 context 包含 `scale`、`data_type`、`business_task`、`expected_output` 四个维度字段

## 2. 排他规则结构扩展

- [ ] 2.1 在 `framework/agents/exclusive_rules.py` 的 `ExclusiveRule` dataclass 中新增 `dimension_conditions: Dict[str, str]` 字段（默认空 dict），用于声明维度判别条件（如 `{"scale": "地块", "data_type": "评价结果"}`）
- [ ] 2.2 新增 `_dimension_conditions_match(dimension_conditions, context)` 函数：检查 context 中对应维度值是否全部匹配 dimension_conditions
- [ ] 2.3 更新 `apply_exclusive_rules` 判定逻辑：一条规则匹配当且仅当 `condition` 匹配（如有）**且** `dimension_conditions` 全部匹配；无 `condition` 的规则仅依赖维度条件；无 `dimension_conditions` 的规则仅依赖关键词（向后兼容）

## 3. 排他规则覆盖新增场景

- [ ] 3.1 在 `EXCLUSIVE_RULES` 中新增 model-1/5 维度判别规则：`dimension_conditions={"scale":"地块","data_type":"评价结果","business_task":"质量等级评价"}` → model-5
- [ ] 3.2 在 `EXCLUSIVE_RULES` 中新增 model-1/5 维度判别规则：`dimension_conditions={"scale":"地块","business_task":"障碍诊断"}` → model-1
- [ ] 3.3 在 `EXCLUSIVE_RULES` 中新增 model-2/3 维度判别规则：`dimension_conditions={"data_type":"处方用量","business_task":"酸化改良"}` → model-2
- [ ] 3.4 在 `EXCLUSIVE_RULES` 中新增 model-2/3 维度判别规则：`dimension_conditions={"data_type":"处方用量","business_task":"有机质培肥"}` → model-3
- [ ] 3.5 确认现有纯关键词规则（无 dimension_conditions）保持向后兼容行为不变

## 4. 测试验证

- [ ] 4.1 在 `tests/test_exclusive_rules.py` 中新增维度判别测试：地块级质量等级评价 → model-5、地块级障碍诊断 → model-1、酸化调理剂用量 → model-2、有机肥施用量 → model-3
- [ ] 4.2 在 `tests/test_exclusive_rules.py` 中新增维度冲突降级测试：五维特征命中多条指向不同模型的规则 → boundary_pending
- [ ] 4.3 在 `tests/test_exclusive_rules.py` 中新增维度缺失回退测试：无 scale/data_type 时回退到 question_type 关键词路由
- [ ] 4.4 在 `tests/test_question_type_keywords.py` 中新增业务任务和预期输出提取测试
- [ ] 4.5 在 `tests/test_question_type_keywords.py` 中新增向后兼容测试：无 context 时行为与 v1 一致
- [ ] 4.6 运行 `python -m pytest tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_multi_agent.py -q`，全部通过为验收标准

```

## openspec/changes/five-dim-routing-logic/specs/routing-exclusive-rules/spec.md

- Source: openspec/changes/five-dim-routing-logic/specs/routing-exclusive-rules/spec.md
- Lines: 1-43
- SHA256: 9149fe6199fa424285e57c87a23a25ccf486b81de6fc0fd7fa4a7b00f332563f

```md
## MODIFIED Requirements

### Requirement: 五维路由特征判定

系统 SHALL 在现有问题类型路由之上叠加五维路由判定，五个维度依次为：业务任务、分析尺度、数据类型、预期输出、模型依赖。路由判定 SHALL 逐级缩小候选 Agent 集合，优先从请求上下文与问题文本提取维度特征；无法确定某一维度时 SHALL 回退到现有 `question_type` 路由作为兜底。五维特征 SHALL 真正参与排他规则判定：`apply_exclusive_rules` SHALL 读取 `context` 中的分析尺度和数据类型，并结合从问题文本提取的业务任务和预期输出标签，作为排他规则的判别条件。

#### Scenario: 地块级质量等级评价问题
- **WHEN** 用户提供 `parcel_id` 且问题为质量等级评价（如"我的田耕地质量等级是多少"）
- **THEN** 系统 SHALL 识别分析尺度为地块级、数据类型为评价结果、业务任务为质量等级评价
- **AND** 路由到 `model-5`

#### Scenario: 地块级障碍诊断问题
- **WHEN** 用户提供 `parcel_id` 且问题为障碍诊断（如"我这块地到底有啥毛病"）
- **THEN** 系统 SHALL 识别分析尺度为地块级、业务任务为障碍诊断
- **AND** 路由到 `model-1`
- **AND** SHALL NOT 路由到 `model-5`

#### Scenario: 省级障碍诊断问题
- **WHEN** 用户问题为省级障碍诊断（如"全省耕地质量存在哪些问题"）
- **THEN** 系统 SHALL 识别分析尺度为省级、业务任务为现状/障碍识别
- **AND** 路由到 `model-1`

#### Scenario: 酸化调理剂用量问题
- **WHEN** 用户问题为酸化治理与调理剂用量（如"我的田酸化了要施多少石灰"）
- **THEN** 系统 SHALL 识别数据类型为处方用量、业务任务为酸化改良
- **AND** 路由到 `model-2`
- **AND** SHALL NOT 路由到 `model-3`

#### Scenario: 有机肥施用量问题
- **WHEN** 用户问题为有机肥施用和培肥措施（如"有机肥每亩施用量多少"）
- **THEN** 系统 SHALL 识别数据类型为处方用量、业务任务为有机质培肥
- **AND** 路由到 `model-3`
- **AND** SHALL NOT 路由到 `model-2`

#### Scenario: 维度缺失回退
- **WHEN** 请求未提供 `parcel_id`、`area_code` 且问题文本无法判定分析尺度
- **THEN** 系统 SHALL 回退到现有 `question_type` 关键词/向量路由
- **AND** SHALL NOT 因维度缺失而拒绝路由

#### Scenario: 维度冲突无法消解
- **WHEN** 五维特征命中多条指向不同模型的排他规则，无法消解歧义
- **THEN** 系统 SHALL 返回「模型边界待确认」降级状态
- **AND** SHALL NOT 调用任一易混淆专业 Agent

```
