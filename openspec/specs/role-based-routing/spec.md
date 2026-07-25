# role-based-routing Specification

## Purpose
TBD - created by archiving change multi-agent-model-framework. Update Purpose after archive.
## Requirements
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

### Requirement: 耕地质量稳定性风险模型路由
系统 SHALL 为耕地质量稳定性与退化风险识别模型分配 question_type，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问稳定性与退化风险相关问题并路由到对应智能体。

#### Scenario: 稳定性问题路由
- **WHEN** 用户问题包含"稳定性"、"稳定吗"、"质量稳定"等关键词
- **THEN** 系统 SHALL 识别为稳定性问题，路由到 StabilityRiskAgent，调用模型1 的历史变化趋势模块查询

#### Scenario: 退化风险问题路由
- **WHEN** 用户问题包含"退化风险"、"持续退化"、"掉级风险"、"退化趋势"等关键词
- **THEN** 系统 SHALL 识别为退化风险问题，路由到 StabilityRiskAgent，调用模型1 的掉级风险或关键因子退化风险模块查询

### Requirement: 耕地质量等级与障碍度评价路由
系统 SHALL 为耕地质量等级与障碍度评价模型分配 question_type，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问质量等级和障碍度相关问题并路由到对应智能体。

#### Scenario: 质量等级问题路由
- **WHEN** 用户问题包含"质量等级"、"几等"、"等级评价"等关键词，且包含地块代码
- **THEN** 系统 SHALL 识别为质量等级问题，路由到 FarmlandGradeObstacleAgent，通过 subprocess 调用 exe 获取等级结果

#### Scenario: 障碍度诊断问题路由
- **WHEN** 用户问题包含"障碍度"、"障碍因子"、"主要障碍"、"限制因素"等关键词，且包含地块代码
- **THEN** 系统 SHALL 识别为障碍度诊断问题，路由到 FarmlandGradeObstacleAgent，通过 subprocess 调用 exe 获取障碍度排序

### Requirement: 模型3 障碍诊断路由
系统 SHALL 为模型3「耕地质量主要问题精准识别模型」分配 question_type，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问障碍诊断相关问题并路由到对应智能体。

#### Scenario: 障碍诊断问题路由
- **WHEN** 用户问题包含"障碍诊断"、"障碍因素"、"障碍类型"、"精准识别"等关键词
- **THEN** 系统 SHALL 识别为障碍诊断问题，路由到 ObstacleDiagnosisAgent，调用模型3 的在线查询接口获取诊断结果

#### Scenario: 障碍组合问题路由
- **WHEN** 用户问题包含"障碍组合"、"多重障碍"、"障碍叠加"等关键词
- **THEN** 系统 SHALL 识别为障碍组合问题，路由到 ObstacleDiagnosisAgent，调用模型3 的在线查询接口获取障碍组合类型

### Requirement: 模型3 酸化改良路由
系统 SHALL 为模型3「耕地土壤酸化改良模型」分配 question_type，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问酸化改良相关问题并路由到对应智能体。

#### Scenario: 酸化程度问题路由
- **WHEN** 用户问题包含"酸化程度"、"酸化分区"、"酸化评价"等关键词
- **THEN** 系统 SHALL 识别为酸化程度问题，路由到 AcidificationImprovementAgent，调用模型3 的在线查询接口获取酸化程度结果

#### Scenario: 改良方案问题路由
- **WHEN** 用户问题包含"改良方案"、"调理剂"、"酸化治理"、"改良措施"等关键词
- **THEN** 系统 SHALL 识别为改良方案问题，路由到 AcidificationImprovementAgent，调用模型3 的在线查询接口获取改良方案

### Requirement: 缺少地块代码时的提示
系统 SHALL 在用户问题包含质量等级、障碍度或酸化改良关键词但未提供地块代码时，返回提示信息要求用户提供地块统一代码。

#### Scenario: 缺少地块代码提示
- **WHEN** 用户问题包含质量等级、障碍度或酸化改良关键词，但未提供地块代码
- **THEN** 系统 SHALL 返回提示信息，要求用户提供地块统一代码以进行评价查询

