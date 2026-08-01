# 设计：以专业 Agent 为单一能力来源

## 决策

建立一个集中式专业能力注册表，作为正式模型 API、`AgentManager`、`QuestionTypeRouter`、问题分类关键词和接口文档的唯一来源。每个注册项对应恰好一个专业 Agent；对外保留语义化 `model_id`，内部保留稳定的 `agent_id`。

注册项至少包含：

- `agent_id`、公开 `model_id`、中文名称与能力边界；
- `question_type`、关键词与典型问题；
- 最小输入、地块标识要求和运行前提；
- 数据来源、可靠性等级和可用的降级策略；
- Agent 类或工厂，以及旧模型 ID 的兼容别名。

## 调用结构

```text
能力注册表
  ├─ AgentManager：按 agent_id 注册 Agent
  ├─ QuestionTypeRouter：按 question_type 查找单一 agent_id
  ├─ 专题模型 API：按公开 model_id 查找能力并调用结构化分析
  └─ OpenAPI/文档：生成或校验公开模型清单和示例

专业 Agent.analyze(payload)
  ├─ 单模型 API：直接返回统一结构化分析结果
  └─ 聊天链路：复用分析结果生成专业答复，再交给一次最终 LLM 汇总
```

## 结构化分析契约

`BaseAgent` 新增 `analyze(payload)`。它是专业计算的唯一入口，返回统一包络，至少包含：

- `status`、`capability`、`summary`、`findings`、`recommendations`；
- `evidence`、`lineage`、`reliability`、`fallback`；
- 成功、未就绪、输入不足、拒绝与降级状态的机器可读错误信息。

`answer_question()` 不再各自构造另一套计算结果；它将问题和上下文转换为 payload，调用 `analyze()`，再负责中文问答表达。专题模型 API 也调用 `analyze()`，只负责 HTTP/接口包装。这避免 API 与聊天链路分别执行不同规则或返回不同可靠性说明。

## 能力分类

正式专业能力仅包含上述 7 项。以下能力保留为非正式专业能力，但不参与 Agent 注册或 `question_type` 路由：

| 模型 ID | 分类 | 定位 |
|---|---|---|
| `spatial-structure-analysis` | 辅助能力 | 空间数据展示和分区支撑 |
| `soil-indicator-analysis` | 辅助能力 | 基础指标分析和上游输入支撑 |
| `multi-factor-collaborative-improvement` | 实验性能力 | 未具备对应综合 Agent 前的 Demo/研究能力 |

分类字段必须对外可见。正式专业模型清单默认只返回正式能力；调用方请求全量能力时才能获得辅助和实验性能力及其不可路由状态。

## 路由与降级

`question_type=0` 继续专用于 RAG。`question_type=1..7` 均一对一对应正式 Agent。关键词重叠时：

- “有机肥、秸秆还田、培肥方案、提升有机质措施”优先路由 `model-5`；
- “SOC、有机碳预测、Dose、施肥量预测、置信度”优先路由 `model-6`。

当 AgentManager 或某 Agent 执行失败时，系统不得回退到隐式的旧多模型组合。它应返回已经生成的同能力结果；若无结果，则返回该能力的结构化失败或未就绪状态，并保留能力 ID、错误码和降级原因。

## 迁移与兼容

实现按以下顺序进行：先引入注册表和测试，再迁移 Agent 与 API，最后切换路由和文档。可无歧义映射的旧正式 ID 可作为兼容别名，但响应必须标示新的规范 ID 及弃用信息。无 Agent 对应的旧 ID 不映射为其他专业模型，以免产生业务语义错误。
