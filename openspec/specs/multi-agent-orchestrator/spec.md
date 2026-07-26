# multi-agent-orchestrator Specification

## Purpose
TBD - created by archiving change migrate-and-unify-framework. Update Purpose after archive.
## Requirements
### Requirement: Multi-Agent Orchestration
The system SHALL provide a multi-agent orchestrator that supports concurrent execution of up to six professional models.

#### Scenario: Execute multiple models concurrently
- **WHEN** a request is submitted that requires multiple models
- **THEN** the system SHALL execute the models concurrently

#### Scenario: Coordinate model execution order
- **WHEN** models have dependencies on each other
- **THEN** the system SHALL execute them in the correct order

#### Scenario: Aggregate results from concurrent models
- **WHEN** all concurrent models complete
- **THEN** the system SHALL aggregate and return combined results

### Requirement: LangGraph Integration
The system SHALL use LangGraph as the workflow orchestration engine.

#### Scenario: Build state machine workflow
- **WHEN** a workflow is defined with nodes and edges
- **THEN** LangGraph SHALL compile and execute the workflow

#### Scenario: Conditional routing
- **WHEN** a node returns a conditional output
- **THEN** the system SHALL route to the appropriate next node

#### Scenario: Async node execution
- **WHEN** nodes are marked as async
- **THEN** they SHALL execute concurrently

### Requirement: Six Professional Models Support
The system SHALL support six professional models for cultivated land assessment.

#### Scenario: Execute acidification assessment
- **WHEN** an acidification assessment request is submitted
- **THEN** the system SHALL execute the acidification model

#### Scenario: Execute lime demand calculation
- **WHEN** a lime demand calculation request is submitted
- **THEN** the system SHALL execute the lime calculator model

#### Scenario: Execute other assessment models
- **WHEN** requests for other models are submitted
- **THEN** the system SHALL route to the appropriate model

### Requirement: Error Handling in Workflow
The system SHALL handle errors during workflow execution gracefully.

#### Scenario: Single model failure
- **WHEN** one model fails during execution
- **THEN** the system SHALL continue with other models and report the error

#### Scenario: Complete workflow failure
- **WHEN** all models fail
- **THEN** the system SHALL return an error status with details

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

