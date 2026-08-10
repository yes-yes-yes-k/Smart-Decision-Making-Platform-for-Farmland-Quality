# Comet Design Handoff

- Change: add-routing-exclusive-rules
- Phase: design
- Mode: compact
- Context hash: 52c21eeb65d7e5fe4afb6bfd856930f9716bb114972e16a79b4a95bbf0654d6d

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/add-routing-exclusive-rules/proposal.md

- Source: openspec/changes/add-routing-exclusive-rules/proposal.md
- Lines: 1-24
- SHA256: bce2c0b5a52fb5b1093fa676c0d08444b4e8414471ab0a6feacf8aa4de4c2df0

```md
## Why

当前路由为两阶段路由（关键词优先 + 向量回退），在重叠模型之间（model-3/障碍诊断与 model-7/质量等级评价、model-2/提升潜力与 model-7/质量等级评价、model-4/酸化调理剂与 model-6/有机质投入量）容易误选，系统无法区分"业务任务、分析尺度、数据类型、预期输出、模型依赖"这五类路由特征。缺少排他规则导致易混淆问题被路由到错误的专业 Agent，且对尚未由专业团队确认的重叠关系（如 model-3 与 model-7 的评价维度重叠）系统会自行选择而非明确降级提示。

## What Changes

- 在 `framework/agents/capabilities.py` 的 `ProfessionalCapability` 中增加**分析尺度**（省/县/片区/地块）与**数据类型**（指标数据/评价结果/处方用量）维度。
- 在 `framework/agents/router.py` 中实现可维护、可版本化的**排他规则配置**：现状评价→model-3；潜力→model-2；有机质投入量→model-6；酸化调理剂→model-4；稳定性风险→model-1；质量等级评价→model-7。
- 实现「模型边界待确认」降级状态：对未由专业团队确认的重叠关系返回显式降级提示，而非自行选择。
- 将路由判定逻辑从 `framework/agents/nodes.py` 模块化为独立路由模块，便于版本管理与回归测试。
- 扩充路由测试集：针对 model-3/7、model-2/7、model-4/6 三组易混淆对，各准备不少于 20 条正例和反例问题。

## Capabilities

### New Capabilities
- `routing-exclusive-rules`: 五维路由特征与排他规则配置，用于消除重叠模型之间的误选，并对未确认的重叠关系提供「模型边界待确认」降级。

### Modified Capabilities
- `role-based-routing`: 现有问题类型路由将升级为五维路由（业务任务-分析尺度-数据类型-预期输出-模型依赖），并引入排他规则与「模型边界待确认」降级状态。

## Impact

- 代码：`framework/agents/capabilities.py`、`framework/agents/router.py`、`framework/agents/nodes.py`（路由逻辑模块化）、新增独立路由模块。
- 测试：`tests/test_question_type_keywords.py` 扩充，新增三组易混淆对测试集。
- API：路由结果可能新增「模型边界待确认」降级状态，影响 `/api/v1/chat/` 响应结构。
```

## openspec/changes/add-routing-exclusive-rules/design.md

- Source: openspec/changes/add-routing-exclusive-rules/design.md
- Lines: 1-51
- SHA256: 891fe2e9fdce7af377db2d2f63848f86ba9fcfa1adfe32a7e2171f142e5c3a2f

