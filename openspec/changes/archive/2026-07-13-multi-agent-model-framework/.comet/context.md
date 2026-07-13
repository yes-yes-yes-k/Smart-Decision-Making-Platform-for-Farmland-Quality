# Comet Design Handoff

- Change: multi-agent-model-framework
- Phase: design
- Mode: compact
- Context hash: e4ac769f91883ce0d95c8efe48cb41d34f062c70b6900cb9b90553df55017a6d

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/multi-agent-model-framework/proposal.md

- Source: openspec/changes/multi-agent-model-framework/proposal.md
- Lines: 1-38
- SHA256: a118c9ef9f580311b0577f21de845d9ad6e5480d11ed8ee83b242cdc1eb38656

```md
## Why

现有框架已集成底层核心引擎（`src/ai_culti_demo`），但缺少面向专业模型的智能体层。Excel「专业模型总览表」定义了 6 个耕地质量专业模型和 3 类用户角色（省市管理端、县域执行端、农户种植端）的问题库，需要将这些模型能力封装为独立智能体，通过中心化编排实现多智能体协作，为不同角色用户提供精准的专业问答和模型计算服务。

## What Changes

- 新增智能体基类 `BaseAgent`，定义统一接口：接收任务、执行模拟计算、返回结构化结果
- 新增 6 个专业智能体，每个对应一个专业模型：
  - `StabilityRiskAgent` — 耕地质量等级稳定性与退化风险识别
  - `PotentialAssessmentAgent` — 耕地质量提升潜力评估
  - `ProblemIdentificationAgent` — 耕地质量主要问题精准识别
  - `AcidificationRemediationAgent` — 耕地土壤酸化改良
  - `OrganicMatterAgent` — 耕地土壤有机质培肥提升
  - `ComprehensiveImprovementAgent` — 耕地综合地力改良提升
- 新增 `AgentManager` 中心化编排器，负责任务分配、智能体调度和结果汇总
- 新增模拟数据层，为每个智能体提供领域内的模拟输入输出数据
- 新增用户角色路由逻辑，根据省市/县域/农户角色将问题路由到正确的智能体组合
- 修改现有 `framework/agents/orchestrator.py`，集成新的多智能体框架
- 修改现有 `framework/api/routes/chat.py`，支持通过聊天接口触发多智能体协作

## Capabilities

### New Capabilities

- `agent-base-framework`: 智能体基类框架，定义 BaseAgent 抽象类、AgentManager 编排器、模拟数据层和通信机制
- `professional-model-agents`: 6 个专业模型智能体实现，每个智能体包含领域知识、模拟计算逻辑和问题回答能力
- `role-based-routing`: 用户角色路由机制，根据省市管理端/县域执行端/农户种植端的问题特征路由到正确的智能体组合

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- **代码影响**: `framework/agents/` 目录新增多个文件，`framework/api/routes/chat.py` 修改调用逻辑
- **API 影响**: `/api/v1/chat/` 接口增强，支持多智能体协作返回结构化结果
- **依赖影响**: 无新增外部依赖，复用现有 LangGraph 框架
- **数据影响**: 使用模拟数据，不依赖真实数据源

```

## openspec/changes/multi-agent-model-framework/design.md

- Source: openspec/changes/multi-agent-model-framework/design.md
- Lines: 1-71
- SHA256: 99b523021b4435a574aff56eff470713b69a423562ece73547ee28ff593fa044

