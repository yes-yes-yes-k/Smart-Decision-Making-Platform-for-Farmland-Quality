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
The system SHALL ensure that the `/api/v1/chat/` response only includes model results relevant to the caller and SHALL NOT expose internal orchestrator or AgentManager execution details inside `data.model_results`.

#### Scenario: RAG question returns no model_results
- **WHEN** a question is routed to the RAG chain (`question_type == 0`)
- **THEN** the response `data` SHALL NOT contain a `model_results` field

#### Scenario: Multi-agent question returns simplified model_results
- **WHEN** a question is routed to multi-agent models (`question_type != 0`)
- **THEN** the response `data.model_results` SHALL only contain the per-model outcome summary agreed in the API contract
- **AND** SHALL NOT contain the raw `data` or `details` fields from AgentManager

### Requirement: 地块标识符上下文透传
系统 SHALL 在 `execute_models` 节点从 `state["request"]` 提取 `parcel_id`（数字字符串，用于 stability_db/diagnosis_db 查询）和 `parcel_code`（字母数字字符串，用于 fortran exe 调用）并加入 `context`，使 AgentManager 内的 agents 能通过 `context.get("parcel_id")` 或 `context.get("parcel_code")` 获取地块标识符执行真实查询。

`parcel_id` 与 `parcel_code` 是两套无映射关系的 ID 空间：`parcel_id` 对应 stability_db/diagnosis_db 的数字 ID（如 "1"），`parcel_code` 对应 fortran exe 数据库的字母数字代码（如 "A0001"）。系统 SHALL NOT 尝试在两套 ID 之间做转换。

两个字段均为可选：未传时 agents SHALL 维持现有 mock 数据 + `need_input` 提示行为，不报错。

#### Scenario: 传递 parcel_id 触发 DB 真实查询
- **WHEN** request 包含 `parcel_id: "1"` 且问题路由到 model-1（StabilityRiskAgent）
- **THEN** `execute_models` SHALL 将 `parcel_id` 透传到 context
- **AND** model-1 SHALL 用 `parcel_id="1"` 查询 stability_db 返回真实稳定性记录（非 mock pH=5.5）

#### Scenario: 传递 parcel_code 触发 fortran exe 真实计算
- **WHEN** request 包含 `parcel_code: "A0001"` 且问题路由到 model-7（FarmlandGradeAgent）
- **THEN** `execute_models` SHALL 将 `parcel_code` 透传到 context
- **AND** model-7 SHALL 用 `parcel_code="A0001"` 调用 fortran exe 返回真实质量等级评价（非 mock）

#### Scenario: 双 ID 并存
- **WHEN** request 同时包含 `parcel_id: "1"` 和 `parcel_code: "A0001"`
- **THEN** context SHALL 同时携带两个字段
- **AND** model-1/3/4 SHALL 读 `parcel_id` 查 DB，model-7 SHALL 读 `parcel_code` 调 exe，互不干扰

#### Scenario: 未传地块标识符时降级
- **WHEN** request 不含 `parcel_id` 和 `parcel_code`
- **THEN** agents SHALL 返回 mock 数据并附加 `need_input` 提示（现有行为不变）
- **AND** SHALL NOT 抛出异常

### Requirement: Type 5 质量等级评价问题库
系统 SHALL 在 `REFERENCE_QUESTIONS` 字典中新增 key `5`，包含至少 3 个质量等级评价问题（如「我的田耕地质量等级是多少」「查询地块的综合指数和障碍度排序」「这块地的耕地质量等级评价结果」），使验证脚本能覆盖 model-7。

`_identify_question_type_keyword` 函数 SHALL 新增 type 5 分支，当问题命中 `QUESTION_TYPE_5_KEYWORDS`（"质量等级"、"等级评价"、"综合指数"、"指标隶属度"、"障碍度排序"、"耕地质量等级"、"质量评价"、"等级评定"、"指标权重"）时返回 `(5, relevance)`。

#### Scenario: 识别质量等级问题为 type 5
- **WHEN** 用户询问「我的田耕地质量等级是多少」
- **THEN** `identify_question_type` SHALL 返回 `question_type=5`

#### Scenario: type 5 问题路由到含 model-7 的 agent 组合
- **WHEN** 问题被识别为 type 5 且角色为 farmer
- **THEN** RoleRouter SHALL 路由到 `["model-4", "model-5", "model-6", "model-7"]`
- **AND** model-7 SHALL 被执行（非 skipped）

### Requirement: model-7 问题感知过滤
系统 SHALL 在 `AgentManager._should_execute_agent` 中对 model-7 增加关键词过滤：只有问题含 `QUESTION_TYPE_5_KEYWORDS` 中的任一关键词时才执行 model-7，否则跳过（status=`skipped`, reason=`question_not_related`）。

#### Scenario: 非质量等级问题跳过 model-7
- **WHEN** farmer 角色问题不含质量等级关键词（如「我的田肥力怎么样」）
- **THEN** AgentManager SHALL 跳过 model-7（status=`skipped`, reason=`question_not_related`）
- **AND** SHALL NOT 调用 fortran exe

#### Scenario: 质量等级问题执行 model-7
- **WHEN** farmer 角色问题含「质量等级」关键词
- **THEN** AgentManager SHALL 执行 model-7
- **AND** model-7 SHALL 调用 fortran exe（如 parcel_code 可用）

### Requirement: 生产 API 接受地块标识符
系统 SHALL 在 `POST /api/v1/chat/` 请求体中支持可选的 `parcel_id`（string，数字格式）和 `parcel_code`（string，字母数字格式）字段，并透传到 `multi_agent_orchestrator.run(request)`。

#### Scenario: API 请求携带 parcel_id
- **WHEN** 客户端 POST `/api/v1/chat/` 且 body 含 `parcel_id: "1"`
- **THEN** 系统 SHALL 将 `parcel_id` 透传到 orchestrator request
- **AND** orchestrator SHALL 将其加入 context 供 agents 读取

#### Scenario: API 请求携带 parcel_code
- **WHEN** 客户端 POST `/api/v1/chat/` 且 body 含 `parcel_code: "A0001"`
- **THEN** 系统 SHALL 将 `parcel_code` 透传到 orchestrator request
- **AND** orchestrator SHALL 将其加入 context 供 model-7 读取

#### Scenario: API 请求不携带地块标识符
- **WHEN** 客户端 POST `/api/v1/chat/` 且 body 不含 `parcel_id` 和 `parcel_code`
- **THEN** 系统 SHALL 正常处理（现有行为不变），agents 返回 mock + `need_input` 提示

