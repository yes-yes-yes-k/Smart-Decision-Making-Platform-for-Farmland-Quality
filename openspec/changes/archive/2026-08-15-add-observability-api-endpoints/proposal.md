## Why

本地观测闭环（`framework/observability/`）已实现路由日志落库、混淆矩阵、看板与追溯链，但目前这些能力只以 CLI/模块形式存在：`trace_result()` 仅在测试中被调用，看板只能通过 `python -m framework.observability.dashboard` 输出文本，chat 接口响应也不返回 `trace_id`。产品侧无法通过 API 按 `trace_id` 追溯一次路由/调用，也无法实时查看路由正确率、混淆率、漏调用率等指标，导致「结果可追溯率 100%」与「路由看板实时展示」的验收目标无法达成。

## What Changes

- **chat API 响应新增 `trace_id`**：`framework/api/routes/chat.py` 的 `/` 与 `/stream` 端点返回 `trace_id`，并在编排入口处生成/透传同一 `trace_id`，供前端与用户后续追溯。
- **新增追溯链 API 端点**：提供按 `trace_id` 查询一次调用的追溯信息（数据版本、Agent 版本、参数、调用时间）的 HTTP 端点，暴露 `traceability.trace_result()`。
- **新增路由看板 API 端点**：提供路由正确率、重叠 Agent 混淆率、漏调用率、参数完整率的 JSON 看板端点，供前端实时展示，并保留现有文本/Markdown 看板能力。
- **观测模块导出完整化**：`framework/observability/__init__.py` 导出 `routing_log`、`metrics`、`dashboard`、`traceability`、`observe`，保证包级入口可用。

## Capabilities

### New Capabilities
- `observability-api`: 将本地路由观测能力（追溯链 + 看板指标）以 HTTP API 暴露，支持按 `trace_id` 追溯调用详情与查询路由质量指标。

### Modified Capabilities
- `routing-observability`: 路由看板与结果可追溯链从「仅 CLI/模块」扩展为「同时通过 HTTP API 提供」；chat 接口响应返回 `trace_id` 以支撑端到端追溯。

## Impact

- 代码：`framework/api/routes/chat.py`（响应新增 `trace_id`）、新增 `framework/api/routes/observability.py`（追溯 + 看板端点）、`framework/api/app.py`（注册新 blueprint）、`framework/observability/__init__.py`（导出完整化）。
- 编排：`framework/agents/orchestrator.py` / `framework/agents/nodes.py` 透传 `trace_id`（如尚未贯穿）。
- 测试：新增/更新 `tests/test_observability_api.py`，更新 `tests/test_routing_observability.py` 与 `tests/test_nodes_passthrough.py`。
- 文档：《大模型开发团队下一步工作建议.docx》P9 可观测性阶段标注 API 端点落地情况（可选）。
- 依赖：无新增第三方依赖（复用 Flask blueprint 与现有 observability 模块）。
