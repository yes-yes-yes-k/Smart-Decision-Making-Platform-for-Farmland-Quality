# Comet Design Handoff

- Change: renumber-models-to-thematic
- Phase: design
- Mode: compact
- Context hash: 67b9b8f81c6027c03332981faadf007d4d8e0631e5b3edfe3aa95418681901cd

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/renumber-models-to-thematic/proposal.md

- Source: openspec/changes/renumber-models-to-thematic/proposal.md
- Lines: 1-46
- SHA256: b4b975bf4bc535e509e4ff27f1dbb8d2f9bcb2dac4b9a08df06ef22fd022415d

```md
## Why

当前系统有 7 个专业模型（model-1~7），其编号与实际专题模型编号不一致，且其中 model-2（提升潜力评估）和 model-6（肥力 SOC/Dose 预测）为占位符模型，没有对应的实际专题模型。需要将 model 编号与实际专题模型编号一一对应，仅保留 5 个实际专题模型。

## What Changes

- **BREAKING** 重新编号 agent_id，使其与专题模型编号一一对应：
  - model-1：障碍诊断（原 model-3，obstacle-diagnosis）
  - model-2：酸化改良（原 model-4，acidification-remediation）
  - model-3：有机质提升（原 model-5，organic-matter-improvement）
  - model-4：稳定性风险（原 model-1，stability-risk-evaluation）
  - model-5：质量等级（原 model-7，quality-grade-evaluation）
- **BREAKING** 移除占位符模型 model-2（improvement-potential-assessment）和 model-6（fertility-soc-dose-prediction）
- **BREAKING** question_type 从 1-7 重新编号为 1-5，与新 model 编号对齐
- 更新排他规则，移除对 model-2/model-6 的引用，更新所有 model 编号
- 更新路由关键词映射，同步 question_type 新编号
- 更新 API 响应中的 agent_id 和 model 编号
- 更新测试套件中所有硬编码的 model-N / question_type 引用

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `role-based-routing`：question_type 从 1-7 改为 1-5，映射关系从 1→model-1/2→model-4/... 改为 1→model-1/2→model-2/... 一一对应；移除 type 4（SOC/Dose 预测）和 type 6（提升潜力）路由场景
- `routing-exclusive-rules`：排他规则中移除 model-2（潜力）和 model-6（有机质投入量）相关条目；更新所有 model 编号引用
- `callable-thematic-model-stubs`：正式专业模型从 7 个减为 5 个；移除 model-2/improvement-potential-assessment 和 model-6/fertility-soc-dose-prediction
- `professional-model-agents`：Agent 目录从 7 项减为 5 项；agent_id 重新编号；移除 PotentialAssessmentAgent 和 FertilityMLAgent 及其相关场景

## Impact

- `framework/agents/capabilities.py`：PROFESSIONAL_CAPABILITIES 重新编号和裁剪
- `framework/agents/routing.py`：question_type 关键词映射重新编号
- `framework/agents/exclusive_rules.py`：排他规则更新 model 引用
- `framework/agents/nodes.py`：路由节点引用更新
- `framework/agents/orchestrator.py`：Agent 注册和图边更新
- `framework/agents/manager.py`：AgentManager 注册表更新
- `framework/api/routes/chat.py`：API 响应字段更新
- `src/ai_culti_demo/thematic_models.py`：MODEL_SPECS 和能力目录更新
- `tests/test_question_type_keywords.py`：测试用例更新 model/question_type 引用
- `tests/test_exclusive_rules.py`：排他规则测试更新
- `tests/test_multi_agent.py`：多 Agent 测试更新
- `docs/openapi.json`、`docs/api.md`：API 文档更新

```

## openspec/changes/renumber-models-to-thematic/design.md

- Source: openspec/changes/renumber-models-to-thematic/design.md
- Lines: 1-65
- SHA256: 7f3c0967b095a6ed49ac5380780e330940ad7e6622def86dc55ae8ed4bb85950

