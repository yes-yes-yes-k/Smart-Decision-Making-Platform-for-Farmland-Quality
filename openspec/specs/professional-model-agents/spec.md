# professional-model-agents Specification

## Purpose
TBD - created by archiving change multi-agent-model-framework. Update Purpose after archive.
## Requirements
### Requirement: 专业智能体目录与正式能力一一对应

系统 SHALL 以 7 个已注册专业智能体作为正式专业能力的唯一来源。每个 Agent SHALL 有一个稳定内部 `agent_id`、一个规范公开 `model_id`、明确中文名称、业务边界、最小输入、数据前提、可靠性状态和降级方式。正式能力为：`model-1/stability-risk-evaluation`、`model-2/improvement-potential-assessment`、`model-3/obstacle-diagnosis`、`model-4/acidification-remediation`、`model-5/organic-matter-improvement`、`model-6/fertility-soc-dose-prediction`、`model-7/quality-grade-evaluation`。

#### Scenario: 读取正式专业能力目录
- **WHEN** 系统初始化专业能力目录
- **THEN** 目录 SHALL 包含且仅包含 7 项正式专业能力
- **AND** 每一项 SHALL 同时给出 Agent ID、公开模型 ID、名称和运行前提

#### Scenario: Agent 注册引用正式能力定义
- **WHEN** `AgentManager` 注册专业智能体
- **THEN** 每个已注册 Agent SHALL 引用统一能力定义
- **AND** SHALL NOT 在 Manager 内重复维护与能力目录冲突的名称或模型标识

### Requirement: 专业 Agent 提供可复用的结构化分析

系统 SHALL 为每个正式专业 Agent 提供 `analyze(payload)` 结构化分析入口。该入口 SHALL 返回 `status`、`capability`、`summary`、`findings`、`recommendations`、`evidence`、`lineage`、`reliability` 和 `fallback`，并包含成功、数据未就绪、输入不足、拒绝或降级时的机器可读状态。

#### Scenario: Agent 为单模型接口执行分析
- **WHEN** 单模型接口按公开模型 ID 调用正式能力
- **THEN** 对应 Agent SHALL 使用 `analyze(payload)` 返回结构化结果
- **AND** 结果 SHALL 标示实际数据来源、可靠性和降级状态

#### Scenario: Agent 为聊天链路复用分析
- **WHEN** 聊天链路路由到某个正式 Agent
- **THEN** Agent 的专业答复 SHALL 基于同一次 `analyze(payload)` 结果生成
- **AND** SHALL NOT 另行产生与单模型接口冲突的专业计算结论

### Requirement: 肥力预测与有机质培肥边界明确

系统 SHALL 将 `model-6` 限定为 SOC/Dose 等肥力预测能力，将 `model-5` 限定为有机肥、秸秆还田和培肥措施等治理建议能力。两项能力 SHALL 在名称、输入、输出、路由关键词和可靠性说明上可区分。

#### Scenario: 查询 SOC 或 Dose 预测
- **WHEN** 用户请求 SOC、有机碳、Dose、施肥量预测或预测置信度
- **THEN** 系统 SHALL 使用 `model-6/fertility-soc-dose-prediction`
- **AND** 返回预测值、模型可用性和置信度/降级说明

#### Scenario: 查询有机质培肥方案
- **WHEN** 用户请求有机肥施用、秸秆还田或有机质培肥措施
- **THEN** 系统 SHALL 使用 `model-5/organic-matter-improvement`
- **AND** SHALL NOT 将治理方案伪装为 SOC 或 Dose 预测

