## Context

本地观测闭环已在 `framework/observability/` 实现：`routing_log`（JSON 行式落盘）、`metrics`（混淆矩阵）、`dashboard`（文本/Markdown 看板）、`traceability`（按 trace_id 追溯）、`observe`（观测封装，已接入 `nodes.identify_question_node`）。API 层使用 Flask + Blueprint，现有路由均带 `@jwt_required` 鉴权（见 `framework/api/routes/` 与 `framework/api/app.py`）。当前缺口：观测能力未暴露为 HTTP API，chat 响应未返回 trace_id，`observability/__init__.py` 仅导出 `routing_log`。

## Goals / Non-Goals

**Goals:**
- 新增观测 API blueprint，暴露追溯链与看板指标两个端点
- chat 接口（`/` 与 `/stream`）响应返回本次调用的 trace_id
- 观测模块包级导出完整化
- 端点沿用现有 JWT 鉴权约定

**Non-Goals:**
- 不引入新的前端页面或实时推送（WebSocket）——本次只提供查询型 JSON API
- 不改变观测模块内部落盘格式与算法（`routing_log`/`metrics`/`traceability` 保持不变）
- 不处理 LangSmith 远端 trace_id 的关联（保持独立 uuid trace_id，spec 中"共享同一 trace_id"已在 llm-routing-judgment 范围约定，本次不扩展）
- 不实现结果追溯链的批量/列表查询

## Decisions

**D1: 新增独立 blueprint `observability_bp`**
新增 `framework/api/routes/observability.py`，在 `app.py` 注册为 `/api/v1/observability`。与现有 `docs_bp`/`chat_bp` 等约定一致。
- 备选：塞进 `chat_bp`——不采用，观测与对话关注点不同，独立 blueprint 更清晰且便于后续扩展看板/追溯列表。

**D2: 端点设计**
- `GET /api/v1/observability/trace/<trace_id>` → 调用 `traceability.trace_result(trace_id)`，命中返回 200 + 追溯信息，未命中返回 404。
- `GET /api/v1/observability/dashboard` → 读取路由日志计算 `compute_log_metrics`，读取 `logs/confusion_matrix.json`（及 `*.llm.json` 变体）计算指标，返回 JSON。
- 两者均 `@jwt_required`，沿用现有鉴权模式。
- 备选：用 `/api/v1/observability/trace?trace_id=...` 查询参数——不采用，RESTful 路径参数更直观，且 trace_id 为路径安全字符。

**D3: 看板指标读取复用 dashboard 模块**
复用 `dashboard.compute_log_metrics` 与 `dashboard.format_dashboard` 的能力，但 API 返回结构化 JSON（而非文本），直接读取路由日志与混淆矩阵 JSON。为保持 API 稳定，用 `logs/` 目录作为默认日志与矩阵位置（与现有脚本一致）。
- 备选：在 observability.py 中重复实现指标计算——不采用，复用现有纯函数避免逻辑漂移。

**D4: chat 响应返回 trace_id**
`observe_routing` 已生成/透传 trace_id 并写入日志，但返回值未暴露 trace_id 到编排层。方案：让 `observe_routing` 的返回值或 state 携带 trace_id（新增返回字段或 state 字段），`multi_agent_orchestrator.run/run_stream` 透传到结果，`chat.py` 在 `response_data` 增加 `trace_id`。实现细节以 build 阶段确认 `observe_routing` 现有签名后最小改动为准（新增可选返回字段，保持向后兼容）。

**D5: 观测模块包导出完整化**
`framework/observability/__init__.py` 从 `from . import routing_log` 扩展为导出 `routing_log`、`metrics`、`dashboard`、`traceability`、`observe`，便于 API 层统一 `from framework.observability import ...`。

## Risks / Trade-offs

- [trace_id 贯穿涉及编排层改动] → chat 非流式/流式两条路径都要透传；build 阶段先确认 `observe_routing` 现有签名与编排返回结构，做最小改动并用 `tests/test_nodes_passthrough.py` 等现有测试回归。
- [看板矩阵文件可能缺失/为旧格式] → `dashboard.main` 已有 `FileNotFoundError` 兜底返回空矩阵；API 层复用同一逻辑，缺失时返回默认值而非报错。
- [日志目录在 API 进程工作目录下的差异] → 沿用 `routing_log._LOG_DIR`（默认 `logs`），与回归脚本/看板 CLI 一致；如部署工作目录不同，可通过现有 `set_log_dir` 或环境约定对齐。
- [鉴权失败时返回 401] → 与现有端点一致，不引入新鉴权机制。
