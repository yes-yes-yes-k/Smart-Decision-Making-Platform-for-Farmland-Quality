# role-based-routing Specification

## Purpose
TBD - created by archiving change multi-agent-model-framework. Update Purpose after archive.
## Requirements
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

### Requirement: Question Type Identification
系统 SHALL 根据用户问题识别问题类型（question_type），路由到对应的专业模型。问题类型关键词 SHALL 覆盖 `专业模型总览表(2).xlsx` 中 3 角色（省市管理端、县域执行端、农户种植端）的经典问题。

问题类型与模型映射：
- TYPE_1（等级稳定性/退化风险）→ StabilityRiskAgent (model-1)
- TYPE_2（酸化程度/调理剂/改良方案）→ AcidificationRemediationAgent (model-4)
- TYPE_3（潜力/障碍因素/主要问题）→ ProblemIdentificationAgent (model-3) / PotentialAssessmentAgent (model-2)
- TYPE_4（有机质/有机肥/肥力/有机碳）→ FertilityMLAgent (model-6) / OrganicMatterAgent (model-5)

#### Scenario: 识别省市管理端问题
- **WHEN** 用户询问"查询区域内耕地质量等级整体稳定吗？"（省市管理端经典问题）
- **THEN** 系统 SHALL 识别为 TYPE_1 并路由到 StabilityRiskAgent

#### Scenario: 识别县域执行端问题
- **WHEN** 用户询问"本县哪些乡镇或地块等级稳定性较弱？"（县域执行端经典问题）
- **THEN** 系统 SHALL 识别为 TYPE_1 并路由到 StabilityRiskAgent

#### Scenario: 识别农户种植端问题
- **WHEN** 用户询问"我的这块田质量等级稳不稳？"（农户种植端经典问题）
- **THEN** 系统 SHALL 识别为 TYPE_1 并路由到 StabilityRiskAgent

#### Scenario: 识别酸化治理问题
- **WHEN** 用户询问"我的田酸化了，pH是XX，我要施加多少碱性调理剂？"（农户种植端经典问题）
- **THEN** 系统 SHALL 识别为 TYPE_2 并路由到 AcidificationRemediationAgent

#### Scenario: 识别有机质培肥问题
- **WHEN** 用户询问"为了提升耕地土壤有机质，有机肥每亩施用量多少？"（农户种植端经典问题）
- **THEN** 系统 SHALL 识别为 TYPE_4 并路由到 FertilityMLAgent 或 OrganicMatterAgent

#### Scenario: 关键词优先于向量匹配
- **WHEN** 问题包含具体模型关键词（如"有机肥""酸化程度"）
- **THEN** 系统 SHALL 优先使用关键词匹配路由，即使向量匹配的相关性分数较低

