## MODIFIED Requirements

### Requirement: Chat API Response Model Results Format

系统 SHALL 确保 `/api/v1/chat/` 和 `/api/v1/chat/stream` 只返回调用方所需的公共聊天数据，禁止暴露 Orchestrator 或 AgentManager 的内部 `data/details`、完整分析包、执行上下文或审计字段。公共响应必须包含 `schema_version`、`trace_id` 和 `status`；其 `data` 必须包含 `message_id`、`answer`、`sources`、`recommendations` 和 `routing`。

#### Scenario: RAG question returns no model_results
- **WHEN** 问题被路由到 RAG 链路（`question_type == 0`）
- **THEN** 响应 `data` 必须省略 `models`
- **AND** 禁止返回空的 `model_results` 或 AgentManager 内部结构作为占位

#### Scenario: 模型问题默认不返回模型详情
- **WHEN** 问题被路由到专业模型且请求未设置 `include_model_results=true`
- **THEN** 响应 `data` 必须返回最终 `answer` 和路由元数据
- **AND** 响应 `data` 必须省略 `models`

#### Scenario: Multi-agent question returns simplified model_results
- **WHEN** 问题被路由到专业模型且请求设置 `include_model_results=true`
- **THEN** 响应 `data.models` 必须以 Agent ID 或规范模型 ID 为键返回每模型 `chat_compact` 投影
- **AND** `models` 禁止包含 AgentManager 的原始 `data` 或 `details`
- **AND** 响应禁止再返回可由 `models` 键推导的 `agents_invoked`

#### Scenario: 聊天路由字段归一化
- **WHEN** 聊天请求处理完成
- **THEN** `data.routing.question_type` 必须表示最终问题类型
- **AND** `data.routing.status` 必须表示最终路由状态
- **AND** 响应禁止在 `data` 中同时返回重复的 `question_type` 和 `routing_status`

#### Scenario: 流式与非流式完成结构一致
- **WHEN** 相同请求分别通过非流式聊天和流式聊天执行完成
- **THEN** 流式 `done.data` 与非流式响应 `data` 必须遵循同一字段结构
- **AND** 两者对 `models` 的省略或包含规则必须一致

## ADDED Requirements

### Requirement: LLM 使用紧凑模型上下文

系统必须只将模型结果的 `llm_context` 投影传给最终 LLM，总结上下文禁止包含 AgentManager 的原始 `data/details`、完整九模块数据、能力目录描述、审计字段或重复的模型自然语言回答。

#### Scenario: 专业结果进入最终总结
- **WHEN** 专业模型生成规范结果且最终 LLM 可用
- **THEN** 编排器必须从规范结果生成 `llm_context` 投影
- **AND** 最终 LLM prompt 必须只包含用户问题和该紧凑投影

#### Scenario: LLM 总结失败
- **WHEN** 最终 LLM 调用超时、失败或返回空内容
- **THEN** 系统必须直接根据规范模型结果生成确定性自然语言答复
- **AND** 系统禁止为了生成降级答复重新执行专业模型
