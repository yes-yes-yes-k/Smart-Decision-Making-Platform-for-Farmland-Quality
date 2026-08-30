# AI 对话当前分析对象与结果溯源设计

## 1. 背景

需求文件中的问题 7 指出：AI 对话在没有明确当前地块或区域的情况下，可能直接输出土壤调理剂需求量等具体结果，用户无法判断结果针对哪个空间对象、基于哪些输入，也难以追溯数据时间和模型版本。

当前实现存在相同风险：

- `/api/v1/chat/` 只把当次请求中的 `parcel_id`、`parcel_code`、`area_code` 透传给编排器，会话本身不保存当前分析对象；
- 非流式和 SSE 流式接口各自拼装请求与响应，容易产生行为差异；
- 专业模型入口对缺失地块的处理不一致，部分路径仍可使用默认或规则降级数据输出具体数值；
- `ModelExecutionLog` 已具备输入输出快照基础，但聊天链路没有稳定传入会话、对象、模型版本和数据时间；
- 当前区域映射服务包含默认回退，不能用作空间对象存在性校验。

## 2. 目标

- 建立省、市、县、片区、地块通用的当前分析对象契约。
- 在同一会话内支持对象设置、继承、切换和清空，不跨会话自动继承。
- 在专业模型执行前统一检查当前对象是否满足模型空间尺度要求。
- 在对象缺失、无效、越权或无法验证时，禁止生产聊天链路输出地块级具体数值。
- 保留显式情景试算能力，但必须与真实空间分析清晰区分。
- 每个真实计算结果都能说明分析对象、关键输入、数据时间、模型版本、计算时间和追溯 ID。
- 为后续按省、市、县、片区、地块和模型进行统计保留可索引字段。

## 3. 非目标

- 不实现前端地图选择器和页面样式。
- 不在本次变更中导入全国完整行政区基础数据。
- 不实现统计报表页面，只保证数据结构可统计。
- 不修改专题模型算法。
- 不全面删除历史 MOCK 代码，只保证其不能绕过生产聊天前置校验。
- 不改变知识问答以及不要求空间对象的普通咨询流程。

## 4. 核心领域模型

### 4.1 AnalysisObject

`AnalysisObject` 是后端校验后生成的规范化值对象：

```json
{
  "type": "parcel",
  "id": "P001",
  "display_name": "韶关市乐昌市某地块",
  "area_code": "440281",
  "parent_path": [
    {"type": "province", "id": "440000", "display_name": "广东省", "area_code": "440000"},
    {"type": "city", "id": "440200", "display_name": "韶关市", "area_code": "440200"},
    {"type": "county", "id": "440281", "display_name": "乐昌市", "area_code": "440281"}
  ],
  "source": "one_map",
  "validated_at": "2026-08-30T18:00:00+08:00"
}
```

允许的 `type` 为 `province`、`city`、`county`、`zone`、`parcel`。客户端只提交对象类型和标识；名称、区域编码、父级路径及验证时间必须由后端权威数据生成，不能直接信任客户端展示文本。

### 4.2 CalculationMode

- `spatial`：默认模式，结果对应真实空间对象。
- `scenario`：显式情景试算，不对应任何真实空间对象，不更新会话当前对象。

## 5. 架构与职责

### 5.1 AnalysisContextService

位于聊天 API 与编排器之间，统一处理：

- 读取会话当前对象；
- 执行 `inherit`、`set`、`clear`；
- 调用空间对象解析器；
- 校验对象访问权限；
- 使用 `context_version` 做乐观并发控制；
- 在校验成功后原子更新会话上下文；
- 为用户消息生成不可变上下文快照。

### 5.2 SpatialObjectResolver

采用类型化解析器注册表：

- 地块解析器精确查询 `parcel_info`；
- 省、市、县、片区解析器精确查询 `spatial_region_catalog`；
- 所有解析器返回相同的 `AnalysisObject`；
- 查询失败、对象不存在和权限不足必须明确区分；
- 禁止使用默认区域、模拟地块或硬编码指标作为校验成功的回退。

### 5.3 AnalysisRequirementGuard

守卫位于问题类型识别之后、Function Calling 或 AgentManager 执行之前。专业能力目录增加：

- `supported_object_types`；
- `requires_spatial_object`；
- `supports_scenario`；
- `required_scenario_inputs`。

守卫只允许满足能力空间对象要求的请求进入模型执行。对象不足时返回 `needs_analysis_object`；情景试算输入不足时返回 `needs_scenario_inputs`。

### 5.4 ResultProvenanceBuilder

负责生成面向客户端的结构化溯源包络，并把相同内容写入消息和执行日志。LLM 只能润色回答正文，不能生成、修改或删除对象与溯源字段。

## 6. 数据模型

### 6.1 kb_conversation

新增：

- `analysis_object` JSON，可空；
- `context_version` 整数，默认 `0`；
- `analysis_object_updated_at` 带时区时间，可空。

会话只保存当前状态，不承担对象历史与业务统计。

### 6.2 kb_message

新增 `analysis_context_snapshot` JSON，保存消息生成时的计算模式、对象和上下文版本，确保历史消息不会因后续切换对象而改变含义。

### 6.3 spatial_region_catalog

新增轻量区域目录，覆盖省、市、县、片区：

- `object_type`、`object_id`；
- `display_name`、`area_code`；
- `parent_object_type`、`parent_object_id`；
- 可选 `layer_id`、`source`、`metadata`；
- `enabled`、`created_at`、`updated_at`。

