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

#### Scenario: 酸化程度问题路由
- **WHEN** 用户问题包含"酸化程度"、"酸化分区"、"酸化评价"等关键词
- **THEN** 系统 SHALL 识别为 type 2，路由到 AcidificationRemediationAgent，获取酸化程度结果

#### Scenario: 改良方案问题路由
- **WHEN** 用户问题包含"改良方案"、"调理剂"、"酸化治理"、"改良措施"等关键词
- **THEN** 系统 SHALL 识别为 type 2，路由到 AcidificationRemediationAgent，获取改良方案

## REMOVED Requirements

### Requirement: Question Type Identification
**Reason**: model-6（肥力 SOC/Dose 预测）和 model-2（提升潜力）已移除，对应的 type 4（SOC/Dose）和 type 6（潜力）路由不再需要。
**Migration**: SOC/Dose 相关问题不再有对应的专业模型；有机肥施用问题改由 type 3（model-3 有机质提升）处理。
