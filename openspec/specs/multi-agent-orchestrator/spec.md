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

系统 SHALL 将旧版 `parcel_id`、`parcel_code` 和 `area_code` 视为过渡期兼容输入，并在 API 边界通过空间对象解析器归一化为规范 `AnalysisObject`。归一化成功后，编排器 SHALL 只向后续节点透传已验证的分析上下文；归一化失败时 SHALL 返回明确错误或对象补充状态，不得将未验证标识直接传给专业 Agent。

`parcel_id` 与 `parcel_code` 仍代表不同的历史 ID 空间，兼容适配器 SHALL NOT 猜测二者之间的转换。新客户端 SHALL 使用 `analysis_context.object`。

#### Scenario: 旧版 parcel_id 成功归一化

- **WHEN** 旧客户端提交已存在的 `parcel_id`
- **THEN** 系统 SHALL 将其解析为规范 parcel 对象并进入统一空间守卫
- **AND** 响应 SHALL 包含旧字段弃用提示

#### Scenario: 传递 parcel_id 触发 DB 真实查询

- **WHEN** 旧客户端提交可精确解析的 `parcel_id` 且问题路由到使用地块数据库的能力
- **THEN** 兼容适配器 SHALL 先把 `parcel_id` 归一化为已验证 parcel 对象
- **AND** 专业能力 SHALL 仅使用该已验证对象查询真实地块数据

#### Scenario: 传递 parcel_code 触发 fortran exe 真实计算

- **WHEN** 旧客户端提交可精确解析的 `parcel_code` 且问题路由到仍使用该历史标识的质量等级能力
- **THEN** 兼容适配器 SHALL 先验证该历史标识并形成规范 parcel 上下文
- **AND** 质量等级能力 SHALL 只使用已验证的 `parcel_code` 执行其当前正式计算实现

#### Scenario: 双 ID 并存

- **WHEN** 旧客户端同时提交 `parcel_id` 和 `parcel_code`
- **THEN** 兼容适配器 SHALL 只有在权威映射能够证明二者指向同一空间对象时才接受请求
- **AND** 在没有权威映射或映射不一致时 SHALL 返回 HTTP 422 和 `legacy_identifier_ambiguity`
- **AND** SHALL NOT 猜测两套 ID 之间的关系

#### Scenario: 旧版标识不存在

- **WHEN** 旧客户端提交不存在的 `parcel_id` 或 `parcel_code`
- **THEN** 系统 SHALL 返回对象无效或对象补充状态
- **AND** SHALL NOT 透传该标识触发 MOCK 或默认数据计算

#### Scenario: 未传地块标识符时降级

- **WHEN** 请求不含旧版 `parcel_id` 和 `parcel_code`
- **THEN** 系统 SHALL 优先使用新协议显式对象或会话已验证对象
- **AND** 若候选能力需要地块但仍无合法对象，SHALL 返回 `needs_analysis_object`
- **AND** SHALL NOT 返回 mock 数据或具体降级数值

#### Scenario: 新旧字段冲突

- **WHEN** 同一请求同时提交 `analysis_context.object` 和指向不同对象的旧版标识
- **THEN** 系统 SHALL 返回 HTTP 422 输入冲突
- **AND** SHALL NOT 修改会话对象或执行模型

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

`POST /api/v1/chat/` 和 `/stream` SHALL 在过渡期接受可选旧版 `parcel_id`、`parcel_code`、`area_code`，并优先使用新 `analysis_context` 契约。旧字段只有在精确解析成功后才能形成当前对象；未携带任何对象时系统 SHALL 根据路由后的能力要求返回知识回答、正常无对象回答或 `needs_analysis_object`，不得维持缺对象 MOCK 数值行为。

#### Scenario: 新协议设置地块

- **WHEN** 客户端通过 `analysis_context.action=set` 提交合法地块
- **THEN** API SHALL 更新会话对象并把规范上下文传给编排器

#### Scenario: API 请求携带 parcel_id

- **WHEN** 客户端 POST 聊天接口且仅携带有效旧版 `parcel_id`
- **THEN** API SHALL 通过兼容适配器归一化并验证该地块
- **AND** SHALL 把规范对象而非原始未验证标识传给编排器

#### Scenario: API 请求携带 parcel_code

- **WHEN** 客户端 POST 聊天接口且仅携带有效旧版 `parcel_code`
- **THEN** API SHALL 通过兼容适配器验证历史地块代码并形成规范上下文
- **AND** SHALL 返回旧字段弃用提示

#### Scenario: 未携带对象的地块级问题

- **WHEN** 请求和会话都无对象且问题要求地块级模型
- **THEN** API SHALL 返回 `needs_analysis_object`
- **AND** SHALL NOT 调用专业模型

#### Scenario: API 请求不携带地块标识符

- **WHEN** 客户端不携带旧版地块标识符
- **THEN** API SHALL 使用新 `analysis_context`、继承会话对象或按能力要求返回对象补充状态
- **AND** SHALL NOT 因旧字段缺失而直接触发 MOCK 计算

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

### Requirement: 专业执行统一空间对象前置守卫

编排器 SHALL 在问题类型确定后、Function Calling 和 AgentManager 任一路径之前执行 `AnalysisRequirementGuard`。任何专业执行路径 SHALL NOT 绕过该守卫。

#### Scenario: Function Calling 路径被守卫拦截

- **WHEN** LLM Function Calling 可用，但当前对象不满足候选模型要求
- **THEN** 编排器 SHALL 在调用 LLM 工具选择之前返回对象补充状态

#### Scenario: 关键词回退路径被守卫拦截

- **WHEN** Function Calling 不可用且系统准备进入关键词回退，但当前对象不满足模型要求
- **THEN** 编排器 SHALL 返回相同对象补充状态

### Requirement: 编排器共享分析上下文与追溯 ID

编排器 SHALL 为单次请求生成一个 `trace_id`，并把已验证 `analysis_context`、`conversation_id`、`user_id` 和上下文版本传入专业执行、结果封装及持久化。专业 Agent SHALL NOT 为同一次请求另建无关联的追溯 ID。

#### Scenario: 多组件追溯一致

- **WHEN** 专业模型成功执行并返回聊天响应
- **THEN** 路由日志、模型执行日志、助手消息和 API 响应 SHALL 使用相同 trace_id 和上下文版本

### Requirement: 对象不足确定性响应

对象不足提示 SHALL 由编排器确定性生成，不得调用总结 LLM。提示 SHALL 包含当前对象、所需对象类型和可执行动作，不得包含专业计算数值。

#### Scenario: 县级对象不足以执行地块模型

- **WHEN** 当前对象为 county，候选模型仅支持 parcel
- **THEN** 响应 SHALL 提示用户选择或输入地块
- **AND** SHALL 保留当前县级对象，不自动替换或清空
