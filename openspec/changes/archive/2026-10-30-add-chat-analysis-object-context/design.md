# add-chat-analysis-object-context Design

## Context

聊天入口当前从请求体临时拼装编排上下文，会话表只保存标题和用户关系。专业模型对缺失地块的行为不统一，Function Calling 与关键词回退均可直接进入执行路径。酸化等路径仍保留默认输入，因此单纯要求 LLM 在回答里补写地块名称不能解决对象错误和数值来源问题。

本设计选择“会话 JSON 当前状态 + 关系型执行快照”：会话保存当前对象以支撑连续追问，执行日志保存可索引字段和完整快照以支撑追溯与统计。业务统计继续以 `parcel_info` 和专题结果表为事实来源。

## Goals / Non-Goals

**Goals:**

- 用统一空间对象契约覆盖省、市、县、片区和地块。
- 保证同一会话连续继承、不同会话相互隔离。
- 在所有专业模型执行路径之前统一校验空间对象。
- 区分真实空间分析与无空间对象的情景试算。
- 统一返回并持久化结果溯源信息。
- 为多级运行统计提供关系型索引字段。

**Non-Goals:**

- 不建设前端交互。
- 不建设完整行政区数据平台。
- 不实现统计页面。
- 不调整模型专业算法。
- 不删除所有历史 MOCK 代码。

## Decisions

### 1. 会话只保存当前规范对象 JSON

`kb_conversation.analysis_object` 保存规范化对象，`context_version` 用于并发控制。JSON 适合扩展空间对象类型，同时避免为当前状态建立多张绑定表。

不选择无状态请求方案，因为前端漏传、刷新和连续追问会重新产生对象丢失。不选择完整对象绑定历史模型，因为当前只需要当前状态，历史与统计由消息及执行快照承担。

### 2. 使用类型化解析器生成 AnalysisObject

客户端提交 `{type, id}`，后端解析器返回规范名称、区域编码、父级路径、来源和验证时间。地块精确查询 `parcel_info`；区域精确查询 `spatial_region_catalog`。权限检查属于解析成功条件。

当前区域映射服务的默认回退仅用于专业参数降级，不能作为对象存在性依据。

### 3. 新增轻量区域目录，不复制地块目录

`spatial_region_catalog` 保存省、市、县、片区及父子关系。地块数据量大且已有 `parcel_info`，因此不复制地块记录。区域目录可从已启用 `area_code_region_map` 精确导入首批数据，后续再通过独立数据任务扩展。

`data_as_of` 使用长度 32 的字符串，以同时容纳调查年度（如 `2024`）与规范 ISO 日期；`data_version` 单独记录数据集版本，避免把调查时间和发布版本混为一谈。

### 4. 模型空间要求集中在能力目录

能力目录声明 `supported_object_types`、`requires_spatial_object`、`supports_scenario` 和 `required_scenario_inputs`。`AnalysisRequirementGuard` 在路由完成后执行，避免在每个 Agent 中重复判断，也确保 Function Calling 与关键词回退遵守相同规则。

### 5. 对象不足是可恢复交互状态

空间对象不足不是服务器错误。接口返回 HTTP 200 与 `interaction_state=needs_analysis_object`，前端据此提示用户选择对象。该路径保存用户问题和助手提示，但不调用工具、专业模型或总结 LLM，也不产生模型执行日志。

显式提交的对象不存在、类型错误或越权返回 HTTP 422；上下文版本冲突返回 HTTP 409；验证依赖不可用返回 HTTP 503。

### 6. 情景试算必须显式进入 scenario 模式

`calculation_mode=scenario` 不读取或修改会话空间对象。只有能力声明支持且必需输入完整时才执行。响应固定包含 `scenario_result=true`、`spatial_object=null` 和“非具体空间对象结果”提示。

### 7. 溯源包络由后端生成

`ResultProvenanceBuilder` 从已验证上下文和实际模型执行生成对象、关键输入、数据时间、模型版本、计算时间和 `trace_id`。LLM 只获得正文润色职责，不得生成或覆盖结构化溯源字段。

### 8. 消息与执行日志保存不可变快照

`kb_message.analysis_context_snapshot` 保证历史消息语义稳定。`model_execution_log` 保存常用可索引字段与完整 JSON 快照，并复用编排器 `trace_id`，不再为每个 Agent 独立生成无关联追溯 ID。