```md
## Context

现有框架已通过 `framework/core_engine/adapter.py` 集成了底层引擎 `src/ai_culti_demo`，提供 6 个专题模型的调用能力。当前 `framework/agents/` 目录包含基于 LangGraph 的编排器，但缺少面向专业模型的独立智能体层。

Excel「专业模型总览表」定义了 6 个专业模型的输入输出规格、模型间依赖关系，以及 3 类用户角色（省市管理端、县域执行端、农户种植端）的经典问题库。需要将这些模型封装为独立智能体，通过中心化编排实现协作。

## Goals / Non-Goals

**Goals:**
- 设计智能体基类 `BaseAgent`，统一智能体接口
- 实现 6 个专业智能体，每个对应一个模型，包含领域知识和模拟计算
- 实现 `AgentManager` 中心化编排器，支持任务分配和结果汇总
- 实现用户角色路由，将问题路由到正确的智能体组合
- 集成到现有 Flask API，通过 `/api/v1/chat/` 接口调用

**Non-Goals:**
- 不连接真实数据源，使用模拟数据
- 不实现真实计算逻辑，采用模拟计算
- 不修改底层引擎 `src/ai_culti_demo`
- 不替换现有 LangGraph 编排器，而是扩展其节点逻辑

## Decisions

### 1. 智能体基类设计

**决策**: 使用抽象基类 `BaseAgent`，定义 `execute(task)` 和 `answer_question(question, context)` 两个核心方法。

**理由**: 统一接口便于 Manager 编排，同时允许每个智能体自定义计算逻辑。`execute` 用于模型计算，`answer_question` 用于问题回答。

**替代方案**: 使用 Protocol 接口 — 但抽象基类更利于复用通用逻辑（如模拟数据加载）。

### 2. 中心化编排模式

**决策**: 使用 `AgentManager` 作为中心编排器，负责：
- 解析用户问题，识别需要的智能体
- 按模型依赖关系调度智能体执行顺序
- 汇总各智能体结果，生成综合回复

**理由**: 中心化编排简单可控，适合模拟环境。模型间存在依赖关系（模型1→模型3→模型6），需要统一调度。

**替代方案**: 去中心化消息传递 — 过于复杂，模拟环境不需要。

### 3. 模拟数据层设计

**决策**: 每个智能体内置模拟数据，包括：
- 模拟输入数据（如 pH=5.5、有机质=25g/kg）
- 模拟计算逻辑（基于阈值的简单规则）
- 模拟输出结果（如"酸化程度: 中度"、"建议施石灰: 50kg/亩"）

**理由**: 独立内置避免跨模块依赖，模拟逻辑足够展示智能体功能。

### 4. 用户角色路由

**决策**: 基于关键词匹配识别用户角色，路由到对应智能体组合：
- 省市管理端 → 模型1(稳定性) + 模型3(问题识别)
- 县域执行端 → 模型1(稳定性) + 模型3(问题识别) + 模型2(潜力)
- 农户种植端 → 模型4(酸化) + 模型5(有机质) + 模型6(综合)

**理由**: 与 Excel 问题库的角色定义一致。

### 5. 与现有编排器集成

**决策**: 扩展现有 `MultiAgentOrchestrator`，在 `execute_models` 节点中调用 `AgentManager`，而非替换整个图。

**理由**: 保持现有 LangGraph 流程不变，最小化改动。

## Risks / Trade-offs

- [模拟数据不真实] → 明确标注为模拟结果，后续可替换为真实计算
- [关键词路由精度有限] → 模拟环境可接受，后续可升级为 LLM 路由
- [智能体间依赖硬编码] → 模拟环境可接受，后续可改为配置驱动

```

## openspec/changes/multi-agent-model-framework/tasks.md

- Source: openspec/changes/multi-agent-model-framework/tasks.md
- Lines: 1-29
- SHA256: eacf3c23e11217f8c4e4293f98b8abc6428ca488142e2e2a480de50ce5ade6fc

