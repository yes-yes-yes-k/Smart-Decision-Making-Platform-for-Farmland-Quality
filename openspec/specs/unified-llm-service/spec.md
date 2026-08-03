# unified-llm-service Specification

## Purpose
TBD - created by archiving change migrate-and-unify-framework. Update Purpose after archive.
## Requirements
### Requirement: Unified LLM Service Interface
The system SHALL provide a unified LLM service interface that supports multiple LLM providers and models.

#### Scenario: Configure LLM provider via environment variables
- **WHEN** the system starts with SILICONFLOW_API_KEY set
- **THEN** the LLM service SHALL initialize with the configured provider

#### Scenario: Generate text with LLM
- **WHEN** a user requests text generation with a prompt
- **THEN** the system SHALL return generated text from the configured LLM

#### Scenario: Fallback when LLM is unavailable
- **WHEN** the configured LLM provider is unreachable
- **THEN** the system SHALL return a fallback response with an error message

### Requirement: Support multiple LLM models
The system SHALL support configuring different LLM models via environment variables.

#### Scenario: Switch to different chat model
- **WHEN** SILICONFLOW_CHAT_MODEL is set to a different model name
- **THEN** the LLM service SHALL use the specified model

#### Scenario: Configure model parameters
- **WHEN** temperature and max_tokens are configured
- **THEN** the LLM service SHALL use these parameters for generation

### Requirement: Conversation history support
The system SHALL support passing conversation history to the LLM.

#### Scenario: Generate response with conversation context
- **WHEN** a user provides conversation history along with a new prompt
- **THEN** the LLM service SHALL generate a response considering the context

### Requirement: 可控 LLM 调用策略

系统 SHALL 支持通过环境变量配置单次 LLM 调用的超时和最大重试次数，并记录每次调用的结果和耗时。

#### Scenario: 配置单次调用预算

- **WHEN** 设置 `SILICONFLOW_LLM_TIMEOUT` 或 `SILICONFLOW_LLM_MAX_RETRIES`
- **THEN** LLM 服务 SHALL 使用配置的超时和重试次数创建聊天客户端

#### Scenario: 记录调用可观测信息

- **WHEN** LLM 服务发起、成功完成或失败完成一次调用
- **THEN** 系统 SHALL 记录模型标识、调用阶段、耗时和失败类型，且不得记录密钥内容