### 9. 统计不查询会话当前 JSON

业务指标统计从 `parcel_info` 与专题结果表聚合；运行统计从 `model_execution_log` 按对象类型、区域、模型与时间聚合。会话 JSON 仅是交互状态，不是事实表。

### 10. 旧字段仅作为兼容输入

顶层 `parcel_id`、`parcel_code`、`area_code` 在过渡期由适配器解析成 `AnalysisObject`，成功后进入同一服务和守卫。无法精确解析时返回错误或对象提示，不能维持旧的 MOCK 数值行为。

由于 `parcel_id` 与 `parcel_code` 当前没有权威映射关系，同时提交二者时只有在可证明指向同一对象的情况下才允许执行；缺少映射或映射冲突时返回 `legacy_identifier_ambiguity`，不得猜测对应关系。

## Request Resolution Order

1. 鉴权并确认会话属于当前用户。
2. 读取 `calculation_mode`，默认 `spatial`。
3. `scenario` 模式忽略会话对象，但不清空会话对象。
4. `spatial` 模式处理 `analysis_context.action`：
   - `set`：解析新对象并以版本条件原子更新；
   - `clear`：以版本条件清空并递增版本；
   - `inherit` 或省略：读取当前对象。
5. 新协议缺失时尝试旧字段兼容归一化。
6. 保存用户消息与实际解析上下文快照。
7. 问题路由后执行空间要求守卫。

## Response Contract

完成状态包含：

- `interaction_state=completed`；
- `analysis_context.mode/version/object`；
- `provenance.trace_id/model_id/model_version/data_as_of/data_version/calculated_at/key_inputs`；
- 现有简化后的 `model_results`（如适用）；
- `answer`。

可恢复状态包含 `needs_analysis_object` 或 `needs_scenario_inputs`、所需类型或字段、当前上下文和确定性提示，不包含虚构结果。

## Transaction Boundaries

- 会话对象更新与用户消息在模型调用前提交。
- 新对象只有在完整验证成功后才更新；422/503 不改变原对象。
- 模型失败不撤销用户已经完成的对象切换。
- 助手消息与执行日志在模型完成后持久化，并共享同一对象版本和 `trace_id`。
- SSE 生成器必须使用显式应用上下文完成后置写入，但调用与非流式相同的服务层。

## Failure Matrix

| 情况 | HTTP | interaction_state / code | 是否调用模型 |
|---|---:|---|---|
| 当前对象满足能力要求 | 200 | completed | 是 |
| 对象尺度不足或缺失 | 200 | needs_analysis_object | 否 |
| 情景输入不足 | 200 | needs_scenario_inputs | 否 |
| 显式对象不存在/类型错误/越权 | 422 | analysis_object_invalid | 否 |
| context_version 冲突 | 409 | analysis_context_conflict | 否 |
| 对象验证依赖不可用 | 503 | analysis_object_validation_unavailable | 否 |

## Migration Plan

1. 添加可空列和 `spatial_region_catalog`，现有会话默认空对象、版本 0。
2. 导入 `area_code_region_map` 中可精确验证的启用区域。
3. 上线上下文服务与响应字段，但暂时保留旧字段兼容。
4. 为能力目录补齐空间要求并启用中央守卫。
5. 停止生产聊天路径的缺对象 MOCK 数值回退。
6. 监控 `needs_analysis_object`、422、409、503 比例和旧字段使用量。
7. 客户端迁移完成后按后续 change 移除旧字段。

## Risks / Trade-offs

- [区域目录初期不完整] → 只允许精确登记对象；未登记对象返回明确错误，不使用默认回退。
- [JSON 字段查询能力有限] → 常用统计字段同时写入执行日志关系型列。
- [旧客户端行为变化] → 保留旧字段解析，但不保留不安全的 MOCK 数值语义。
- [并发切换导致 409] → 返回最新版本和对象，客户端刷新后重试。
- [模型数据时间定义不一致] → 使用 `data_as_of` 与 `data_version` 双字段，模型适配器负责提供实际值。

## Open Questions

无。完整行政区目录导入、前端对象选择器和统计页面分别作为后续 change。