```md
## Context

当前系统注册了 7 个专业模型（model-1~7），其 agent_id 编号与实际专题模型编号不一致。实际专题模型仅有 5 个（障碍诊断、酸化改良、有机质提升、稳定性风险、质量等级），其中 model-2（提升潜力评估）和 model-6（肥力 SOC/Dose 预测）为占位符模型。

现有 question_type 到 model 的映射为非一一对应（1→model-1、2→model-4、3→model-3、4→model-6、5→model-7、6→model-2、7→model-5），增加了路由逻辑的复杂性。

## Goals / Non-Goals

**Goals:**
- 将 agent_id 重新编号，使其与专题模型编号一一对应：model-1=障碍诊断、model-2=酸化改良、model-3=有机质提升、model-4=稳定性风险、model-5=质量等级
- 移除占位符模型 model-2（improvement-potential-assessment）和 model-6（fertility-soc-dose-prediction）
- question_type 从 1-7 重新编号为 1-5，与新 model 编号一一对应
- 更新排他规则、路由关键词、API 响应和测试套件

**Non-Goals:**
- 不改变 model_id 字符串标识符（如 obstacle-diagnosis 保持不变）
- 不改变 Agent 内部实现逻辑
- 不改变非专业能力（spatial-structure-analysis, soil-indicator-analysis, multi-factor-collaborative-improvement）
- 不实现新的路由策略或排他规则逻辑

## Decisions

### 决策 1：agent_id 一一对应专题模型编号

新映射关系：
| agent_id | 专题模型 | model_id（不变） | 原 agent_id |
|---|---|---|---|
| model-1 | 障碍诊断 | obstacle-diagnosis | model-3 |
| model-2 | 酸化改良 | acidification-remediation | model-4 |
| model-3 | 有机质提升 | organic-matter-improvement | model-5 |
| model-4 | 稳定性风险 | stability-risk-evaluation | model-1 |
| model-5 | 质量等级 | quality-grade-evaluation | model-7 |

**理由**：agent_id 与专题模型编号一一对应，消除编号混乱，便于沟通和维护。

### 决策 2：question_type 重新编号为 1-5

新映射：1→model-1（障碍诊断）、2→model-2（酸化改良）、3→model-3（有机质提升）、4→model-4（稳定性风险）、5→model-5（质量等级）。type 0 仍为 RAG。

**理由**：question_type 与 agent_id 一一对应简化路由逻辑，不再需要非一一对应的映射表。

### 决策 3：移除占位符模型

移除 model-2（PotentialAssessmentAgent）和 model-6（FertilityMLAgent）及其所有相关代码：capabilities 注册、routing 关键词、exclusive_rules 条目、orchestrator 注册、manager 注册、测试用例。

**理由**：这两个模型为占位符，没有对应的实际专题模型，移除后系统更清晰。

### 决策 4：排他规则更新

排他规则中原引用 model-2（潜力）和 model-6（有机质投入量）的条目移除。剩余排他规则的 model 编号更新为新编号。易混淆对从 model-3/7、model-2/7、model-4/6 调整为 model-1/5（障碍诊断 vs 质量等级）、model-2/3（酸化 vs 有机质，如有重叠）。

**理由**：移除模型后排他规则需同步清理，避免引用不存在的模型。

### 决策 5：model_id 字符串保持不变

`model_id`（如 obstacle-diagnosis、acidification-remediation）保持不变，仅 `agent_id`（model-N）重新编号。LEGACY_MODEL_ALIASES 保持不变。

**理由**：model_id 是对外公开的稳定标识，改变会破坏 API 消费者。agent_id 是内部标识，可安全重新编号。

## Risks / Trade-offs

- [question_type 编号变化可能影响已存储的对话历史] → question_type 为运行时路由值，不持久化存储，无影响
- [排他规则测试需全面更新] → 测试中硬编码的 model-N 引用全部同步更新，确保覆盖率不降
- [API 响应中 agent_id 变化] → agent_id 为内部标识，API 响应主要返回 model_id，影响可控
- [移除模型可能导致导入错误] → 全面清理 import 和注册引用，确保无悬空引用

```

