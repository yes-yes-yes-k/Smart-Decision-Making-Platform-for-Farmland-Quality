## ADDED Requirements

### Requirement: 可控 LLM 调用策略

系统 SHALL 支持通过环境变量配置单次 LLM 调用的超时和最大重试次数，并记录每次调用的结果和耗时。

#### Scenario: 配置单次调用预算

- **WHEN** 设置 `SILICONFLOW_LLM_TIMEOUT` 或 `SILICONFLOW_LLM_MAX_RETRIES`
- **THEN** LLM 服务 SHALL 使用配置的超时和重试次数创建聊天客户端

#### Scenario: 记录调用可观测信息

- **WHEN** LLM 服务发起、成功完成或失败完成一次调用
- **THEN** 系统 SHALL 记录模型标识、调用阶段、耗时和失败类型，且不得记录密钥内容
