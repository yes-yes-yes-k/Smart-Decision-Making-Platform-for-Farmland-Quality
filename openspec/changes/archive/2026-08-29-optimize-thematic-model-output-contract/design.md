## 上下文

本设计以 `09db7a637d49f8fcca502428dff8772a1111ea35` 为基线。当前专业模型链路包含四种不同职责的数据：模型 `execute()` 的原始计算结果、`analyze()` 的展示型分析包、`answer_from_analysis()` 的聊天答复，以及 AgentManager/Orchestrator 的执行详情。默认适配器把原始结果同时写入 `analysis` 与 `evidence`，再逐字段生成 `findings`；聊天链路将完整分析包嵌入模型详情，并把完整 `model_results` 交给 LLM 和 HTTP 调用方。

基线还已经引入了两条模型执行路径：Function Calling 路径由 LLM 选择专题工具并生成答复，关键词回退路径由 AgentManager 执行后再由 Orchestrator 汇总。两条路径目前都可能把结果包装为 `data/details`，Function Calling 还会在成功时写入 `routing_method=function_calling`，关键词路径写入 `routing_method=keyword_fallback`。这些是需要被统一输出契约收敛的既有入口，不是本变更要重新实现的架构。

现有实现的初衷是让不同模型共用 API、CLI 和聊天编排入口，但统一的是展示字段名称而非业务语义。同一模型的 DB、CSV、SQLite、预计算和 ML 路径仍返回不同形状，状态也分散在 `status`、`degraded`、`simulated`、`fallback`、`reliability`、`reason` 等字段中。`09db7a6` 的聊天接口仍暴露 AgentManager 的原始 `data/details`，并且专题模型接口仍同时返回 `model`、`capability` 和 Model-5 提升字段，与本变更要求的公共契约不一致。

本变更涉及 Agent 基类、六个专业 Agent、专题模型 API、聊天编排、LLM 上下文、流式响应和持久化快照，需要通过一个规范化边界避免各层继续独立适配。

现有数据流应按以下方式迁移，保留两条执行路径但只允许一个结构化事实来源：

```text
Function Calling ─┐
                  ├─ 规范模型结果信封 ─┬─ public_full
关键词回退 ───────┘                    ├─ chat_compact
                                       ├─ llm_context
                                       └─ audit
```

## 目标 / 非目标

**目标：**

- 为六个正式专题模型建立一份稳定、可版本化、可验证的公共结果信封。
- 同一模型的所有数据路径输出同一业务 Schema，不同模型保留各自业务字段。
- 让结构化业务结果只有一个事实来源，公共 API、聊天、LLM 和审计通过显式投影消费它。
- 统一成功、部分可用、输入拒绝、能力不可用和执行失败的状态及问题表达。
- 显著减少响应体积和 LLM 上下文，消除递归嵌套及语义重复。
- 提供可回滚的兼容迁移路径，并保证非流式与流式聊天完成事件一致。

**非目标：**

- 不改变六个模型的计算公式、训练模型、输入特征或数据库表结构。
- 不在本变更中实现 Model-6 的综合地力业务逻辑。
- 不强制六个模型使用相同的 `result` 业务字段。
- 不把 trace、执行日志或模型中间变量设计成公共 API。
- 不依赖 LLM 将自然语言重新解析成结构化模型结果。

## 决策

### 决策一：`analyze()` 返回规范模型结果信封

规范结果固定为：

```json
{
  "model_id": "stability-risk-evaluation",
  "status": "ok",
  "subject": {"type": "parcel", "id": "2241"},
  "result": {},
  "meta": {
    "data_source": "precomputed",
    "simulated": false,
    "model_version": null
  },
  "issues": []
}
```

`model_id`、`status`、`subject`、`result`、`meta` 和 `issues` 始终存在。`subject.type` 至少支持 `parcel`、`area` 和 `unknown`；无法确定 ID 时 `subject.id` 为 `null`。`result` 在 `ok` 时为对象，在 `degraded` 时可为部分结果对象，在 `rejected`、`unavailable` 和 `error` 时为 `null`。

选择这一结构是为了把身份、结果可用性、评价对象、业务数据、运行元数据和异常分别归属到唯一字段。未选择继续扩展旧包络，因为 `summary/findings/evidence` 是展示概念，无法为六个模型提供稳定的机器语义。