```md
## 1. 智能体基类框架

- [ ] 1.1 创建 `framework/agents/base.py`，实现 `BaseAgent` 抽象基类，定义 `execute(task)`、`answer_question(question, context)` 方法和 `name`/`description`/`model_id`/`domain` 属性
- [ ] 1.2 创建 `framework/agents/manager.py`，实现 `AgentManager` 中心化编排器，包含智能体注册、任务分配、依赖调度和结果汇总功能
- [ ] 1.3 创建 `framework/agents/mock_data.py`，实现模拟数据层基类，提供模拟数据加载和阈值规则计算工具

## 2. 专业智能体实现

- [ ] 2.1 创建 `framework/agents/specialized/stability_risk_agent.py`，实现 StabilityRiskAgent（模型1），包含等级稳定性评价和退化风险识别的模拟计算
- [ ] 2.2 创建 `framework/agents/specialized/potential_agent.py`，实现 PotentialAssessmentAgent（模型2），包含提升潜力评估和障碍度值计算的模拟逻辑
- [ ] 2.3 创建 `framework/agents/specialized/problem_agent.py`，实现 ProblemIdentificationAgent（模型3），包含障碍因素识别和障碍组合分析的模拟逻辑
- [ ] 2.4 创建 `framework/agents/specialized/acidification_agent.py`，实现 AcidificationRemediationAgent（模型4），包含酸化程度判定和调理剂施用量计算的模拟逻辑
- [ ] 2.5 创建 `framework/agents/specialized/organic_matter_agent.py`，实现 OrganicMatterAgent（模型5），包含有机质评估和有机肥施用量计算的模拟逻辑
- [ ] 2.6 创建 `framework/agents/specialized/comprehensive_agent.py`，实现 ComprehensiveImprovementAgent（模型6），包含多模型结果综合和分区分类建议的模拟逻辑

## 3. 角色路由与集成

- [ ] 3.1 创建 `framework/agents/router.py`，实现用户角色识别（省市/县域/农户）和智能体组合路由逻辑
- [ ] 3.2 修改 `framework/agents/nodes.py`，在 `execute_models` 节点中集成 AgentManager 调用
- [ ] 3.3 修改 `framework/agents/orchestrator.py`，确保 MultiAgentOrchestrator 正确调用 AgentManager
- [ ] 3.4 修改 `framework/api/routes/chat.py`，支持返回多智能体协作的结构化结果

## 4. 测试与验证

- [ ] 4.1 编写智能体基类和 Manager 的单元测试
- [ ] 4.2 编写每个专业智能体的独立功能测试（验证模拟计算和问题回答）
- [ ] 4.3 编写多智能体协同测试（验证依赖调度和结果汇总）
- [ ] 4.4 编写 API 集成测试（验证 `/api/v1/chat/` 接口触发多智能体协作）
- [ ] 4.5 验证三类用户角色（省市/县域/农户）的问题都能正确路由和返回结果

```

## openspec/changes/multi-agent-model-framework/specs/agent-base-framework/spec.md

- Source: openspec/changes/multi-agent-model-framework/specs/agent-base-framework/spec.md
- Lines: 1-42
- SHA256: 8d0b2347792278d2ded95cea46ba98066ab860481e936188ecf74e0f68dcc0b5

```md
## ADDED Requirements

### Requirement: BaseAgent 抽象基类
系统 SHALL 提供抽象基类 `BaseAgent`，定义智能体的统一接口，包括 `execute(task)` 方法和 `answer_question(question, context)` 方法。

#### Scenario: 智能体执行任务
- **WHEN** Manager 调用智能体的 `execute(task)` 方法，传入任务描述和上下文数据
- **THEN** 智能体 SHALL 返回包含 `status`、`result` 和 `metadata` 的结构化字典

#### Scenario: 智能体回答问题
- **WHEN** 调用智能体的 `answer_question(question, context)` 方法
- **THEN** 智能体 SHALL 返回包含 `answer`、`evidence` 和 `confidence` 的结构化字典

#### Scenario: 智能体元数据
- **WHEN** 创建智能体实例
- **THEN** 智能体 SHALL 包含 `name`、`description`、`model_id` 和 `domain` 属性

### Requirement: AgentManager 中心化编排器
系统 SHALL 提供 `AgentManager` 编排器，负责智能体注册、任务分配、依赖调度和结果汇总。

#### Scenario: 智能体注册
- **WHEN** 系统初始化时
- **THEN** AgentManager SHALL 注册所有 6 个专业智能体，并记录每个智能体的依赖关系

#### Scenario: 任务分配与调度
- **WHEN** 用户提交问题，Manager 识别需要的智能体组合
- **THEN** Manager SHALL 按依赖关系顺序调度智能体执行，前序智能体的输出作为后续智能体的输入

#### Scenario: 结果汇总
- **WHEN** 所有智能体执行完成
- **THEN** Manager SHALL 汇总各智能体结果，生成包含 `summary`、`details` 和 `recommendations` 的综合回复

### Requirement: 模拟数据层
系统 SHALL 为每个智能体提供模拟数据层，包括模拟输入数据、模拟计算逻辑和模拟输出结果。

#### Scenario: 模拟数据加载
- **WHEN** 智能体初始化时
- **THEN** 智能体 SHALL 加载内置的模拟数据集，包含领域相关的输入参数和参考阈值

#### Scenario: 模拟计算执行
- **WHEN** 智能体执行计算任务
- **THEN** 智能体 SHALL 基于阈值规则对模拟数据进行计算，并返回带有 `simulated` 标记的结果

```

