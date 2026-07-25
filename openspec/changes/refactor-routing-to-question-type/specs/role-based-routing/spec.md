## REMOVED Requirements

### Requirement: 用户角色识别
**Reason**: 本次重构将路由依据从用户角色（province/county/farmer）改为问题类型（question_type 1-5）。角色识别逻辑（`ROLE_KEYWORDS` 关键词匹配、`identify_role` 方法、`ROLE_AGENTS` 角色到智能体映射）完全移除，由 `identify_question_type` + `TYPE_AGENTS` 1:1 映射取代。
**Migration**: 客户端不应再依赖 API 响应中的 `role` 字段。改用 `question_type` 字段（1=稳定性、2=酸化、3=障碍诊断、4=肥力、5=质量等级、0=通用/RAG）。`RoleRouter` 类重命名为 `QuestionTypeRouter`，`get_agents_for_role(role)` 替换为 `get_agents_for_type(question_type)`。

## MODIFIED Requirements

### Requirement: 智能体组合执行
系统 SHALL 根据 `question_type` 路由结果，按 1:1 映射执行对应的单一专业智能体，并将结果汇总返回。`TYPE_AGENTS` 映射表定义如下：

- question_type=1 → model-1（StabilityRiskAgent）
- question_type=2 → model-4（AcidificationRemediationAgent）
- question_type=3 → model-3（ProblemIdentificationAgent）
- question_type=4 → model-6（FertilityMLAgent）
- question_type=5 → model-7（FarmlandGradeAgent）
- question_type=0 → 不调用 AgentManager，走 RAG 链路（由 `route_models` 节点保证）

系统 SHALL NOT 对已路由的智能体进行二次关键词过滤（移除 `_should_execute_agent` 方法）。每个 question_type 严格对应单一模型，路由即执行。

model-2（PotentialAssessmentAgent）和 model-5（OrganicMatterAgent）SHALL 保留在 `AgentManager.agents` 注册表中用于向后兼容，但 SHALL NOT 出现在 `TYPE_AGENTS` 映射中，即不被任何 question_type 路由调用。

#### Scenario: type 1 问题仅调用 model-1
- **WHEN** 用户问题被 `identify_question_type` 识别为 type 1（如「我的这块田质量等级稳不稳」）
- **THEN** `AgentManager.process` SHALL 仅调用 model-1（StabilityRiskAgent）
- **AND** SHALL NOT 调用 model-2/3/4/5/6/7

#### Scenario: type 2 问题仅调用 model-4
- **WHEN** 用户问题被识别为 type 2（如「我的田酸化了，pH 是 XX，我要施加多少碱性调理剂」）
- **THEN** `AgentManager.process` SHALL 仅调用 model-4（AcidificationRemediationAgent）
- **AND** SHALL NOT 调用其他模型

#### Scenario: type 3 问题仅调用 model-3
- **WHEN** 用户问题被识别为 type 3（如「我这块地到底有啥毛病」）
- **THEN** `AgentManager.process` SHALL 仅调用 model-3（ProblemIdentificationAgent）
- **AND** SHALL NOT 调用 model-2（PotentialAssessmentAgent）

#### Scenario: type 4 问题仅调用 model-6
- **WHEN** 用户问题被识别为 type 4（如「我的田肥力怎么样」）
- **THEN** `AgentManager.process` SHALL 仅调用 model-6（FertilityMLAgent）
- **AND** SHALL NOT 调用 model-5（OrganicMatterAgent）

#### Scenario: type 5 问题仅调用 model-7
- **WHEN** 用户问题被识别为 type 5（如「我的田耕地质量等级是多少」）
- **THEN** `AgentManager.process` SHALL 仅调用 model-7（FarmlandGradeAgent）
- **AND** SHALL NOT 调用 model-4/5/6

#### Scenario: 单智能体直接回答
- **WHEN** 路由结果只包含一个智能体（1:1 映射的常态）
- **THEN** 系统 SHALL 直接调用该智能体的 `answer_question` 方法返回结果

### Requirement: API 集成
系统 SHALL 通过现有 `/api/v1/chat/` 接口集成多智能体框架，用户提问后触发基于 `question_type` 的智能体调度。

#### Scenario: 聊天接口触发多智能体
- **WHEN** 用户通过 `/api/v1/chat/` 接口提交问题
- **THEN** 系统 SHALL 调用 AgentManager 进行 question_type 路由和智能体调度，返回综合结果
- **AND** SHALL NOT 在响应中返回 `role` 字段（已移除）