## openspec/changes/renumber-models-to-thematic/tasks.md

- Source: openspec/changes/renumber-models-to-thematic/tasks.md
- Lines: 1-28
- SHA256: aaca2a7b2c5c578b4a24d02405c9088505670859858b2d29122ef06be505eec2

```md
## 1. 核心注册表更新

- [ ] 1.1 更新 `framework/agents/capabilities.py`：重新编号 PROFESSIONAL_CAPABILITIES（model-1=obstacle-diagnosis, model-2=acidification-remediation, model-3=organic-matter-improvement, model-4=stability-risk-evaluation, model-5=quality-grade-evaluation），移除 model-2/improvement-potential-assessment 和 model-6/fertility-soc-dose-prediction，更新 question_type 为 1-5
- [ ] 1.2 更新 `src/ai_culti_demo/thematic_models.py`：MODEL_SPECS 移除 fertility-soc-dose-prediction 和 improvement-potential-assessment 相关条目，更新 NON_PROFESSIONAL_CATEGORIES 引用

## 2. 路由逻辑更新

- [ ] 2.1 更新 `framework/agents/routing.py`：question_type 关键词映射从 1-7 重新编号为 1-5，移除 type 4（SOC/Dose）和 type 6（潜力）关键词组，将原 type 1（稳定性）关键词映射到 type 4，原 type 3（障碍）映射到 type 1，原 type 7（有机质）映射到 type 3
- [ ] 2.2 更新 `framework/agents/exclusive_rules.py`：移除 model-2（潜力）和 model-6（有机质投入量）相关排他规则，更新所有 model 编号引用为新编号，更新易混淆对为 model-1/5 和 model-2/3
- [ ] 2.3 更新 `framework/agents/nodes.py`：路由节点引用更新为新 model 编号和 question_type

## 3. Agent 注册与编排更新

- [ ] 3.1 更新 `framework/agents/manager.py`：AgentManager 注册表移除 PotentialAssessmentAgent（原 model-2）和 FertilityMLAgent（原 model-6），更新剩余 Agent 的 agent_id 为新编号
- [ ] 3.2 更新 `framework/agents/orchestrator.py`：工作流图节点和边引用更新为新 agent_id，移除原 model-2 和 model-6 相关节点

## 4. API 与文档更新

- [ ] 4.1 更新 `framework/api/routes/chat.py`：确保 API 响应中 agent_id 和 question_type 使用新编号
- [ ] 4.2 更新 `framework/api/routes/models.py`：模型列表 API 返回 5 个模型
- [ ] 4.3 更新 `docs/openapi.json` 和 `docs/api.md`：同步模型编号和数量

## 5. 测试套件更新

- [ ] 5.1 更新 `tests/test_question_type_keywords.py`：所有 model-N 引用更新为新编号，移除 model-2/model-6 相关测试用例，question_type 断言更新为 1-5，更新易混淆对为 model-1/5 和 model-2/3
- [ ] 5.2 更新 `tests/test_exclusive_rules.py`：排他规则测试更新 model 引用，移除 model-2/model-6 相关测试
- [ ] 5.3 更新 `tests/test_multi_agent.py`：多 Agent 测试更新 agent_id 引用，移除 model-2/model-6 相关断言
- [ ] 5.4 运行路由相关测试套件验证全部通过

```

## openspec/changes/renumber-models-to-thematic/specs/callable-thematic-model-stubs/spec.md

- Source: openspec/changes/renumber-models-to-thematic/specs/callable-thematic-model-stubs/spec.md
- Lines: 1-15
- SHA256: c4246fa2875664683a1494fdfae87ce29202472f354980ce8509633b340f3da0