## openspec/changes/multi-agent-model-framework/specs/professional-model-agents/spec.md

- Source: openspec/changes/multi-agent-model-framework/specs/professional-model-agents/spec.md
- Lines: 1-71
- SHA256: cc9ace10556ed8775ac8677bac26c2ff62d52003d6bf36996207713ec665560c

```md
## ADDED Requirements

### Requirement: StabilityRiskAgent 智能体
系统 SHALL 实现 `StabilityRiskAgent` 智能体，对应模型1「耕地质量等级稳定性与退化风险识别模型」，负责评价耕地质量等级稳定性并识别退化风险。

#### Scenario: 等级稳定性评价
- **WHEN** 用户询问"全省耕地质量整体稳定吗？"
- **THEN** 智能体 SHALL 返回稳定性总体评价，包括稳定/一般/较弱面积占比，使用模拟数据

#### Scenario: 退化风险识别
- **WHEN** 用户询问"哪些县区高等级耕地存在退化风险？"
- **THEN** 智能体 SHALL 返回高等级不稳定耕地分布、县区排序和面积统计

#### Scenario: 重点关注清单
- **WHEN** 用户询问"哪些对象需要纳入重点关注清单？"
- **THEN** 智能体 SHALL 输出需要关注的县区/乡镇/地块清单，说明风险类型和来源

### Requirement: PotentialAssessmentAgent 智能体
系统 SHALL 实现 `PotentialAssessmentAgent` 智能体，对应模型2「耕地质量提升潜力评估模型」，负责评估耕地质量提升潜力和计算障碍度值。

#### Scenario: 提升潜力评估
- **WHEN** 智能体接收到地块质量指标数据
- **THEN** 智能体 SHALL 计算 11 个评价指标的潜在障碍度值和提升潜力等级

#### Scenario: 目标 pH 计算
- **WHEN** 智能体接收到当前 pH 值和质量目标
- **THEN** 智能体 SHALL 计算目标 pH 或 pH 增加值，供模型1和模型3使用

### Requirement: ProblemIdentificationAgent 智能体
系统 SHALL 实现 `ProblemIdentificationAgent` 智能体，对应模型3「耕地质量主要问题精准识别模型」，负责识别主要/次要障碍因素和障碍组合。

#### Scenario: 障碍因素识别
- **WHEN** 用户询问"耕地在哪些方面有问题？"
- **THEN** 智能体 SHALL 返回主要障碍因素、次要障碍因素和障碍组合统计

#### Scenario: 指标障碍等级统计
- **WHEN** 智能体接收到地块指标数据
- **THEN** 智能体 SHALL 输出每个指标的障碍等级（1~10级频数统计）

### Requirement: AcidificationRemediationAgent 智能体
系统 SHALL 实现 `AcidificationRemediationAgent` 智能体，对应模型4「耕地土壤酸化改良模型」，负责判定酸化程度并计算调理剂施用量。

#### Scenario: 酸化程度判定
- **WHEN** 用户询问"全省耕地酸化程度如何？"
- **THEN** 智能体 SHALL 返回不同酸化等级的比例分布

#### Scenario: 调理剂施用量计算
- **WHEN** 用户询问"如何治理强酸性耕地土壤？施加多少调理剂？"
- **THEN** 智能体 SHALL 返回碱性材料施用量建议（如石灰施用量 kg/亩）

### Requirement: OrganicMatterAgent 智能体
系统 SHALL 实现 `OrganicMatterAgent` 智能体，对应模型5「耕地土壤有机质培肥提升模型」，负责有机质提升评估和有机肥施用量计算。

#### Scenario: 有机质含量评估
- **WHEN** 用户询问"全省耕地土壤有机质含量如何？"
- **THEN** 智能体 SHALL 返回有机质含量空间分布和低值区域识别

#### Scenario: 有机肥施用量计算
- **WHEN** 用户询问"有机肥每亩施用量多少？"
- **THEN** 智能体 SHALL 返回有机肥施用量建议和潜在有机质提升预测值

### Requirement: ComprehensiveImprovementAgent 智能体
系统 SHALL 实现 `ComprehensiveImprovementAgent` 智能体，对应模型6「耕地综合地力改良提升模型」，负责综合多个模型结果形成分区分类的综合提升建议。

#### Scenario: 综合提升建议
- **WHEN** Manager 将模型1-5的结果传递给本智能体
- **THEN** 智能体 SHALL 综合各模型结果，生成分区分类的综合提升建议

#### Scenario: 农户地块综合诊断
- **WHEN** 农户询问"我这块地质量怎么样？"
- **THEN** 智能体 SHALL 返回地块质量等级、稳定性、主要问题和改良建议的综合诊断

```

