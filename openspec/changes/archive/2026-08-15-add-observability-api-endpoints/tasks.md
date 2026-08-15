## 1. 观测模块包导出完整化

- [x] 1.1 修改 `framework/observability/__init__.py`：导出 `routing_log`、`metrics`、`dashboard`、`traceability`、`observe`
- [x] 1.2 验证 `from framework.observability import traceability, dashboard, metrics` 可正常导入（现有测试不回归）

## 2. 追溯链 API 端点

- [x] 2.1 新增 `framework/api/routes/observability.py`，定义 `observability_bp`（url_prefix 由 app.py 注册为 `/api/v1/observability`）
- [x] 2.2 实现 `GET /trace/<trace_id>`：调用 `traceability.trace_result(trace_id, log_dir)`，命中返回 200 + 追溯信息，未命中返回 404
- [x] 2.3 实现 `GET /dashboard`：读取路由日志计算总调用数/漏调用率/参数完整率，读取混淆矩阵 JSON 计算正确率/混淆率，返回结构化 JSON；数据缺失时返回默认值
- [x] 2.4 两个端点均加 `@jwt_required` 鉴权，与现有端点一致
- [x] 2.5 在 `framework/api/app.py` 注册 `observability_bp` 为 `/api/v1/observability`

## 3. chat 接口返回 trace_id

- [x] 3.1 确认 `observe_routing` 现有签名与返回值，使编排层能取得本次调用的 trace_id（最小改动，保持向后兼容）
- [x] 3.2 `framework/agents/orchestrator.py` 的 `run` / `run_stream` 结果透传 trace_id
- [x] 3.3 `framework/api/routes/chat.py` 的 `/` 与 `/stream` 端点 `response_data` 新增 `trace_id` 字段
- [x] 3.4 确保流式与非流式两条路径均返回一致的 trace_id

## 4. 测试

- [x] 4.1 新增 `tests/test_observability_api.py`：追溯命中/未命中、看板指标、看板数据缺失、鉴权 401
- [x] 4.2 更新 `tests/test_nodes_passthrough.py` 或相关测试，断言 chat 响应含 trace_id
- [x] 4.3 更新 `tests/test_routing_observability.py`（如签名变化）并运行回归
- [x] 4.4 运行 `pytest tests/test_observability_api.py tests/test_routing_observability.py tests/test_nodes_passthrough.py` 全部通过
