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
