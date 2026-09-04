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
- **THEN** the system SHALL aggregate their outputs into a caller-facing format
- **AND** SHALL NOT forward raw agent metadata such as `details`, `confidence`, or internal `evidence` arrays as part of the public chat response

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

### Requirement: 地块标识符上下文透传
系统 SHALL 在 `execute_models` 节点从 `state["request"]` 提取 `parcel_id`（数字字符串，用于 stability_db/diagnosis_db 查询）和 `parcel_code`（字母数字字符串，用于 fortran exe 调用）并加入 `context`，使 AgentManager 内的 agents 能通过 `context.get("parcel_id")` 或 `context.get("parcel_code")` 获取地块标识符执行真实查询。

`parcel_id` 与 `parcel_code` 是两套无映射关系的 ID 空间：`parcel_id` 对应 stability_db/diagnosis_db 的数字 ID（如 "1"），`parcel_code` 对应 fortran exe 数据库的字母数字代码（如 "A0001"）。系统 SHALL NOT 尝试在两套 ID 之间做转换。

两个字段均为可选：未传时 agents SHALL 维持现有 mock 数据 + `need_input` 提示行为，不报错。

#### Scenario: 传递 parcel_id 触发 DB 真实查询
- **WHEN** request 包含 `parcel_id: "1"` 且问题路由到 model-1（StabilityRiskAgent）
- **THEN** `execute_models` SHALL 将 `parcel_id` 透传到 context
- **AND** model-1 SHALL 用 `parcel_id="1"` 查询 stability_db 返回真实稳定性记录（非 mock pH=5.5）

#### Scenario: 传递 parcel_code 触发 fortran exe 真实计算
- **WHEN** request 包含 `parcel_code: "A0001"` 且问题路由到 model-2（FarmlandGradeAgent）
- **THEN** `execute_models` SHALL 将 `parcel_code` 透传到 context
- **AND** model-2 SHALL 用 `parcel_code="A0001"` 调用 fortran exe 返回真实质量等级评价（非 mock）

#### Scenario: 双 ID 并存
- **WHEN** request 同时包含 `parcel_id: "1"` 和 `parcel_code: "A0001"`
- **THEN** context SHALL 同时携带两个字段
- **AND** model-1/3/5 SHALL 读 `parcel_id` 查 DB，model-2 SHALL 读 `parcel_code` 调 exe，互不干扰

#### Scenario: 未传地块标识符时降级
- **WHEN** request 不含 `parcel_id` 和 `parcel_code`
- **THEN** agents SHALL 返回 mock 数据并附加 `need_input` 提示（现有行为不变）
- **AND** SHALL NOT 抛出异常

### Requirement: Type 2 质量等级评价问题库
系统 SHALL 在 `REFERENCE_QUESTIONS` 字典中维护 key `2`，包含至少 3 个质量等级评价问题（如「我的田耕地质量等级是多少」「查询地块的综合指数和障碍度排序」「这块地的耕地质量等级评价结果」），使验证脚本能覆盖 model-2。

`_identify_question_type_keyword` 函数 SHALL 维护 type 2 分支，当问题命中 `QUESTION_TYPE_2_KEYWORDS`（"质量等级"、"等级评价"、"综合指数"、"指标隶属度"、"障碍度排序"、"耕地质量等级"、"质量评价"、"等级评定"、"指标权重"）时返回 `(2, relevance)`。

`TYPE_AGENTS` 映射表 SHALL 将 question_type=2 严格映射到 `["model-2"]`（1:1 映射），SHALL NOT 包含 model-1/3/4/5。type 2 问题的路由 SHALL NOT 依赖用户角色识别（role-based 路由已移除）。

#### Scenario: 识别质量等级问题为 type 2
- **WHEN** 用户询问「我的田耕地质量等级是多少」
- **THEN** `identify_question_type` SHALL 返回 `question_type=2`

#### Scenario: type 2 问题仅路由到 model-2
- **WHEN** 问题被识别为 type 2
- **THEN** `QuestionTypeRouter.get_agents_for_type(2)` SHALL 返回 `["model-2"]`
- **AND** `AgentManager.process` SHALL 仅调用 model-2（FarmlandGradeAgent）
- **AND** SHALL NOT 调用 model-1/3/4/5
- **AND** model-2 SHALL 被执行（status ≠ `skipped`），无需 `_should_execute_agent` 二次过滤

#### Scenario: 非 type 2 问题不调用 model-2
- **WHEN** 问题被识别为 type 1/3/4/5（如「我的田稳定性怎么样」识别为 type 1）
- **THEN** `AgentManager.process` SHALL NOT 调用 model-2
- **AND** SHALL NOT 在 `details` 中出现 model-2 的 `skipped` 条目（因路由未包含 model-2）

### Requirement: 生产 API 接受地块标识符
系统 SHALL 在 `POST /api/v1/chat/` 请求体中支持可选的 `parcel_id`（string，数字格式）和 `parcel_code`（string，字母数字格式）字段，并透传到 `multi_agent_orchestrator.run(request)`。

#### Scenario: API 请求携带 parcel_id
- **WHEN** 客户端 POST `/api/v1/chat/` 且 body 含 `parcel_id: "1"`
- **THEN** 系统 SHALL 将 `parcel_id` 透传到 orchestrator request
- **AND** orchestrator SHALL 将其加入 context 供 agents 读取

#### Scenario: API 请求携带 parcel_code
- **WHEN** 客户端 POST `/api/v1/chat/` 且 body 含 `parcel_code: "A0001"`
- **THEN** 系统 SHALL 将 `parcel_code` 透传到 orchestrator request
- **AND** orchestrator SHALL 将其加入 context 供 model-2 读取

#### Scenario: API 请求不携带地块标识符
- **WHEN** 客户端 POST `/api/v1/chat/` 且 body 不含 `parcel_id` 和 `parcel_code`
- **THEN** 系统 SHALL 正常处理（现有行为不变），agents 返回 mock + `need_input` 提示

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

