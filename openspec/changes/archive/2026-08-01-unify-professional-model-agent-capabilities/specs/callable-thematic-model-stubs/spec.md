## REMOVED Requirements

### Requirement: 系统提供 6 个可调用的模拟专题模型目录
正式专业模型目录改为以 7 个专业 Agent 为准，原六模型目录不再适用。

## ADDED Requirements

### Requirement: 专题能力按正式、辅助与实验性分类发布

系统 MUST 发布统一能力目录。正式专业模型 SHALL 由 7 个专业 Agent 一一提供；`spatial-structure-analysis` SHALL 标记为辅助空间能力，`soil-indicator-analysis` SHALL 标记为辅助指标能力，`multi-factor-collaborative-improvement` SHALL 标记为实验性能力。辅助和实验性能力 SHALL NOT 被列为正式专业模型，也 SHALL NOT 获得聊天 `question_type` 路由。

#### Scenario: 请求默认专业模型清单
- **WHEN** 调用方请求正式专业模型清单
- **THEN** 系统 MUST 返回 7 个正式模型的公开 ID、中文名称、最小输入和运行前提
- **AND** SHALL NOT 返回空间结构、指标分析或协同提升为正式专业模型

#### Scenario: 请求全量能力清单
- **WHEN** 调用方显式请求包含非正式能力的全量清单
- **THEN** 系统 MUST 返回辅助和实验性能力
- **AND** 每项 MUST 标示分类、是否可聊天路由及可靠性状态

### Requirement: 正式专业模型复用 Agent 的统一结构化调用

系统 MUST 允许调用方以正式公开 `model_id` 调用对应专业 Agent 的结构化分析，返回统一字段 `status`、`capability`、`summary`、`findings`、`recommendations`、`evidence`、`lineage`、`reliability` 和 `fallback`。

#### Scenario: 调用酸化改良专业模型
- **WHEN** 调用方以 `model_id=acidification-remediation` 和满足前提的输入发起调用
- **THEN** 系统 MUST 调用 `model-4` 的结构化分析
- **AND** 返回与聊天链路同源的酸化判断、改良建议和可靠性状态

#### Scenario: 调用不具备 Agent 对应关系的辅助能力
- **WHEN** 调用方调用空间结构或关键指标辅助能力
- **THEN** 系统 MUST 返回其辅助能力分类和 Demo/数据状态
- **AND** SHALL NOT 声明已调用专业 Agent

### Requirement: 旧模型标识的迁移行为可解释

系统 MUST 为可无歧义映射到正式专业能力的旧公开模型 ID 提供兼容行为，并在响应中返回规范 `model_id` 和弃用提示。系统 MUST NOT 将无 Agent 对应关系的旧模型 ID 映射为不等价的正式专业能力。

#### Scenario: 使用酸化治理旧模型标识
- **WHEN** 调用方使用可映射的旧酸化治理模型标识
- **THEN** 系统 MUST 返回 `acidification-remediation` 作为规范模型标识
- **AND** 返回可迁移提示

#### Scenario: 使用协同提升模型标识
- **WHEN** 调用方使用 `multi-factor-collaborative-improvement`
- **THEN** 系统 MUST 将其标示为实验性能力
- **AND** SHALL NOT 映射到 `model-6` 或其他正式专业 Agent
