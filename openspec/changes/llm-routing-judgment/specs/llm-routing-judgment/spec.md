## ADDED Requirements

### Requirement: LLM 路由判定

系统 SHALL 在 `ROUTING_MODE=llm` 且 LLM 服务可用时，先调用 LLM 对用户问题进行类型初判，返回结构化 JSON（`question_type` + `reason`），再叠加排他规则兜底。LLM 判定优先级高于关键词/向量判定。

#### Scenario: LLM 可用时全量初判
- **WHEN** `ROUTING_MODE=llm` 且 LLM 服务可用
- **THEN** 系统 SHALL 调用 LLM 对问题判定 `question_type`（0..6）与 `reason`
- **AND** 判定结果 SHALL 传递给排他规则进行最终兜底

#### Scenario: LLM 判定后叠加排他规则
- **WHEN** LLM 返回 `question_type` 命中易混淆对（model-3/2、model-4/5）
- **THEN** 系统 SHALL 将 LLM 结果传入 `apply_exclusive_rules`
- **AND** 排他规则消解结果 SHALL 作为最终路由类型

### Requirement: ROUTING_MODE 配置开关

系统 SHALL 提供 `ROUTING_MODE` 配置，取值 `llm` 或 `keyword`，默认 `llm`。`keyword` 模式 SHALL 保持现有纯关键词/向量/排他规则路由行为不变。

#### Scenario: 默认启用 LLM 判定
- **WHEN** 未显式配置 `ROUTING_MODE`
- **THEN** 系统 SHALL 采用 `llm` 模式

#### Scenario: 切换回纯关键词模式
- **WHEN** `ROUTING_MODE=keyword`
- **THEN** 系统 SHALL 走纯关键词/向量/排他规则路由，不调用 LLM 判定

### Requirement: LLM 判定失败回退

系统 SHALL 在 LLM 不可用、JSON 解析失败或返回非法 `question_type` 时，自动回退到关键词/向量判定，路由不中断，且 SHALL NOT 向主流程抛出异常。

#### Scenario: LLM 服务不可用
- **WHEN** LLM 服务不可用（`is_available()=False`）
- **THEN** 系统 SHALL 回退关键词/向量判定
- **AND** 路由正常完成，无异常

#### Scenario: LLM 返回非法 JSON 或越界类型
- **WHEN** LLM 返回的 JSON 解析失败或 `question_type` 不在 0..6 范围内
- **THEN** 系统 SHALL 回退关键词/向量判定
- **AND** 记录失败原因到观测日志

### Requirement: 观测日志记录 LLM 判定

系统 SHALL 在路由观测日志中记录 `router_method`（`llm`/`keyword`）、`llm_reason`、`llm_duration_ms`，以支持 LLM 路由与关键词路由的对比分析与对账。

#### Scenario: 记录 LLM 判定详情
- **WHEN** 一次路由判定由 LLM 完成
- **THEN** 观测日志 SHALL 记录 `router_method=llm`、`llm_reason`、`llm_duration_ms`
- **AND** 日志 SHALL 保持与远端 trace 共享同一 `trace_id`

#### Scenario: 记录关键词回退
- **WHEN** 一次路由判定因 LLM 不可用或解析失败回退到关键词
- **THEN** 观测日志 SHALL 记录 `router_method=keyword`
- **AND** 记录 `llm_failure_reason`（如有）