```md
## Context

现有路由为两阶段路由（关键词优先 + 向量回退），实现在 `framework/agents/nodes.py` 的 `identify_question_type` 中。路由仅依赖 `question_type`（1-7 与 0=RAG）做 1:1 映射到单一 Agent，缺少对重叠模型之间判别所必需的路由特征。易混淆对包括：
- model-3（障碍诊断）与 model-7（质量等级评价）：共享"等级/评价"语义。
- model-2（提升潜力）与 model-7（质量等级评价）：均涉及"等级提升"。
- model-4（酸化调理剂）与 model-6（有机质投入量）：均涉及"投入量/用量"。

`ProfessionalCapability` 目前仅含 question_type、minimal_inputs 等元数据，无分析尺度（省/县/片区/地块）与数据类型（指标数据/评价结果/处方用量）维度。

## Goals / Non-Goals

**Goals:**
- 将路由升级为五维路由：业务任务、分析尺度、数据类型、预期输出、模型依赖。
- 建立可维护、可版本化的排他规则配置，消除三组易混淆对误选。
- 对未由专业团队确认的重叠关系返回「模型边界待确认」显式降级状态。
- 将路由判定逻辑从 nodes.py 模块化为独立路由模块。
- 扩充三组易混淆对测试集（各 ≥20 条正例与反例）。

**Non-Goals:**
- 不实现工具注册中心（4.2）、统一数据对象与适配器（4.3）、任务编排器（4.4）、调用状态机（4.5）、结果保护 Guardrails（4.6）、可观测性（4.7）、端到端流程（4.8）。
- 不改变 `question_type` 到 Agent 的既有 1:1 映射数据结构，仅在其之上叠加五维特征与排他规则。

## Decisions

### 决策 1：五维路由特征来源与判定顺序
- **判定顺序**：业务任务 → 分析尺度 → 数据类型 → 预期输出 → 模型依赖，逐级缩小候选 Agent 集合。
- **来源**：优先从 `request` 上下文（如 `parcel_id`、`area_code`、`scale`）与问题文本提取；文本无法确定时使用关键词/向量判定当前维度。
- **理由**：保持向后兼容，未显式提供某一维度时沿用现有 question_type 路由作为兜底，避免破坏现有 470 个测试。

### 决策 2：排他规则独立配置文件
- 在 `framework/agents/router.py` 同级新增 `exclusive_rules.py`（或 `routing_rules.py`），以数据驱动方式声明排他规则，规则可版本化、可单测。
- 每条规则声明：易混淆模型对、判别维度、判定条件、命中目标 Agent。
- **理由**：将规则从 nodes.py 硬编码判断中解耦，便于专业团队确认后增量维护。

### 决策 3：「模型边界待确认」降级状态
- 当排他规则无法消解重叠（优先级冲突或未配置）时，路由返回显式降级状态，标记 `routing_status: "boundary_pending"`，而非自行选择。
- 由 `identify_question_type` 返回可识别的降级信号，`route_models` 分支处理，最终在 API 响应中体现。
- **理由**：符合 docx 要求"对未确认的重叠关系系统返回'模型边界待确认'而非自行选择"。

### 决策 4：路由逻辑模块化
- 抽取 `framework/agents/nodes.py` 中 `identify_question_type`、`_identify_question_type_keyword`、`_identify_question_type_vector`、`check_relevance` 至独立路由模块（如 `framework/agents/routing.py`），nodes.py 保留图节点组装。
- **理由**：独立模块便于版本管理、回归测试，符合 docx 4.1 任务 5。

### 决策 5：测试集扩充方式
- 扩充 `tests/test_question_type_keywords.py`，新增三组混淆对测试模块（model-3/7、model-2/7、model-4/6），各 ≥20 条正例 + 反例。
- 正例断言路由到正确 Agent/question_type；反例断言不误选到易混淆对。

## Risks / Trade-offs

- [五维特征可能无法从问题文本提取] → 保持现有 question_type 兜底路由，未提供维度时降级为现状行为。
- [排他规则冲突导致误路由] → 「模型边界待确认」降级状态兜底，禁止静默选择；规则单测覆盖冲突场景。
- [模块化重构破坏现有测试] → 保持 `identify_question_type` 等对外函数签名不变，新增模块仅迁移内部实现。
```

## openspec/changes/add-routing-exclusive-rules/tasks.md

- Source: openspec/changes/add-routing-exclusive-rules/tasks.md
- Lines: 1-24
- SHA256: a7cf37ae4bd588d96b323f6953d91d69fe8261623b48e47897a252b9ac70953b