### 决策二：状态与问题使用正交字段表达

模型状态仅允许：

- `ok`：结果完整可用；
- `degraded`：结果可用但不完整、使用了替代路径或默认值；
- `rejected`：输入冲突、越界或不满足业务约束，未执行计算；
- `unavailable`：能力、数据或运行依赖尚不可用；
- `error`：已尝试执行但发生非预期失败。

`issues` 元素固定包含 `code`、`severity` 和 `message`，可选包含 `field` 与不含敏感信息的 `details`。`ok` 通常对应空数组；其他状态必须至少有一条能解释该状态的问题。`meta` 只描述运行事实，首版固定包含 `data_source`、`simulated` 和可空 `model_version`。

未选择保留多个布尔值，是因为 `degraded=true`、`fallback.used=true` 与 `reliability.level` 可能互相矛盾。未选择只返回自然语言错误，是因为客户端需要稳定错误码。

### 决策三：按 `model_id` 判别业务结果

公共信封统一，`result` 按规范模型 ID 判别：

- Model-1：`region`、`score`、`grade`、`modules`；九模块仅保留在 `modules`，删除 `all_results`。
- Model-2：`quality_grade`、`composite_index`、`indicators`、`obstacle_degree`。
- Model-3：`obstacle_type`、`primary_factors`、`secondary_factors`、`obstacle_degrees`、`obstacle_levels`、`obstacle_combination`。
- Model-4：`acidification_level`、`background_acid`、`acid_deposition_input`、`crop_acid_output`、`nitrogen_cycle_acid`、`agricultural_acid`、`soil_conditioner_dosage`、`woody_peat_dosage`、`sub_model`。
- Model-5：`soc_prediction`、`dose_prediction`、`soc_confidence`、`dose_confidence`、`region`、`land_type`、`imputed_features`。
- Model-6：未实现期间 `result=null`、`status=unavailable`，并返回 `MODEL_NOT_IMPLEMENTED`。

各 Agent 负责把本模型的不同来源适配到规范字段，来源差异只进入 `meta.data_source`。不使用无业务含义的通用 `confidence`；Model-5 的两个预测置信度属于业务结果，继续保留。

### 决策四：引入四种显式投影，禁止隐式复制

规范模型结果是唯一事实来源，消费者通过纯转换函数获得：

1. `public_full`：专题模型 API 的完整规范结果；
2. `chat_compact`：聊天可选返回的关键指标，不含大体积模块、中间值或内部错误堆栈；
3. `llm_context`：最终总结所需的模型名称、状态、关键结果、问题和建议；
4. `audit`：完整输入、规范输出和内部诊断，仅写入执行日志或 trace。

投影函数不得重新执行模型，不得把规范结果完整复制到多个同级字段，也不得通过字符串化整个对象生成 `findings`。

未选择让调用方自行裁剪，因为那仍会让完整内部对象跨越 API 与 LLM 边界。未选择 JSON 引用，因为普通 HTTP JSON 响应没有跨字段对象引用语义。

### 决策四补充：统一 Function Calling 和关键词回退

Function Calling 和关键词回退均必须在 Agent 执行完成后转换为规范模型结果。Function Calling 返回的自然语言 `content` 只能作为答复候选或内部执行信息，不能反向解析成 `result`，也不能与规范结果并列作为第二个事实来源。Function Calling 已成功生成非空答复时，Orchestrator 直接使用该答复；关键词回退才调用最终 LLM，且只传 `llm_context` 投影。

当 Function Calling 不可用、LLM 不返回工具调用或工具执行失败时，继续使用基线已有的关键词回退行为，但回退结果必须经过与 Function Calling 相同的状态、元数据和问题映射。

### 决策五：专题模型 API 与聊天 API 使用不同数据载荷

HTTP 层继续使用项目现有的 `status/data` 传输包络以控制迁移范围，并新增顶层 `schema_version` 与 `trace_id`。外层 `status` 表示 HTTP 请求处理结果，`data.status` 表示模型业务结果。

`POST /api/v1/models/run` 的 `data` 为一个 `public_full` 模型结果。