```md
## MODIFIED Requirements

### Requirement: 专题能力按正式、辅助与实验性分类发布

系统 MUST 发布统一能力目录。正式专业模型 SHALL 由 5 个专业 Agent 一一提供；`spatial-structure-analysis` SHALL 标记为辅助空间能力，`soil-indicator-analysis` SHALL 标记为辅助指标能力，`multi-factor-collaborative-improvement` SHALL 标记为实验性能力。辅助和实验性能力 SHALL NOT 被列为正式专业模型，也 SHALL NOT 获得聊天 `question_type` 路由。

#### Scenario: 请求默认专业模型清单
- **WHEN** 调用方请求正式专业模型清单
- **THEN** 系统 MUST 返回 5 个正式模型的公开 ID、中文名称、最小输入和运行前提
- **AND** SHALL NOT 返回空间结构、指标分析或协同提升为正式专业模型

#### Scenario: 请求全量能力清单
- **WHEN** 调用方显式请求包含非正式能力的全量清单
- **THEN** 系统 MUST 返回辅助和实验性能力
- **AND** 每项 MUST 标示分类、是否可聊天路由及可靠性状态

```

## openspec/changes/renumber-models-to-thematic/specs/professional-model-agents/spec.md

- Source: openspec/changes/renumber-models-to-thematic/specs/professional-model-agents/spec.md
- Lines: 1-134
- SHA256: e84c516d380da27ff0af58648a9690dfec462aec28b5ac424a89c3d409d7355f

[TRUNCATED]