```md
## 1. 五维路由特征扩展

- [ ] 1.1 在 `framework/agents/capabilities.py` 的 `ProfessionalCapability` 中增加 `analysis_scale`（省/县/片区/地块）与 `data_type`（指标数据/评价结果/处方用量）字段，并为 7 个 capability 填充默认维度
- [ ] 1.2 新增 `framework/agents/routing.py` 独立路由模块，迁移 `identify_question_type`、`_identify_question_type_keyword`、`_identify_question_type_vector`、`check_relevance` 等判定逻辑，保持对外函数签名不变
- [ ] 1.3 在 `framework/agents/nodes.py` 中改为从 `routing.py` 导入路由函数，保留图节点状态组装与分支调度

## 2. 排他规则配置

- [ ] 2.1 新增排他规则配置文件（如 `framework/agents/exclusive_rules.py`），以数据驱动方式声明 model-3/7、model-2/7、model-4/6 三组易混淆对及其判别条件
- [ ] 2.2 实现排他规则判定逻辑：现状评价→model-3；潜力→model-2；有机质投入量→model-6；酸化调理剂→model-4；稳定性风险→model-1；质量等级评价→model-7
- [ ] 2.3 实现「模型边界待确认」降级状态 `routing_status: "boundary_pending"`，重叠无法消解时返回显式降级而非自行选择

## 3. 路由集成与 API 响应

- [ ] 3.1 在 `route_models` 分支中处理「模型边界待确认」降级信号，不调用任一易混淆专业 Agent
- [ ] 3.2 在 `aggregate_results` 中透传 `routing_status` 与「模型边界待确认」提示到 `/api/v1/chat/` 响应结构
- [ ] 3.3 运行现有测试确认五维路由叠加不破坏既有 `question_type` 1:1 路由行为

## 4. 路由测试集扩充

- [ ] 4.1 扩充 `tests/test_question_type_keywords.py`，新增 model-3/7 易混淆对测试（≥20 条正例 + 反例）
- [ ] 4.2 新增 model-2/7 易混淆对测试（≥20 条正例 + 反例）
- [ ] 4.3 新增 model-4/6 易混淆对测试（≥20 条正例 + 反例）
- [ ] 4.4 新增排他规则与「模型边界待确认」降级状态测试
- [ ] 4.5 运行全部路由测试并生成扩充报告，确认整体正确率达标
```

## openspec/changes/add-routing-exclusive-rules/specs/role-based-routing/spec.md

- Source: openspec/changes/add-routing-exclusive-rules/specs/role-based-routing/spec.md
- Lines: 1-34
- SHA256: d27503722d84ff002df03eba1dd0380b857d376fabfba64c9f4ab208aeee449c

```md
## MODIFIED Requirements

### Requirement: 智能体组合执行

系统 SHALL 根据统一能力目录的 `question_type` 对 1 至 7 进行一对一专业路由；`question_type=0` SHALL 继续走 RAG，不调用 AgentManager。映射为：1→`model-1`、2→`model-4`、3→`model-3`、4→`model-6`、5→`model-7`、6→`model-2`、7→`model-5`。路由即执行，系统 SHALL NOT 进行二次关键词过滤。

在五维路由生效时，系统 SHALL 在 `question_type` 判定基础之上叠加排他规则：当排他规则命中且能明确判别时，SHALL 路由到排他规则指定的目标 Agent；当排他规则无法消解重叠时，SHALL 返回「模型边界待确认」降级状态，而非自行选择。

#### Scenario: 提升潜力问题调用 model-2
- **WHEN** 用户问题被识别为 type 6 且排他规则判定潜力任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-2/PotentialAssessmentAgent`

#### Scenario: 有机质培肥问题调用 model-5
- **WHEN** 用户问题被识别为 type 7 且排他规则判定培肥任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-5/OrganicMatterAgent`

#### Scenario: 质量等级评价调用 model-7
- **WHEN** 用户问题为质量等级评价且排他规则判定
- **THEN** 系统 SHALL 路由到 `model-7`
- **AND** SHALL NOT 路由到 `model-3`

#### Scenario: 现状障碍识别调用 model-3
- **WHEN** 用户问题为现状/障碍识别且排他规则判定
- **THEN** 系统 SHALL 路由到 `model-3`
- **AND** SHALL NOT 路由到 `model-7`

#### Scenario: 知识性问题走 RAG
- **WHEN** 用户问题被识别为 type 0
- **THEN** 系统 SHALL 路由到 RAG
- **AND** SHALL NOT 调用任何专业 Agent

#### Scenario: 重叠问题模型边界待确认
- **WHEN** 排他规则无法消解 model-3 与 model-7 等重叠关系
- **THEN** 系统 SHALL 返回「模型边界待确认」降级提示
- **AND** SHALL NOT 自行选择任一 Agent
```

## openspec/changes/add-routing-exclusive-rules/specs/routing-exclusive-rules/spec.md

- Source: openspec/changes/add-routing-exclusive-rules/specs/routing-exclusive-rules/spec.md
- Lines: 1-74
- SHA256: 690e05385156c497b1b8923b9e4002f38502ce808ee95c597038cf8c21898922

