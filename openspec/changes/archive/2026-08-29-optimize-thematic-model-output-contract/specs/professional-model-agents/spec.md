## MODIFIED Requirements

### Requirement: 专业 Agent 提供可复用的结构化分析

系统 SHALL 为每个正式专业 Agent 提供 `analyze(payload)` 结构化分析入口。该入口必须返回统一模型结果信封，包含 `model_id`、`status`、`subject`、`result`、`meta` 和 `issues`，并遵循 `thematic-model-output-contract` 对状态、问题、模型业务 Schema 和严格 JSON 的要求。`analyze(payload)` 返回的规范结果必须是单模型 API、聊天链路、LLM 上下文和审计投影的唯一业务事实来源。

#### Scenario: Agent 为单模型接口执行分析
- **WHEN** 单模型接口按公开模型 ID 调用正式能力
- **THEN** 对应 Agent 必须使用 `analyze(payload)` 返回规范模型结果
- **AND** 单模型接口必须从该结果生成 `public_full` 投影
- **AND** Agent 禁止额外构造与规范 `result` 冲突的业务结论

#### Scenario: Agent 为聊天链路复用分析
- **WHEN** 聊天链路路由到某个正式 Agent
- **THEN** Agent 的专业答复和模型精简结果必须基于同一次 `analyze(payload)` 结果生成
- **AND** 系统禁止从自然语言答复反向解析结构化结果
- **AND** 系统禁止在聊天详情中嵌入完整分析包的重复副本

#### Scenario: 不同运行路径规范化
- **WHEN** 同一专业 Agent 可从数据库、CSV、SQLite、预计算、ML 或规则路径获得结果
- **THEN** Agent 必须在 `analyze(payload)` 边界将所有路径适配到同一模型业务 Schema
- **AND** 数据来源和模拟状态必须记录在 `meta` 中

#### Scenario: 专业能力目录独立查询
- **WHEN** 调用方需要模型名称、用途、能力边界或运行前提
- **THEN** 系统必须通过专业能力目录提供这些描述
- **AND** 每次模型执行结果禁止重复返回内容相同的 `model` 和 `capability`