```md
## MODIFIED Requirements

### Requirement: 专业智能体目录与正式能力一一对应

系统 SHALL 以 5 个已注册专业智能体作为正式专业能力的唯一来源。每个 Agent SHALL 有一个稳定内部 `agent_id`、一个规范公开 `model_id`、明确中文名称、业务边界、最小输入、数据前提、可靠性状态和降级方式。正式能力为：`model-1/obstacle-diagnosis`（障碍诊断）、`model-2/acidification-remediation`（酸化改良）、`model-3/organic-matter-improvement`（有机质提升）、`model-4/stability-risk-evaluation`（稳定性风险）、`model-5/quality-grade-evaluation`（质量等级）。

#### Scenario: 读取正式专业能力目录
- **WHEN** 系统初始化专业能力目录
- **THEN** 目录 SHALL 包含且仅包含 5 项正式专业能力
- **AND** 每一项 SHALL 同时给出 Agent ID、公开模型 ID、名称和运行前提

#### Scenario: Agent 注册引用正式能力定义
- **WHEN** `AgentManager` 注册专业智能体
- **THEN** 每个已注册 Agent SHALL 引用统一能力定义
- **AND** SHALL NOT 在 Manager 内重复维护与能力目录冲突的名称或模型标识

### Requirement: ProblemIdentificationAgent 智能体
系统 SHALL 实现 `ObstacleDiagnosisAgent` 智能体，对应模型1「耕地质量主要问题精准识别模型」，负责识别主要/次要障碍因素和障碍组合。

**模型输入**（来源：xlsx 总览表）：
- 一级农业区、二级农业区、土壤pH、有机质、pH、有效磷、速效钾、容重、耕层质地、灌溉能力、排水能力、地形部位、质地构型、有效土层、地块唯一编码、地块经纬度、地块边界、行政区划边界、农田类型（水田/旱地）

**模型输出**（来源：xlsx 总览表）：
- 主要障碍因素、次要障碍因素、pH障碍等级、有机质障碍等级、有效磷障碍等级、速效钾障碍等级、容重障碍等级、耕层质地障碍等级、灌溉能力障碍等级、排水能力障碍等级、地形部位障碍等级、质地构型障碍等级、有效土层障碍等级、障碍因素组合

#### Scenario: 障碍因素识别
- **WHEN** 用户询问"全省耕地质量存在哪些问题？"
- **THEN** 智能体 SHALL 返回全省/市范围内的主要障碍因素、次要障碍因素和障碍组合统计

#### Scenario: 指标障碍等级统计
- **WHEN** 智能体接收到地块指标数据
- **THEN** 智能体 SHALL 输出每个指标的障碍等级（1~10级频数统计），最后一列为该指标是否主要、次要障碍因素

#### Scenario: 县域障碍诊断
- **WHEN** 县域执行端用户询问"县/乡镇里的耕地在哪些方面有问题"
- **THEN** 智能体 SHALL 统计全区域内的信息，每个指标为一行，列为每个指标1~10等级的频数统计，最后一列为是否主要、次要障碍因素

#### Scenario: 农户地块问题
- **WHEN** 农户询问"我这块地有没有问题？"
- **THEN** 智能体 SHALL 用简单语言说明耕地质量等级、列举低等级的指标

### Requirement: AcidificationRemediationAgent 智能体
系统 SHALL 实现 `AcidificationRemediationAgent` 智能体，对应模型2「耕地土壤酸化改良模型」，负责判定酸化程度并计算调理剂施用量。

**模型输入**（来源：xlsx 总览表）：
- 土壤pH、有机质、阳离子交换量、土壤黏粒、总氮、游离铁、总铁、交换性氢离子、交换性铝离子、全氮、全磷、全钾、游离氧化铁、年降雨量、年降雨pH年均值、施肥类型及施肥量、作物类型及产量、农田类型（水田/旱地）、目标pH（或pH增加值）

**模型输出**（来源：xlsx 总览表）：
- 土壤酸化程度级别、土壤本底酸量、农业活动产酸量、碱性调理剂施用量、木本泥炭施用量

#### Scenario: 酸化程度判定
- **WHEN** 用户询问"查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？"
- **THEN** 智能体 SHALL 按 GB/T 42817-2023 标准（酸性 5.5≤pH<6.5、强酸性 4.5≤pH<5.5、极强酸性 pH<4.5）输出酸化等级和比例

#### Scenario: 调理剂施用量计算
- **WHEN** 农户询问"我的田酸化了，pH是XX，我要施加多少碱性调理剂可以治理好？"
- **THEN** 智能体 SHALL 输出使土壤pH从当前值提升到6.5目标值的碱性调理剂建议施用量，结合 GB/T 42817-2023 和 NY/T 443-2019 标准

#### Scenario: 不同土地利用类型酸化
- **WHEN** 用户询问"查询区域内不同土地利用类型的酸化程度"
- **THEN** 智能体 SHALL 输出旱地、水田、园地、林地等不同土地利用类型土壤的酸化等级及比例

#### Scenario: 农户酸化判断
- **WHEN** 农户询问"我的这块田酸化严重吗？"
- **THEN** 智能体 SHALL 输出该地块土壤酸化等级

### Requirement: OrganicMatterAgent 智能体
系统 SHALL 实现 `OrganicMatterAgent` 智能体，对应模型3「耕地土壤有机质培肥提升模型」，负责有机质提升评估和有机肥施用量计算。

**模型输入**（来源：xlsx 总览表）：
- 土壤pH、有机质、有效磷、速效钾、总氮、阳离子交换量、土壤黏粒、交换性氢离子、交换性铝离子、游离铁、总铁、全氮、全磷、全钾、游离氧化铁、土壤容重、年降雨量、年降雨pH年均值、施肥类型及施肥量、作物类型及产量、农田类型（水田/旱地）、目标土壤有机质

**模型输出**（来源：xlsx 总览表）：
- 有机肥/秸秆、有机肥施用量、秸秆施用量

#### Scenario: 有机质含量评估
- **WHEN** 用户询问"全省耕地土壤有机质含量如何，空间分布情况？"
- **THEN** 智能体 SHALL 返回总体水平（平均含量及高、中、低等级占比）和空间分布（哪些区域较高、较低，是否呈现地形梯度）

#### Scenario: 有机肥施用量计算

```

Full source: openspec/changes/renumber-models-to-thematic/specs/professional-model-agents/spec.md

