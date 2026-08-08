## 1. 本地路由调用日志模块

- [x] 1.1 新建 `framework/observability/__init__.py`
- [x] 1.2 实现 `framework/observability/routing_log.py`：JSON 行式日志写入（含 trace_id、question、question_type、候选 Agent、命中排他规则、降级状态、耗时、失败原因、结果版本）
- [x] 1.3 实现 `framework/observability/observe.py`：`observe_routing()` 观测封装，包装 router/exclusive_rules 调用链
- [x] 1.4 实现本地日志路径与开关配置（默认 `logs/`，按天文件，可关闭）

## 2. 混淆矩阵与追溯链

- [x] 2.1 实现 `framework/observability/metrics.py`：`confusion_metrics()` 计算 TP/FP/FN/TN、accuracy、confusion_rate
- [x] 2.2 实现 `framework/observability/traceability.py`：按 trace_id 追溯数据版本、Agent 版本、参数、调用时间

## 3. 路由回归自动化

- [ ] 3.1 扩充 `tests/test_question_type_keywords.py`：model-1/5、model-2/3 各 ≥20 条正反例
- [ ] 3.2 新增 `tests/test_routing_observability.py` 测试混淆矩阵与追溯链
- [ ] 3.3 新增 `scripts/run_routing_regression.py`：自动运行回归并输出混淆矩阵，退出码反映目标达成

## 4. 路由看板

- [ ] 4.1 实现 `framework/observability/dashboard.py` 与 `__main__.py`：CLI 文本看板（正确率、混淆率、漏调用率、参数完整率）
- [ ] 4.2 看板支持导出 Markdown 报告

## 5. 验证与文档

- [ ] 5.1 运行全部相关测试确认通过
- [ ] 5.2 运行回归脚本输出混淆矩阵
- [ ] 5.3 更新 langsmith-monitoring 主 spec（同步本地日志要求）