`(object_type, object_id)` 唯一。地块继续以 `parcel_info` 为事实来源，不复制到区域目录。

### 6.4 model_execution_log

聊天链路必须正确填写现有 `user_id`、`conversation_id` 和编排器 `trace_id`，并新增：

- `analysis_object_type`；
- `analysis_object_id`；
- `area_code`；
- `context_version`；
- `analysis_context_snapshot` JSON；
- `model_version`；
- `data_as_of`（字符串，可表达调查年度或 ISO 日期）；
- `data_version`。

对对象类型、对象 ID、区域编码和执行时间建立索引。完整父级路径保存在快照中，常用统计字段保持关系型可索引。

## 7. API 契约

### 7.1 请求

```json
{
  "message": "我的田酸化严重吗？",
  "conversation_id": 12,
  "analysis_context": {
    "action": "set",
    "expected_version": 3,
    "object": {"type": "parcel", "id": "P001"}
  },
  "calculation_mode": "spatial"
}
```

`action`：

- `inherit`：继承会话对象，默认；
- `set`：校验并切换对象；
- `clear`：清空当前对象。

同一请求显式设置的新对象优先于继承对象。`scenario` 模式不修改会话对象。

### 7.2 成功响应

```json
{
  "status": "ok",
  "data": {
    "interaction_state": "completed",
    "analysis_context": {
      "mode": "spatial",
      "version": 4,
      "object": {}
    },
    "provenance": {
      "trace_id": "...",
      "model_id": "acidification-remediation",
      "model_version": "...",
      "data_as_of": "2024",
      "data_version": "...",
      "calculated_at": "...",
      "key_inputs": []
    },
    "answer": "..."
  }
}
```

### 7.3 对象不足

返回 HTTP 200 和 `interaction_state=needs_analysis_object`，包含 `required_object_types`、当前上下文和用户提示。该路径不调用 Function Calling、专业 Agent 或总结 LLM，也不产生模型执行日志。

### 7.4 错误状态

- 对象不存在、类型错误或无访问权限：HTTP 422，原会话对象不变；
- 上下文版本冲突：HTTP 409；
- 对象验证依赖不可用：HTTP 503，禁止回退到默认对象；
- 情景试算输入不足：HTTP 200，`interaction_state=needs_scenario_inputs`。

## 8. 核心流程与事务边界

1. 鉴权并读取用户所属会话。
2. 解析上下文动作和计算模式。
3. 校验对象存在性、父级路径与权限。
4. 使用 `expected_version` 原子更新会话对象。
5. 保存用户消息及上下文快照。
6. 识别问题类型和候选模型。
7. 运行模型空间对象守卫。
8. 校验通过后进入 Function Calling 或 AgentManager。
9. 生成不可变溯源包络，再由 LLM 润色正文。
10. 使用同一 `trace_id` 保存助手消息和执行日志。

会话对象更新和用户消息在模型调用前提交。模型失败不会撤销用户已经完成的对象切换。助手消息与执行日志在模型完成后写入。

## 9. 生产安全规则

- 地块级模型在无合法地块时不得执行。
- 县域统计模型可以接受县级对象，不得无条件强制地块。
- 当前只有县级对象时，地块级问题不得擅自选择县内任一地块。
- 数据库异常不得回退到默认区域、MOCK 地块或默认指标。
- MOCK 数据只能用于测试或显式演示接口，不能进入生产聊天数值回答。
- `scenario` 结果必须显示“情景试算，非具体空间对象结果”，且 `spatial_object=null`。
- 非流式与 SSE 流式聊天必须复用同一上下文服务、守卫和响应封装。

## 10. 向后兼容与迁移

- 现有会话回填 `analysis_object=null`、`context_version=0`。
- 先增加可空字段并部署兼容读取，再启用强制守卫。
- 从 `area_code_region_map` 精确导入已启用条目作为首批区域目录；不导入默认回退。
- 旧版顶层 `parcel_id`、`parcel_code`、`area_code` 在过渡期归一化为新对象并返回弃用提示。
- 旧版标识无法精确解析时返回错误或对象提示，不触发 MOCK 计算。
- `parcel_id` 与 `parcel_code` 同时提交时必须通过权威映射证明属于同一对象；缺少映射或不一致时返回歧义错误。

## 11. 统计能力

业务统计从 `parcel_info` 与专题模型结果表按区域层级聚合；运行统计从 `model_execution_log` 按对象类型、区域、模型和时间聚合。会话 JSON 只保存当前交互状态，不作为业务事实来源。

如果后续需要分析对象切换行为，可新增轻量上下文事件表，不改变本次 API 契约。

## 12. 测试与验收

测试覆盖：

- 设置、继承、切换、清空及并发版本冲突；
- 各对象类型解析、父级路径和权限校验；
- 不存在、越权、类型错误和验证服务不可用；
- 地块级问题缺对象时不调用模型、不调用 LLM、不返回数值；
- 县域统计问题允许县级对象通过；
- Function Calling 和关键词回退均不能绕过守卫；
- 情景试算成功和缺输入分支；
- 非流式与 SSE 契约一致；
- 消息与执行日志共享对象版本和 `trace_id`；
- 旧版请求兼容与非法标识拒绝。

验收时，每个具体计算结果必须能回答：针对谁、使用什么关键输入、数据何时、调用哪个模型版本、何时计算以及如何追溯。
