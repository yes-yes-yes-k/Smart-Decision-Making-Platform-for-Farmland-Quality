# role-based-routing Specification

## Purpose
TBD - created by archiving change multi-agent-model-framework. Update Purpose after archive.

## Requirements

### Requirement: 智能体组合执行

系统 SHALL 根据统一能力目录的 `question_type` 对 1 至 6 进行一对一专业路由；`question_type=0` SHALL 继续走 RAG，不调用 AgentManager。映射为：1→`model-1`（稳定性风险）、2→`model-2`（质量等级评价）、3→`model-3`（障碍诊断）、4→`model-4`（酸化改良）、5→`model-5`（有机质培肥）、6→`model-6`（占位符）。路由即执行，系统 SHALL NOT 进行二次关键词过滤。

在 `ROUTING_MODE=llm` 且 LLM 可用时，系统 SHALL 先经 LLM 初判 `question_type`，再叠加排他规则；LLM 不可用或解析失败时回退关键词/向量判定。在五维路由生效时，系统 SHALL 在 `question_type` 判定基础之上叠加排他规则：当排他规则命中且能明确判别时，SHALL 路由到排他规则指定的目标 Agent；当排他规则无法消解重叠时，SHALL 返回「模型边界待确认」降级状态，而非自行选择。

#### Scenario: 障碍诊断问题调用 model-3
- **WHEN** 用户问题被识别为 type 3 且排他规则判定障碍诊断任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-3/ObstacleDiagnosisAgent`

#### Scenario: 酸化改良问题调用 model-4
- **WHEN** 用户问题被识别为 type 4 且排他规则判定酸化改良任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-4/AcidificationRemediationAgent`