聊天响应的 `data` 固定包含 `message_id`、`answer`、`sources`、`recommendations` 和 `routing`。`routing` 包含 `question_type` 与 `status`。默认不返回模型详情；请求显式设置 `include_model_results=true` 时，额外返回 `models` 映射，其值为 `chat_compact` 投影。`models` 的键已经表达被调用模型，因此不再公开重复的 `agents_invoked`。

RAG 路径始终省略 `models`。流式接口的 `done.data` 与非流式聊天的 `data` 使用同一序列化函数；token 和 meta 事件维持流式职责。

### 决策六：LLM 只接收紧凑上下文

最终 LLM 总结只接收用户问题和 `llm_context` 投影，不接收 AgentManager 的 `data/details`、完整九模块结果、能力目录描述、审计信息或重复自然语言答案。LLM 不负责决定模型状态，也不负责补齐结构化字段；LLM 失败时由确定性模板根据规范结果生成回答。

### 决策七：所有输出必须满足严格 JSON

公共响应在序列化前递归校验非有限浮点值。`NaN`、正无穷和负无穷必须转换为 `null`，并在影响结果解释时添加 `NON_FINITE_VALUE` warning。JSON 序列化使用禁止输出非标准数值的严格模式，测试必须对响应执行标准 JSON 解析。

### 决策八：通过 Schema 版本和兼容窗口迁移

`schema_version` 使用字符串版本 `2.0`。兼容期内，调用方可通过请求字段 `response_schema="1.0"` 获取旧结构；未指定时的新默认值为 `2.0`。旧序列化器只能从规范结果单向生成，不允许旧对象继续作为内部事实来源。

旧结构返回时增加弃用信息，记录旧模式调用量。前端和外部调用方迁移完成后删除 `1.0` 序列化器。模型目录接口不再在每次执行结果中重复返回能力描述，调用方需要名称、用途或运行前提时使用模型目录。

## 风险 / 权衡

- [旧前端或脚本依赖 `analysis/evidence/findings` 和 `model_results.data.details`] → 提供 `response_schema="1.0"` 兼容窗口、弃用提示和迁移示例，并用调用日志确认下线时机。
- [各模型历史路径字段不完整，无法一次映射全部规范字段] → 允许 `degraded` 返回部分 `result`，缺失字段使用 `null` 并通过 `issues` 解释，禁止伪造默认业务值。
- [聊天精简投影遗漏前端需要的指标] → 每个模型定义稳定的聊天关键字段清单，并为显式详情需求保留专题模型 API。
- [两套序列化器在兼容期增加维护成本] → 规范结果只维护一套，旧版仅作为有删除期限的纯投影层。
- [状态归一化改变监控统计口径] → 在迁移期同时记录旧状态与规范状态映射，更新告警和仪表盘后再移除旧口径。
- [严格 JSON 清洗可能掩盖上游数值问题] → 同时生成 `NON_FINITE_VALUE` issue 并记录内部日志，公共接口不暴露非法 JSON。

## 迁移计划

1. 建立规范结果类型、状态/问题校验器、严格 JSON 清洗器和四种投影函数，先补齐契约测试。
2. 逐个迁移 Model-1 至 Model-6 的 `analyze()` 适配，确保每个数据来源映射到同一模型 Schema，并将 Model-6 桩响应改为 `unavailable`。
3. 将 Function Calling 的 `tool_result` 和关键词回退的 AgentManager 结果都转换为规范结果，不改变已有的工具调用和回退触发条件。
4. 让专题模型 API 默认返回 Schema 2.0，同时提供从规范结果生成的 1.0 兼容投影。
5. 改造 AgentManager、Orchestrator 和 LLM prompt，只在内部传递规范结果或紧凑投影；Function Calling 成功答复不重复总结。
6. 改造聊天非流式与流式响应；默认省略模型详情，显式请求时返回 `models` 精简投影。
7. 更新前端、API 文档、示例和监控，观察旧模式调用量后移除 1.0 兼容层。

回滚时保留规范结果内部实现，临时将 `response_schema` 默认值切回 `1.0`；由于旧响应由规范结果单向投影生成，不需要回滚模型计算逻辑或数据库数据。

## 开放问题

- 兼容窗口按一个发布周期还是按固定日期结束，需要结合现有前端和外部调用方清单在实施前确认；这不影响 Schema 2.0 的结构和实现顺序。
