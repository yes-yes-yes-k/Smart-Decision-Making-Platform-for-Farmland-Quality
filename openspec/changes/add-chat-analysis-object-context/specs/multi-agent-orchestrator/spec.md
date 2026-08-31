# multi-agent-orchestrator Specification (Delta)

## MODIFIED Requirements

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

## ADDED Requirements

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
