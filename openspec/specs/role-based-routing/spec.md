# role-based-routing Specification

## Purpose
TBD - created by archiving change multi-agent-model-framework. Update Purpose after archive.
## Requirements
### Requirement: 用户角色识别
系统 SHALL 基于关键词匹配识别用户角色（省市管理端、县域执行端、农户种植端），并将问题路由到对应的智能体组合。

农户种植端（farmer）角色 SHALL 包含 model-7（FarmlandGradeAgent），使 farmer 问「我的田质量等级」时能触发耕地质量等级评价。model-7 的实际执行受 `AgentManager._should_execute_agent` 关键词过滤约束——仅当问题含 `QUESTION_TYPE_5_KEYWORDS` 时执行，否则跳过。

#### Scenario: 省市管理端路由
- **WHEN** 用户问题包含"全省"、"全市"、"全局"、"政策"等关键词
- **THEN** 系统 SHALL 识别角色为"省市管理端"，路由到 StabilityRiskAgent + ProblemIdentificationAgent

#### Scenario: 县域执行端路由
- **WHEN** 用户问题包含"本县"、"乡镇"、"片区"、"任务"等关键词
- **THEN** 系统 SHALL 识别角色为"县域执行端"，路由到 StabilityRiskAgent + ProblemIdentificationAgent + PotentialAssessmentAgent

#### Scenario: 农户种植端路由
- **WHEN** 用户问题包含"我的田"、"这块地"、"施氮肥"、"施多少"等关键词
- **THEN** 系统 SHALL 识别角色为"农户种植端"，路由到 AcidificationRemediationAgent (model-4) + OrganicMatterAgent (model-5) + FertilityMLAgent (model-6) + FarmlandGradeAgent (model-7)

#### Scenario: farmer 质量等级问题触发 model-7
- **WHEN** farmer 角色问题包含"质量等级"、"等级评价"、"综合指数"等 `QUESTION_TYPE_5_KEYWORDS` 关键词
- **THEN** 系统 SHALL 执行 model-7（FarmlandGradeAgent），调用 fortran exe 获取真实质量等级评价（如 `parcel_code` 可用）

#### Scenario: farmer 非质量等级问题跳过 model-7
- **WHEN** farmer 角色问题不含 `QUESTION_TYPE_5_KEYWORDS` 关键词（如「我的田肥力怎么样」）
- **THEN** 系统 SHALL 跳过 model-7（status=`skipped`, reason=`question_not_related`）
- **AND** SHALL 只执行 model-4/5/6

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

