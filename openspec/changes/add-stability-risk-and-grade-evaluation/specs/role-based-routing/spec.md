## ADDED Requirements

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
