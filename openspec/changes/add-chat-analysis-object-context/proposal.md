# add-chat-analysis-object-context Proposal

## Why

当前聊天接口只透传单次请求中的 `parcel_id`、`parcel_code` 和 `area_code`，会话没有稳定的“当前分析对象”。当对象缺失或地块查询失败时，部分专业模型路径仍可能使用默认或规则降级输入输出具体数值，用户无法判断结果对应哪个地块、使用了哪些数据，也无法可靠追溯模型版本和计算时间。

问题 7 要求 AI 对话能够继承并展示当前区域或地块，在缺少必要对象时停止地块级计算，并为结果提供对象、关键输入、数据时间和模型信息。本 change 在现有聊天、编排和专题模型能力之上补齐这一安全边界。

## What Changes

- 新增省、市、县、片区、地块通用的规范化 `AnalysisObject` 契约。
- 在会话中保存当前分析对象与版本，支持设置、继承、切换、清空和乐观并发控制。
- 新增类型化空间对象解析器；地块精确查询 `parcel_info`，区域精确查询区域目录，禁止默认对象回退。
- 在问题路由之后、Function Calling 或 AgentManager 之前增加统一空间尺度守卫。
- 对象不足时返回机器可读的 `needs_analysis_object`，不调用模型、工具或总结 LLM。
- 保留显式 `scenario` 情景试算，但要求完整输入并标明不对应真实空间对象。
- 统一非流式与 SSE 的上下文解析、守卫和响应封装。
- 在响应、消息和执行日志中保存分析对象、关键输入、数据时间、模型版本、计算时间和 `trace_id`。
- 为后续省、市、县、片区、地块及模型调用统计增加关系型索引字段。
- 过渡期兼容旧版顶层 `parcel_id`、`parcel_code`、`area_code`，但非法标识不再触发 MOCK 计算。
- 同时提交无权威映射的 `parcel_id` 与 `parcel_code` 时返回歧义错误，避免两套 ID 实际指向不同地块。

## Capabilities

### New Capabilities

- `analysis-object-context`: 规范化空间分析对象、会话上下文生命周期、模型空间尺度守卫、情景试算与结果溯源。

### Modified Capabilities

- `database-models`: 会话保存当前对象与版本，消息保存不可变上下文快照。
- `thematic-model-orm`: 新增区域目录以及执行日志的对象、版本、数据时间和模型版本字段。
- `multi-agent-orchestrator`: 在所有专业执行路径前统一拦截对象不足请求，并归一化旧版标识。
- `professional-model-agents`: 生产聊天路径禁止在缺少合法对象时使用默认或模拟输入生成具体数值。
- `function-calling-system`: 工具调用必须在上下文守卫之后执行，不能自行补造空间对象。
- `api-documentation-examples`: 更新聊天请求、响应、错误和兼容字段示例。

## Impact

- 数据库：`kb_conversation`、`kb_message`、`model_execution_log` 增加字段；新增 `spatial_region_catalog`。
- API：`POST /api/v1/chat/` 与 `/stream` 增加 `analysis_context`、`calculation_mode`、`interaction_state`、`provenance`。
- 编排：新增上下文解析与模型前置守卫节点或等价服务。
- 专业模型：生产聊天入口统一执行对象前置条件，不再以 MOCK 数值满足缺对象请求。
- 兼容性：旧字段在过渡期继续接受并返回弃用提示；新客户端应改用 `analysis_context`。
- 运维：需要执行可空字段迁移并导入首批区域目录。

## Non-Goals

- 不实现前端地图对象选择器。
- 不导入完整全国行政区数据。
- 不实现统计报表页面。
- 不修改专题模型算法。