#### Scenario: 有机质培肥问题调用 model-5
- **WHEN** 用户问题被识别为 type 5 且排他规则判定培肥任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-5/OrganicMatterAgent`

#### Scenario: 稳定性风险问题调用 model-1
- **WHEN** 用户问题被识别为 type 1 且排他规则判定稳定性风险任务
- **THEN** `AgentManager.process` SHALL 仅调用 `model-1/StabilityRiskAgent`

#### Scenario: 质量等级评价调用 model-2
- **WHEN** 用户问题为质量等级评价且排他规则判定
- **THEN** 系统 SHALL 路由到 `model-2`
- **AND** SHALL NOT 路由到 `model-3`

#### Scenario: 现状障碍识别调用 model-3
- **WHEN** 用户问题为现状/障碍识别且排他规则判定
- **THEN** 系统 SHALL 路由到 `model-3`
- **AND** SHALL NOT 路由到 `model-2`

#### Scenario: 知识性问题走 RAG
- **WHEN** 用户问题被识别为 type 0
- **THEN** 系统 SHALL 路由到 RAG
- **AND** SHALL NOT 调用任何专业 Agent

#### Scenario: 重叠问题模型边界待确认
- **WHEN** 排他规则无法消解 model-3 与 model-2 等重叠关系
- **THEN** 系统 SHALL 返回「模型边界待确认」降级提示
- **AND** SHALL NOT 自行选择任一 Agent

#### Scenario: LLM 初判后路由
- **WHEN** `ROUTING_MODE=llm` 且 LLM 可用
- **THEN** 系统 SHALL 先经 LLM 初判 `question_type`
- **AND** 将 LLM 结果叠加排他规则后路由到对应 model

#### Scenario: LLM 不可用时回退关键词
- **WHEN** `ROUTING_MODE=llm` 但 LLM 不可用或 JSON 解析失败
- **THEN** 系统 SHALL 回退关键词/向量判定
- **AND** 路由行为与 `keyword` 模式一致，不中断

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

### Requirement: 耕地质量稳定性风险模型路由
系统 SHALL 为耕地质量稳定性与退化风险识别模型分配 question_type=1，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问稳定性与退化风险相关问题并路由到对应智能体。

#### Scenario: 稳定性问题路由
- **WHEN** 用户问题包含"稳定性"、"稳定吗"、"质量稳定"等关键词
- **THEN** 系统 SHALL 识别为 type 1，路由到 StabilityRiskAgent，调用模型1 的历史变化趋势模块查询

#### Scenario: 退化风险问题路由
- **WHEN** 用户问题包含"退化风险"、"持续退化"、"掉级风险"、"退化趋势"等关键词
- **THEN** 系统 SHALL 识别为 type 1，路由到 StabilityRiskAgent，调用模型1 的掉级风险或关键因子退化风险模块查询

### Requirement: 耕地质量等级与障碍度评价路由
系统 SHALL 为耕地质量等级与障碍度评价模型分配 question_type=2，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问质量等级和障碍度相关问题并路由到对应智能体。

#### Scenario: 质量等级问题路由
- **WHEN** 用户问题包含"质量等级"、"几等"、"等级评价"等关键词，且包含地块代码
- **THEN** 系统 SHALL 识别为 type 2，路由到 FarmlandGradeObstacleAgent，获取等级结果

#### Scenario: 障碍度诊断问题路由
- **WHEN** 用户问题包含"障碍度"、"障碍因子"、"主要障碍"、"限制因素"等关键词，且包含地块代码
- **THEN** 系统 SHALL 识别为 type 2，路由到 FarmlandGradeObstacleAgent，获取障碍度排序

### Requirement: 模型3 障碍诊断路由
系统 SHALL 为障碍诊断模型分配 question_type=3，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问障碍诊断相关问题并路由到对应智能体。

#### Scenario: 障碍诊断问题路由
- **WHEN** 用户问题包含"障碍诊断"、"障碍因素"、"障碍类型"、"精准识别"等关键词
- **THEN** 系统 SHALL 识别为 type 3，路由到 ObstacleDiagnosisAgent，调用障碍诊断在线查询接口获取诊断结果

#### Scenario: 障碍组合问题路由
- **WHEN** 用户问题包含"障碍组合"、"多重障碍"、"障碍叠加"等关键词
- **THEN** 系统 SHALL 识别为 type 3，路由到 ObstacleDiagnosisAgent，调用障碍诊断在线查询接口获取障碍组合类型

### Requirement: 模型4 酸化改良路由
系统 SHALL 为酸化改良模型分配 question_type=4，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问酸化改良相关问题并路由到对应智能体。

#### Scenario: 酸化程度问题路由
- **WHEN** 用户问题包含"酸化程度"、"酸化分区"、"酸化评价"等关键词
- **THEN** 系统 SHALL 识别为 type 4，路由到 AcidificationRemediationAgent，获取酸化程度结果

#### Scenario: 改良方案问题路由
- **WHEN** 用户问题包含"改良方案"、"调理剂"、"酸化治理"、"改良措施"等关键词
- **THEN** 系统 SHALL 识别为 type 4，路由到 AcidificationRemediationAgent，获取改良方案

### Requirement: 缺少地块代码时的提示
系统 SHALL 在用户问题包含质量等级、障碍度或酸化改良关键词但未提供地块代码时，返回提示信息要求用户提供地块统一代码。

#### Scenario: 缺少地块代码提示
- **WHEN** 用户问题包含质量等级、障碍度或酸化改良关键词，但未提供地块代码
- **THEN** 系统 SHALL 返回提示信息，要求用户提供地块统一代码以进行评价查询

### Requirement: 路由失败不回退到隐式多模型组合

系统 SHALL 在 AgentManager 或已路由 Agent 失败时保留当前能力的结构化状态。系统 SHALL NOT 使用旧的 `QUESTION_TYPE_TO_MODEL_ID` 多模型组合回退，也 SHALL NOT 在响应中执行未声明的其他专业 Agent。

#### Scenario: 已路由 Agent 执行失败
- **WHEN** 已路由的专业 Agent 抛出异常或返回未就绪状态
- **THEN** 系统 SHALL 返回当前 `question_type`、对应 Agent ID、错误/降级原因和可用专业结果
- **AND** SHALL NOT 调用额外的专业 Agent

### Requirement: model-5 肥力字段透传

系统 SHALL 通过 `/api/v1/chat/` 将 `area_code`、`land_type`、规范土壤字段及 `SJD/YJZ/TD/TL/TJ/YXL/SXJ/YJZTSZ/YJFLX` 外部字段透传至 model-5；type 5 返回 `agents_invoked=["model-5"]` 及真实或明确降级的模型元数据。type 6 SHALL 继续只调用 model-6 占位 Agent。

#### Scenario: type 5 韶关请求
- **WHEN** type 5 请求包含 `area_code=lechang`、土地类型和土壤特征
- **THEN** API SHALL 返回对应 RF 的 `model_version`、Dose 和可靠性状态
