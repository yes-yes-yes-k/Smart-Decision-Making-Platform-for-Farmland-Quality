## ADDED Requirements

### Requirement: 多智能体统一 LLM 总结

系统 SHALL 在专业智能体完成后最多调用一次 LLM，以整合专业结果为最终自然语言答复。

#### Scenario: 专业结果完成后的统一总结

- **WHEN** 多智能体路线中的专业智能体已生成结构化结果且 LLM 服务可用
- **THEN** 编排器 SHALL 仅发起一次最终 LLM 调用，并将问题与专业智能体结果作为总结上下文

#### Scenario: 专业智能体不重复调用 LLM

- **WHEN** 多智能体路线执行单个或多个专业智能体
- **THEN** 专业智能体 SHALL 默认使用领域规则和计算结果，且不得各自发起 RAG 或 LLM 生成调用

### Requirement: LLM 总结失败时保留专业结果

系统 SHALL 将专业智能体汇总作为 LLM 总结的降级结果。

#### Scenario: LLM 总结超时或失败

- **WHEN** 最终 LLM 调用返回失败、超时或无有效内容
- **THEN** 编排器 SHALL 返回专业智能体的 `summary`，并不得以空文本或失败文本覆盖该结果