## openspec/changes/renumber-models-to-thematic/specs/role-based-routing/spec.md

- Source: openspec/changes/renumber-models-to-thematic/specs/role-based-routing/spec.md
- Lines: 1-93
- SHA256: c64431152fef9fc03e0dd62c9f1ef9d038b23361e22e7629f59b4242a67a81ea

[TRUNCATED]

```md
## MODIFIED Requirements

### Requirement: 智能体组合执行

系统 SHALL 根据统一能力目录的 `question_type` 对 1 至 5 进行一对一专业路由；`question_type=0` SHALL 继续走 RAG，不调用 AgentManager。映射为：1→`model-1`（障碍诊断）、2→`model-2`（酸化改良）、3→`model-3`（有机质提升）、4→`model-4`（稳定性风险）、5→`model-5`（质量等级）。路由即执行，系统 SHALL NOT 进行二次关键词过滤。

在五维路由生效时，系统 SHALL 在 `question_type` 判定基础之上叠加排他规则：当排他规则命中且能明确判别时，SHALL 路由到排他规则指定的目标 Agent；当排他规则无法消解重叠时，SHALL 返回「模型边界待确认」降级状态，而非自行选择。

#### Scenario: 障碍诊断问题调用 model-1
- **WHEN** 用户问题被识别为 type 1 且排他规则判定障碍诊断任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-1/ObstacleDiagnosisAgent`

#### Scenario: 酸化改良问题调用 model-2
- **WHEN** 用户问题被识别为 type 2 且排他规则判定酸化改良任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-2/AcidificationRemediationAgent`

#### Scenario: 有机质培肥问题调用 model-3
- **WHEN** 用户问题被识别为 type 3 且排他规则判定培肥任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-3/OrganicMatterAgent`

#### Scenario: 稳定性风险问题调用 model-4
- **WHEN** 用户问题被识别为 type 4 且排他规则判定稳定性风险任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-4/StabilityRiskAgent`

#### Scenario: 质量等级评价调用 model-5
- **WHEN** 用户问题为质量等级评价且排他规则判定
- **THEN** 系统 SHALL 路由到 `model-5`
- **AND** SHALL NOT 路由到 `model-1`

#### Scenario: 现状障碍识别调用 model-1
- **WHEN** 用户问题为现状/障碍识别且排他规则判定
- **THEN** 系统 SHALL 路由到 `model-1`
- **AND** SHALL NOT 路由到 `model-5`

#### Scenario: 知识性问题走 RAG
- **WHEN** 用户问题被识别为 type 0
- **THEN** 系统 SHALL 路由到 RAG
- **AND** SHALL NOT 调用任何专业 Agent

#### Scenario: 重叠问题模型边界待确认
- **WHEN** 排他规则无法消解 model-1 与 model-5 等重叠关系
- **THEN** 系统 SHALL 返回「模型边界待确认」降级提示
- **AND** SHALL NOT 自行选择任一 Agent

### Requirement: 耕地质量稳定性风险模型路由
系统 SHALL 为耕地质量稳定性与退化风险识别模型分配 question_type=4，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问稳定性与退化风险相关问题并路由到对应智能体。

#### Scenario: 稳定性问题路由
- **WHEN** 用户问题包含"稳定性"、"稳定吗"、"质量稳定"等关键词
- **THEN** 系统 SHALL 识别为 type 4，路由到 StabilityRiskAgent，调用模型4 的历史变化趋势模块查询

#### Scenario: 退化风险问题路由
- **WHEN** 用户问题包含"退化风险"、"持续退化"、"掉级风险"、"退化趋势"等关键词
- **THEN** 系统 SHALL 识别为 type 4，路由到 StabilityRiskAgent，调用模型4 的掉级风险或关键因子退化风险模块查询

### Requirement: 耕地质量等级与障碍度评价路由
系统 SHALL 为耕地质量等级与障碍度评价模型分配 question_type=5，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问质量等级和障碍度相关问题并路由到对应智能体。

#### Scenario: 质量等级问题路由
- **WHEN** 用户问题包含"质量等级"、"几等"、"等级评价"等关键词，且包含地块代码
- **THEN** 系统 SHALL 识别为 type 5，路由到 FarmlandGradeObstacleAgent，获取等级结果

#### Scenario: 障碍度诊断问题路由
- **WHEN** 用户问题包含"障碍度"、"障碍因子"、"主要障碍"、"限制因素"等关键词，且包含地块代码
- **THEN** 系统 SHALL 识别为 type 5，路由到 FarmlandGradeObstacleAgent，获取障碍度排序

### Requirement: 障碍诊断路由
系统 SHALL 为障碍诊断模型分配 question_type=1，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问障碍诊断相关问题并路由到对应智能体。

#### Scenario: 障碍诊断问题路由
- **WHEN** 用户问题包含"障碍诊断"、"障碍因素"、"障碍类型"、"精准识别"等关键词
- **THEN** 系统 SHALL 识别为 type 1，路由到 ObstacleDiagnosisAgent，调用障碍诊断在线查询接口获取诊断结果

#### Scenario: 障碍组合问题路由
- **WHEN** 用户问题包含"障碍组合"、"多重障碍"、"障碍叠加"等关键词
- **THEN** 系统 SHALL 识别为 type 1，路由到 ObstacleDiagnosisAgent，调用障碍诊断在线查询接口获取障碍组合类型

### Requirement: 酸化改良路由
系统 SHALL 为酸化改良模型分配 question_type=2，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问酸化改良相关问题并路由到对应智能体。


```

