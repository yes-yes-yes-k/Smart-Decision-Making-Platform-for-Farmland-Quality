# Brainstorm Summary

- Change: add-observability-closure
- Date: 2026-08-08

## 确认的技术方案

新增 `framework/observability/` 包作为横切观测层，不侵入路由/排他规则核心逻辑：
- `routing_log.py`：JSON 行式日志（trace_id、question、候选 Agent、命中排他规则、降级状态、耗时、失败原因、结果版本）
- `observe.py`：`observe_routing()` 观测封装，包装 nodes.identify_question_node 的两次路由调用（identify_question_type + apply_exclusive_rules）
- `metrics.py`：`confusion_metrics()` 计算 TP/FP/FN/TN、accuracy、confusion_rate
- `traceability.py`：按 trace_id 追溯数据版本/Agent 版本/参数/调用时间
- `dashboard.py` + `__main__.py`：CLI 文本看板（正确率/混淆率/漏调用率/参数完整率），可导出 Markdown

## 关键取舍与风险

- 日志介质：JSON 落盘（logs/routing_calls.jsonl、logs/traceability.jsonl），复用 audit_logger 范式，无新增依赖
- 观测点：nodes.identify_question_node 内包装两次路由调用
- 混淆矩阵：纯 Python，复用 test_question_type_keywords.py 已有 model-1/5、model-2/3 正反例（≥20）
- 追溯链：每日志带 trace_id，串联数据版本→Agent版本→参数→调用时间
- 风险：日志性能→轻量元数据+可配置路径开关；本地与远端口径→共享 trace_id；日志膨胀→按天文件

## 测试策略

- 新增 tests/test_routing_observability.py（日志落盘、混淆矩阵、追溯链、看板）
- 新增 scripts/run_routing_regression.py（自动回归+输出混淆矩阵，退出码反映达标）

## Spec Patch

无（specs 已覆盖全部需求，无需回写）