#### Scenario: 返回结构化结果
- **WHEN** 多智能体执行完成
- **THEN** API SHALL 返回包含 `question_type`、`agents_invoked`、`summary` 和 `recommendations` 的结构化 JSON 响应
- **AND** SHALL NOT 包含 `role` 字段

### Requirement: Question Type Identification
系统 SHALL 根据用户问题识别问题类型（question_type），路由到对应的专业模型。问题类型关键词 SHALL 覆盖 `专业模型总览表(2).xlsx` 中 3 角色（省市管理端、县域执行端、农户种植端）的经典问题。

问题类型与模型 1:1 映射：
- TYPE_1（等级稳定性/退化风险）→ StabilityRiskAgent (model-1)
- TYPE_2（酸化程度/调理剂/改良方案）→ AcidificationRemediationAgent (model-4)
- TYPE_3（潜力/障碍因素/主要问题）→ ProblemIdentificationAgent (model-3)
- TYPE_4（有机质/有机肥/肥力/有机碳）→ FertilityMLAgent (model-6)
- TYPE_5（耕地质量等级评价/综合指数/障碍度排序）→ FarmlandGradeAgent (model-7)

系统 SHALL NOT 将 TYPE_3 路由到 model-2（PotentialAssessmentAgent），SHALL NOT 将 TYPE_4 路由到 model-5（OrganicMatterAgent）。model-2 和 model-5 保留注册但不被路由调用。

系统 SHALL 在 `identify_question_type` 函数最前端执行知识性问题预检（`_is_knowledge_question`），命中知识性问题模式时直接返回 `(0, 1.0)` 走 RAG，先于 relevance 检查和领域关键词匹配。知识性问题模式 SHALL 包含：
- 开头匹配（强信号）：`"什么是"`、`"何为"`、`"解释"`
- 包含匹配（含义类）：`"是什么意思"`、`"什么意思"`、`"定义"`、`"概念"`、`"含义"`

知识性问题预检 SHALL NOT 匹配具体诊断/评价问题（如「我的田耕地质量等级是多少」「我的田酸化严重吗」），这些问题 SHALL 进入领域关键词匹配路由到对应专业模型。

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
- **THEN** 系统 SHALL 识别为 TYPE_4 并路由到 FertilityMLAgent（不路由到 OrganicMatterAgent）

#### Scenario: 识别质量等级评价问题
- **WHEN** 用户询问"我的田耕地质量等级是多少？"（农户种植端经典问题）
- **THEN** 系统 SHALL 识别为 TYPE_5 并路由到 FarmlandGradeAgent (model-7)

#### Scenario: 关键词优先于向量匹配
- **WHEN** 问题包含具体模型关键词（如"有机肥""酸化程度"）
- **THEN** 系统 SHALL 优先使用关键词匹配路由，即使向量匹配的相关性分数较低

#### Scenario: 知识性问题开头匹配走 RAG
- **WHEN** 用户询问"什么是土壤酸化？"（开头匹配"什么是"）
- **THEN** `_is_knowledge_question` SHALL 返回 True
- **AND** `identify_question_type` SHALL 返回 `question_type=0`
- **AND** 系统 SHALL 路由到 RAG（rag_chat_node），SHALL NOT 路由到 model-4

#### Scenario: 知识性问题含义匹配走 RAG
- **WHEN** 用户询问"耕地质量等级是什么意思？"（包含匹配"是什么意思"）
- **THEN** `_is_knowledge_question` SHALL 返回 True
- **AND** `identify_question_type` SHALL 返回 `question_type=0`
- **AND** 系统 SHALL 路由到 RAG，SHALL NOT 路由到 model-7

#### Scenario: 知识性问题解释类走 RAG
- **WHEN** 用户询问"解释一下 SOC 指标"（开头匹配"解释"）
- **THEN** `_is_knowledge_question` SHALL 返回 True
- **AND** `identify_question_type` SHALL 返回 `question_type=0`
- **AND** 系统 SHALL 路由到 RAG

#### Scenario: 具体诊断问题不被知识性预检误判
- **WHEN** 用户询问"我的田耕地质量等级是多少？"（含"质量等级"领域关键词，但不匹配知识模式）
- **THEN** `_is_knowledge_question` SHALL 返回 False
- **AND** `identify_question_type` SHALL 返回 `question_type=5`
- **AND** 系统 SHALL 路由到 model-7

#### Scenario: 具体酸化问题不被知识性预检误判
- **WHEN** 用户询问"我的田酸化严重吗？"（含"酸化"领域关键词，但不匹配知识模式）
- **THEN** `_is_knowledge_question` SHALL 返回 False
- **AND** `identify_question_type` SHALL 返回 `question_type=2`
- **AND** 系统 SHALL 路由到 model-4