```md
## ADDED Requirements

### Requirement: 五维路由特征判定

系统 SHALL 在现有问题类型路由之上叠加五维路由判定，五个维度依次为：业务任务、分析尺度、数据类型、预期输出、模型依赖。路由判定 SHALL 逐级缩小候选 Agent 集合，优先从请求上下文与问题文本提取维度特征；无法确定某一维度时 SHALL 回退到现有 `question_type` 路由作为兜底。

#### Scenario: 地块级质量等级评价问题
- **WHEN** 用户提供 `parcel_id` 且问题为质量等级评价（如"我的田耕地质量等级是多少"）
- **THEN** 系统 SHALL 识别分析尺度为地块级、数据类型为评价结果、业务任务为质量等级评价
- **AND** 路由到 `model-7`

#### Scenario: 省级障碍诊断问题
- **WHEN** 用户问题为省级障碍诊断（如"全省耕地质量存在哪些问题"）
- **THEN** 系统 SHALL 识别分析尺度为省级、业务任务为现状/障碍识别
- **AND** 路由到 `model-3`

#### Scenario: 维度缺失回退
- **WHEN** 请求未提供 `parcel_id`、`area_code` 且问题文本无法判定分析尺度
- **THEN** 系统 SHALL 回退到现有 `question_type` 关键词/向量路由
- **AND** SHALL NOT 因维度缺失而拒绝路由

### Requirement: 排他规则配置

系统 SHALL 提供独立、可版本化、可单测的排他规则配置，以数据驱动方式声明易混淆模型对及其判别条件。排他规则 SHALL 覆盖：现状评价→model-3；潜力→model-2；有机质投入量→model-6；酸化调理剂→model-4；稳定性风险→model-1；质量等级评价→model-7。

#### Scenario: 现状评价优先 model-3
- **WHEN** 用户问题为现状/障碍识别（如"我这块地到底有啥毛病"）
- **THEN** 系统 SHALL 依据排他规则路由到 `model-3`
- **AND** SHALL NOT 路由到 `model-7`

#### Scenario: 有机质投入量路由 model-6
- **WHEN** 用户问题为有机质投入量/施肥量预测
- **THEN** 系统 SHALL 依据排他规则路由到 `model-6`
- **AND** SHALL NOT 路由到 `model-4` 或 `model-5`

#### Scenario: 酸化调理剂路由 model-4
- **WHEN** 用户问题为酸化治理与调理剂用量
- **THEN** 系统 SHALL 依据排他规则路由到 `model-4`
- **AND** SHALL NOT 路由到 `model-6`

### Requirement: 模型边界待确认降级状态

当排他规则无法消解模型重叠（如未由专业团队确认 model-3 与 model-7 的评价维度分工）时，系统 SHALL 返回「模型边界待确认」显式降级状态，SHALL NOT 自行选择任一 Agent。路由结果 SHALL 携带 `routing_status: "boundary_pending"` 信号，并在 API 响应中体现。

#### Scenario: 无法消解的重叠问题
- **WHEN** 用户问题同时命中排他规则冲突或多模型重叠且无明确判别条件
- **THEN** 系统 SHALL 返回「模型边界待确认」降级提示
- **AND** SHALL NOT 调用任一易混淆专业 Agent

#### Scenario: 可消解的重叠问题
- **WHEN** 排他规则能明确判别重叠问题归属
- **THEN** 系统 SHALL 正常路由到对应 Agent
- **AND** SHALL NOT 触发「模型边界待确认」降级

### Requirement: 路由逻辑模块化

系统 SHALL 将问题类型判定逻辑从图节点模块中抽取为独立路由模块，对外保持 `identify_question_type` 等函数签名不变，便于版本管理和回归测试。

#### Scenario: 独立路由模块
- **WHEN** 应用加载路由逻辑
- **THEN** 路由判定函数 SHALL 位于独立路由模块中
- **AND** 图节点仅负责状态组装与分支调度

### Requirement: 易混淆对测试集

系统 SHALL 扩充路由测试集，针对 model-3/7、model-2/7、model-4/6 三组易混淆对各提供不少于 20 条正例与反例问题。正例 SHALL 断言路由到正确 Agent/question_type；反例 SHALL 断言不误选到易混淆对。

#### Scenario: 正例路由正确
- **WHEN** 提交易混淆对的正例问题
- **THEN** 系统 SHALL 路由到对应的正确 Agent/question_type

#### Scenario: 反例不误选
- **WHEN** 提交易混淆对的反例问题
- **THEN** 系统 SHALL 不路由到易混淆对中的另一 Agent
- **AND** 测试断言通过
```
