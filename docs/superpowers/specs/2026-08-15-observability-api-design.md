---
comet_change: add-observability-api-endpoints
role: technical-design
canonical_spec: openspec
status: implemented-and-archived
archived_at: 2026-08-15
---

# 观测 API 端点与 trace_id 贯穿 — 技术设计

## Context

本地路由观测闭环已在 `framework/observability/` 落地：`routing_log`（JSON 行式落盘）、`metrics`（混淆矩阵）、`dashboard`（文本/Markdown 看板）、`traceability.trace_result`（按 trace_id 追溯）、`observe.observe_routing`（观测封装，已接入 `nodes.identify_question_node`）。这些能力目前仅以 CLI/模块形式存在：

- `trace_result()` 只在测试中被调用，无 HTTP 端点暴露。
- 看板只能通过 `python -m framework.observability.dashboard` 输出文本。
- chat 接口（`framework/api/routes/chat.py` 的 `/` 与 `/stream`）响应不返回 `trace_id`，用户无法端到端追溯一次路由/调用。

API 层为 Flask + Blueprint，现有端点均带 `@jwt_required` 鉴权（见 `framework/api/routes/` 与 `framework/api/app.py`）。编排层为 LangGraph：`MultiAgentOrchestrator.run` 返回 `model_results`，`run_stream` 手动执行节点并在 `done` 事件携带结果。`observe_routing` 当前返回 4 元组 `(question_type, relevance, final_type, routing_status)`，`trace_id` 仅作为可选入参写日志，不向外暴露。

## Goals / Non-Goals

**Goals:**
- 新增观测 API blueprint，暴露追溯链与看板指标端点，供前端实时查询。
- chat 接口（非流式 + 流式）响应返回本次调用的 `trace_id`，且与本地路由日志中的 trace_id 一致。
- 观测模块包级导出完整化，API 层统一 `from framework.observability import ...`。
- 端点沿用现有 JWT 鉴权约定。

**Non-Goals:**
- 不引入前端页面或实时推送（WebSocket）——只提供查询型 JSON API。
- 不改变观测模块内部落盘格式与算法（`routing_log` / `metrics` / `traceability` 保持不变）。
- 不做 LangSmith 远端 trace_id 关联（保持独立 uuid trace_id，属 llm-routing-judgment 范围约定）。
- 不做追溯链的批量/列表查询、不做看板历史趋势。

## Decisions

### D1: trace_id 通过 LangGraph state 贯穿

在 `MultiAgentState` 新增 `trace_id: Optional[str]` 字段。`identify_question_node` 调用 `observe_routing` 时获取本次调用实际使用的 trace_id 并写入 state（`observe_routing` 内部用 `trace_id or uuid.uuid4().hex` 生成，若 API 层传入则透传，否则自生成）。

- **方案 A（采用）**：`identify_question_node` 直接构造/透传 trace_id 写入 state，`run` 返回 dict 加 `trace_id`，`run_stream` 的 `done` 数据加 `trace_id`。
- 备选 B：改 `observe_routing` 返回 5 元组——不采用，会破坏现有 4 元组调用契约与测试，改动面大。
- 备选 C：API 层生成 trace_id 塞进 request——不采用，增加 request→state→日志三层贯穿，且与现有 `observe_routing` 自生成逻辑重复。

实现细节：`observe_routing` 已在 `entry` 中写入 `trace_id`，`identify_question_node` 需拿到该值。方案：在 `observe_routing` 内部额外把 `tid` 通过模块级状态或返回值副作用暴露——采用**最小侵入**做法：`observe_routing` 保持 4 元组签名不变，但新增可选关键字参数让调用方预生成 trace_id；`identify_question_node` 在调用前生成 `uuid.uuid4().hex` 传入，并把同一值写入 state。这样 chat 响应与日志天然一致，且无需改返回签名。

### D2: 观测 API 独立 blueprint

新增 `framework/api/routes/observability.py`，定义 `observability_bp`，在 `app.py` 注册为 `/api/v1/observability`：

- `GET /api/v1/observability/trace/<trace_id>` → `traceability.trace_result(trace_id)`，命中 200 + 追溯信息，未命中 404。
- `GET /api/v1/observability/dashboard` → 读取路由日志计算 `dashboard.compute_log_metrics`，读取 `logs/confusion_matrix.json`（及 `*.llm.json` 变体）返回结构化 JSON；缺失时返回默认值。
- 两者均 `@jwt_required`。

复用 `dashboard.compute_log_metrics` 避免指标逻辑漂移。看板矩阵读取与 `dashboard.main` 一致（`logs/` 目录），缺失时兜底空矩阵。

### D3: chat 接口返回 trace_id

`chat.py` 的 `/` 与 `/stream` 在 `response_data` 增加 `trace_id`，取自 `orchestrator.run/run_stream` 结果中的 `trace_id`。`run` 在 `model_results` 外层返回 dict 时附加 `trace_id`；`run_stream` 在 `done` 数据中附加。

### D4: 观测模块包导出完整化

`framework/observability/__init__.py` 导出 `routing_log`、`metrics`、`dashboard`、`traceability`、`observe`。

## Risks / Trade-offs

- [trace_id 贯穿涉及编排层] → state 新增字段 + `run`/`run_stream` 结果附加；用 `test_nodes_passthrough.py` 与 `test_routing_observability.py` 回归。
- [看板矩阵文件缺失/旧格式] → 复用 `dashboard.main` 的 `FileNotFoundError` 兜底，缺失返回默认值。
- [日志目录进程工作目录差异] → 沿用 `routing_log._LOG_DIR`（默认 `logs`）；测试用 `set_log_path` 隔离。
- [鉴权失败 401] → 与现有端点一致，不引入新鉴权机制。

## Migration Plan

- 后端：新增 blueprint、注册路由、state 字段、orchestrator 结果附加 trace_id、chat 响应附加 trace_id、包导出。
- 测试：新增 `tests/test_observability_api.py`；更新 `test_nodes_passthrough.py`、`test_routing_observability.py`。
- 回滚：删除 blueprint 注册与 state/响应附加字段即可，无数据迁移。

## Open Questions

无——技术方案与 open 阶段 design.md 决策一致，无影响 spec/任务拆分的未决项。
