---
comet_change: add-observability-closure
role: technical-design
canonical_spec: openspec
---

# P9 本地可观测性闭环 技术设计

## Context

当前系统已启用 LangSmith 远端追踪（framework/llm/service.py 读取 LANGCHAIN_* 环境变量），覆盖 LLM 调用远端 trace。已有 framework/upload/audit_logger.py 提供 JSON 落盘模式用于数据导入审计。五维路由（P1）已落地于 framework/agents/exclusive_rules.py 与 routing.py，排他规则与「模型边界待确认」降级机制已就绪。运行时路由入口为 framework/agents/nodes.py 的 `identify_question_node`（调用 `identify_question_type` + `apply_exclusive_rules`）。

但系统缺少本地持久化路由/调用日志、路由混淆矩阵、路由回归自动化、路由看板与结果追溯链，无法量化「正确路由率、重叠 Agent 混淆率、漏调用率」。

## Goals / Non-Goals

**Goals：**
- 本地路由/调用日志落库：候选 Agent、路由理由、五维上下文、排他规则命中、降级状态、耗时、失败原因、结果版本。
- 混淆矩阵测试：model-1/5、model-2/3 两组易混淆对各 ≥20 条正反例，输出分类性能统计。
- 路由回归自动化：可自动运行并输出混淆矩阵。
- 路由看板：路由正确率、重叠 Agent 混淆率、漏调用率、参数完整率。
- 结果可追溯链：结果可追溯到数据版本、Agent 版本、参数、调用时间。

**Non-Goals：**
- 不实现 P2 统一数据对象、P7 多模型编排、P8 结果保护。
- 不修改五维路由/排他规则自身逻辑。
- 不替代 LangSmith 远端追踪，两者并行覆盖。

## Decisions

### 决策 1：本地日志存储介质 — JSON 行式落盘
新增 `framework/observability/routing_log.py`，将路由判定写为 JSON 行式文件（`logs/routing_calls.jsonl`、`logs/traceability.jsonl`），复用 audit_logger 范式。
**备选**：SQLite — 引入新依赖与部署复杂度，本项目规模暂不需要。

### 决策 2：观测点注入位置
在 `nodes.identify_question_node` 内包装两次路由调用（`identify_question_type` + `apply_exclusive_rules`），通过 `observe_routing()` 记录观测数据，不侵入路由核心逻辑。
**备选**：直接内联记录 — 耦合高、难以独立测试。

### 决策 3：混淆矩阵计算
新增 `metrics.py::confusion_metrics()`，基于真实标签与预测结果计算 TP/FP/FN/TN、accuracy、confusion_rate，输出字典。
**备选**：sklearn — 过重。

### 决策 4：看板输出形式
CLI 命令 `python -m framework.observability.dashboard`，读取日志/矩阵输出文本看板，支持导出 Markdown。
**备选**：HTML/Web 看板 — 需前端服务，超出 P9 范围。

### 决策 5：结果追溯链
每日志记录 `trace_id`（会话/请求级），看板与日志可按 trace_id 串联「数据版本 → Agent 版本 → 参数 → 调用时间」链。

## Risks / Trade-offs

- [日志性能开销] → 轻量元数据，路径可配置并可关闭。
- [本地与远端 trace 口径不一致] → 共享同一 trace_id，看板标注来源。
- [混淆矩阵样本偏好] → 复用 test_question_type_keywords.py 既有词干扩展，两组各 ≥20 条。
- [日志文件膨胀] → 按天文件命名。

## Migration Plan

- 新增 `framework/observability/` 模块、`tests/test_routing_observability.py`、`scripts/run_routing_regression.py`。
- 在 `nodes.identify_question_node` 注入观测点，不改变现有路由行为。
- 无数据库 schema 变更，无破坏性接口变更；可随时回滚移除观测点。

## Open Questions

- 本地日志默认目录是否纳入 `.gitignore`（建议纳入）。
- 看板暂不做常驻监听，按需刷新。