Full source: openspec/changes/renumber-models-to-thematic/specs/role-based-routing/spec.md

## openspec/changes/renumber-models-to-thematic/specs/routing-exclusive-rules/spec.md

- Source: openspec/changes/renumber-models-to-thematic/specs/routing-exclusive-rules/spec.md
- Lines: 1-33
- SHA256: a1d368ccd03bf095235a688dd0b5e6280c4b02a1d30f48ba71bb16533d0aaaf5

```md
## MODIFIED Requirements

### Requirement: 排他规则配置

系统 SHALL 提供独立、可版本化、可单测的排他规则配置，以数据驱动方式声明易混淆模型对及其判别条件。排他规则 SHALL 覆盖：现状评价→model-1；酸化调理剂→model-2；有机质培肥→model-3；稳定性风险→model-4；质量等级评价→model-5。

#### Scenario: 现状评价优先 model-1
- **WHEN** 用户问题为现状/障碍识别（如"我这块地到底有啥毛病"）
- **THEN** 系统 SHALL 依据排他规则路由到 `model-1`
- **AND** SHALL NOT 路由到 `model-5`

#### Scenario: 酸化调理剂路由 model-2
- **WHEN** 用户问题为酸化治理与调理剂用量
- **THEN** 系统 SHALL 依据排他规则路由到 `model-2`
- **AND** SHALL NOT 路由到 `model-3`

#### Scenario: 有机质培肥路由 model-3
- **WHEN** 用户问题为有机肥施用和培肥措施
- **THEN** 系统 SHALL 依据排他规则路由到 `model-3`
- **AND** SHALL NOT 路由到 `model-2`

### Requirement: 易混淆对测试集

系统 SHALL 扩充路由测试集，针对 model-1/5（障碍诊断 vs 质量等级）、model-2/3（酸化 vs 有机质）两组易混淆对各提供不少于 20 条正例与反例问题。正例 SHALL 断言路由到正确 Agent/question_type；反例 SHALL 断言不误选到易混淆对。

#### Scenario: 正例路由正确
- **WHEN** 提交换淆对的正例问题
- **THEN** 系统 SHALL 路由到对应的正确 Agent/question_type

#### Scenario: 反例不误选
- **WHEN** 提交付淆对的反例问题
- **THEN** 系统 SHALL 不路由到易混淆对中的另一 Agent
- **AND** 测试断言通过

```
