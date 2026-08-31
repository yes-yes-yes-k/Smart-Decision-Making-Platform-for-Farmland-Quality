# 专题模型输出契约迁移说明

## Schema 2.0（默认）

`POST /api/v1/models/run` 的 `data` 是完整模型结果信封：

```json
{
  "schema_version": "2.0",
  "trace_id": "<uuid>",
  "status": "ok",
  "data": {
    "model_id": "quality-grade-evaluation",
    "status": "ok",
    "subject": {"type": "parcel", "id": "P-1"},
    "result": {
      "quality_grade": "一等",
      "composite_index": 0.88,
      "indicators": {},
      "obstacle_degree": []
    },
    "meta": {"data_source": "csv", "simulated": false, "model_version": null},
    "issues": []
  }
}
```

六个正式模型的业务字段只出现在 `data.result`。`status` 只能是
`ok`、`degraded`、`rejected`、`unavailable` 或 `error`；失败状态的 `result` 为 `null`。

聊天接口默认只返回 `message_id`、`answer`、`sources`、`recommendations` 和 `routing`。
需要模型摘要时，在请求中加入 `include_model_results=true`，返回 `data.models` 的精简投影。
RAG 问题不会返回 `models`。

## Schema 1.0 兼容窗口

在迁移完成前，可在专题模型或聊天请求中加入 `response_schema: "1.0"`。
旧响应由 Schema 2.0 规范结果单向投影生成，并带有 `SCHEMA_1_DEPRECATED` 提示；旧结构不会参与模型计算。

| 旧字段 | Schema 2.0 | 说明 |
| --- | --- | --- |
| `analysis` / `evidence` | `data.result` | 业务事实统一放在 result |
| `degraded` / `fallback` / `reliability` | `data.status`、`data.meta`、`data.issues` | 状态、运行事实和问题分离 |
| `model` / `capability` | 模型目录接口 | 执行结果不重复返回能力描述 |
| 聊天 `question_type` / `routing_status` | 聊天 `data.routing` | 路由字段集中在 routing |
| 聊天 `model_results.data.details` | 聊天 `data.models` | 仅显式请求时返回精简投影 |

兼容调用量和规范状态计数可通过 `GET /api/v1/observability/dashboard` 的 `schema_metrics` 查看。
下线 Schema 1.0 前，应确认 `schema_calls["1.0"]` 已降为零，并完成前端字段迁移。