## openspec/changes/multi-agent-model-framework/specs/role-based-routing/spec.md

- Source: openspec/changes/multi-agent-model-framework/specs/role-based-routing/spec.md
- Lines: 1-38
- SHA256: 7c8069c250b5d9d4f77a998ca759a34d14008f25bbc9364d75ab88461b0ea378

```md
## ADDED Requirements

### Requirement: 用户角色识别
系统 SHALL 基于关键词匹配识别用户角色（省市管理端、县域执行端、农户种植端），并将问题路由到对应的智能体组合。

#### Scenario: 省市管理端路由
- **WHEN** 用户问题包含"全省"、"全市"、"全局"、"政策"等关键词
- **THEN** 系统 SHALL 识别角色为"省市管理端"，路由到 StabilityRiskAgent + ProblemIdentificationAgent

#### Scenario: 县域执行端路由
- **WHEN** 用户问题包含"本县"、"乡镇"、"片区"、"任务"等关键词
- **THEN** 系统 SHALL 识别角色为"县域执行端"，路由到 StabilityRiskAgent + ProblemIdentificationAgent + PotentialAssessmentAgent

#### Scenario: 农户种植端路由
- **WHEN** 用户问题包含"我的田"、"这块地"、"施氮肥"、"施多少"等关键词
- **THEN** 系统 SHALL 识别角色为"农户种植端"，路由到 AcidificationRemediationAgent + OrganicMatterAgent + ComprehensiveImprovementAgent

### Requirement: 智能体组合执行
系统 SHALL 根据路由结果，按依赖关系顺序执行智能体组合，并将结果汇总返回。

#### Scenario: 多智能体协同
- **WHEN** 路由结果包含多个智能体
- **THEN** 系统 SHALL 按依赖顺序执行（如模型1→模型3→模型6），前序输出作为后续输入

#### Scenario: 单智能体直接回答
- **WHEN** 路由结果只包含一个智能体
- **THEN** 系统 SHALL 直接调用该智能体的 `answer_question` 方法返回结果

### Requirement: API 集成
系统 SHALL 通过现有 `/api/v1/chat/` 接口集成多智能体框架，用户提问后触发多智能体协作。

#### Scenario: 聊天接口触发多智能体
- **WHEN** 用户通过 `/api/v1/chat/` 接口提交问题
- **THEN** 系统 SHALL 调用 AgentManager 进行角色路由和智能体调度，返回综合结果

#### Scenario: 返回结构化结果
- **WHEN** 多智能体执行完成
- **THEN** API SHALL 返回包含 `role`、`agents_invoked`、`summary` 和 `details` 的结构化 JSON 响应

```
