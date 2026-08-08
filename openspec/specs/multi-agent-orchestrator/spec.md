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

系统 SHALL 支持并且只支持 6 个正式专题模型。工作流 SHALL 将耕地质量等级评价和提升潜力评估统一交由 `model-2` 执行；`model-7` SHALL NOT 被注册、调度或计入模型数量。

#### Scenario: Execute acidification assessment
- **WHEN** an acidification assessment request is submitted
- **THEN** the system SHALL execute the acidification model

#### Scenario: Execute lime demand calculation
- **WHEN** a lime demand calculation request is submitted
- **THEN** the system SHALL execute the lime calculator model

#### Scenario: Execute other assessment models
- **WHEN** requests for other models are submitted
- **THEN** the system SHALL route to the appropriate model

#### Scenario: 执行模型2真实评价
- **WHEN** 多智能体工作流收到质量等级或提升潜力问题以及有效 `parcel_code`
- **THEN** 工作流 SHALL 调用 `model-2` 返回真实 Python 计算结果
- **AND** `agents_invoked` SHALL 仅包含 `model-2` 作为该问题的专题执行者

#### Scenario: 执行其他专题模型
- **WHEN** 多智能体工作流收到稳定性、障碍诊断、酸化改良、有机质培肥或肥力预测问题
- **THEN** 工作流 SHALL 将请求路由到相应的 `model-1`、`model-3`、`model-4`、`model-5` 或 `model-6`
- **AND** SHALL NOT 注册或调用 `model-7`

### Requirement: Error Handling in Workflow
The system SHALL handle errors during workflow execution gracefully.

#### Scenario: Single model failure
- **WHEN** one model fails during execution
- **THEN** the system SHALL continue with other models and report the error

#### Scenario: Complete workflow failure
- **WHEN** all models fail
- **THEN** the system SHALL return an error status with details

### Requirement: Chat API Response Model Results Format
The system SHALL ensure that the `/api/v1/chat/` response only includes model results relevant to the caller and SHALL NOT expose internal orchestrator or AgentManager execution details inside `data.model_results`.

#### Scenario: RAG question returns no model_results
- **WHEN** a question is routed to the RAG chain (`question_type == 0`)
- **THEN** the response `data` SHALL NOT contain a `model_results` field

#### Scenario: Multi-agent question returns simplified model_results
- **WHEN** a question is routed to multi-agent models (`question_type != 0`)
- **THEN** the response `data.model_results` SHALL only contain the per-model outcome summary agreed in the API contract
- **AND** SHALL NOT contain the raw `data` or `details` fields from AgentManager

### Requirement: 地块标识符上下文透传

系统 SHALL 将请求中的 `parcel_id`、`parcel_code`、`xqmc_code`、`scenario` 和可选 `csv_path` 原样写入 Agent 上下文。`parcel_id` SHALL 继续供依赖数据库记录的专题模型使用；`parcel_code` SHALL 供 `model-2` 进行真实质量等级和单地块潜力计算；`xqmc_code` 与 `scenario` SHALL 供县域潜力情景计算使用。

#### Scenario: 传递 parcel_id 触发 DB 真实查询
- **WHEN** request 包含 `parcel_id: "1"` 且问题路由到 model-1（StabilityRiskAgent）
- **THEN** `execute_models` SHALL 将 `parcel_id` 透传到 context
- **AND** model-1 SHALL 用 `parcel_id="1"` 查询 stability_db 返回真实稳定性记录（非 mock pH=5.5）

#### Scenario: 传递 parcel_code 触发模型2真实计算
- **WHEN** 请求包含 `parcel_code: "A0001"` 且问题被路由到 `model-2`
- **THEN** 工作流 SHALL 将 `parcel_code` 传入 `model-2`
- **AND** `model-2` SHALL 返回真实 Python 质量等级或潜力计算结果，且 `simulated` 为 `false`

#### Scenario: 传递 parcel_code 触发模型2真实计算
- **WHEN** request 包含 `parcel_code: "A0001"` 且问题路由到质量等级或提升潜力能力
- **THEN** `execute_models` SHALL 将 `parcel_code` 透传到 `model-2`
- **AND** `model-2` SHALL 使用项目内纯 Python 评价引擎返回真实结果，不再要求或调用 Fortran exe

#### Scenario: 双 ID 并存
- **WHEN** request 同时包含 `parcel_id: "1"` 和 `parcel_code: "A0001"`
- **THEN** context SHALL 同时携带两个字段
- **AND** model-1/3/4 SHALL 读 `parcel_id` 查 DB，model-2 SHALL 读 `parcel_code` 进行 Python 评价，互不干扰

#### Scenario: 未传地块标识符时保留错误契约
- **WHEN** type 5 或单地块 type 6 请求未提供 `parcel_code`，或县域 type 6 请求缺少 `xqmc_code`/`scenario`
- **THEN** 工作流 SHALL 返回 `status: "error"` 和对应的机器可读错误码（`MISSING_PARCEL_CODE` 或 `MISSING_SCENARIO`）
- **AND** 结果 SHALL 明确说明缺少真实计算输入，不得伪造地块级或县域真实计算结果

### Requirement: Type 5 质量等级评价问题库
系统 SHALL 在 `REFERENCE_QUESTIONS` 字典中维护 key `5`，包含至少 3 个质量等级评价问题（如「我的田耕地质量等级是多少」「查询地块的综合指数和障碍度排序」「这块地的耕地质量等级评价结果」），使验证脚本能覆盖模型2的真实质量等级分支。

`_identify_question_type_keyword` 函数 SHALL 维护 type 5 分支，当问题命中 `QUESTION_TYPE_5_KEYWORDS`（"质量等级"、"等级评价"、"综合指数"、"指标隶属度"、"障碍度排序"、"耕地质量等级"、"质量评价"、"等级评定"、"指标权重"）时返回 `(5, relevance)`。

`TYPE_AGENTS` 映射表 SHALL 将 question_type=5 和 question_type=6 均严格映射到 `["model-2"]`（1:1 映射）。type 5/type 6 问题的路由 SHALL NOT 依赖用户角色识别（role-based 路由已移除）。

#### Scenario: 识别质量等级问题为 type 5
- **WHEN** 用户询问「我的田耕地质量等级是多少」
- **THEN** `identify_question_type` SHALL 返回 `question_type=5`

#### Scenario: type 5 问题仅路由到 model-2
- **WHEN** 问题被识别为 type 5
- **THEN** `QuestionTypeRouter.get_agents_for_type(5)` SHALL 返回 `["model-2"]`
- **AND** `AgentManager.process` SHALL 仅调用 model-2（PotentialAssessmentAgent）
- **AND** SHALL NOT 调用 model-4/5/6
- **AND** model-2 SHALL 被执行（status ≠ `skipped`），无需 `_should_execute_agent` 二次过滤

#### Scenario: 非 type 5/type 6 问题不调用 model-2
- **WHEN** 问题被识别为 type 1/2/3/4（如「我的田肥力怎么样」识别为 type 4）
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
- **THEN** 系统 SHALL 正常处理；若问题路由到模型2真实分支，响应 SHALL 保留相应输入错误码

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

