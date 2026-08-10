## Context

当前系统已启用 LangSmith 远端追踪（framework/llm/service.py 读取 LANGCHAIN_* 环境变量），覆盖 LLM 调用远端 trace。已有的 framework/upload/audit_logger.py 提供 JSON 落盘模式用于数据导入审计，可作为本地日志的实现范式。五维路由（P1）已落地于 framework/agents/exclusive_rules.py 与 router.py，排他规则与"模型边界待确认"降级机制已就绪。但缺少本地路由/调用日志、混淆矩阵、路由回归自动化、路由看板与结果追溯链，无法量化路由质量。

## Goals / Non-Goals

**Goals:**
- 本地路由/调用日志落库：记录候选 Agent、路由理由、五维上下文、排他规则命中、降级状态、耗时、失败原因、结果版本。
- 混淆矩阵测试：model-1/5、model-2/3 两组易混淆对各 ≥20 条正反例，输出分类性能统计。
- 路由回归自动化：接入 test_question_type_keywords.py，可自动运行并输出混淆矩阵。
- 路由看板：展示路由正确率、重叠 Agent 混淆率、漏调用率、参数完整率。
- 结果可追溯链：结果可追溯到数据版本、Agent 版本、参数、调用时间。

**Non-Goals:**
- 不实现 P2 统一数据对象、P7 多模型编排、P8 结果保护。
- 不修改五维路由/排他规则自身逻辑。
- 不替代 LangSmith 远端追踪，两者并行覆盖。

## Decisions

### 决策 1：本地日志存储介质 —— 沿用 JSON 落盘（近似 audit_logger）
**选择**：在 `framework/observability/` 新增 JSON 行式日志文件（`logs/routing_calls.jsonl`、`logs/traceability.jsonl`），复用 audit_logger 的 JSON 落盘范式。
**理由**：无新增第三方依赖、易于人工审查与脚本解析、与现有数据导入审计一致。
**备选**：SQLite —— 提供更强查询能力，但引入新依赖与部署复杂度；本项目规模暂不需要。

### 决策 2：观测点注入位置
**选择**：在 `router.get_agents_for_type` 与 `exclusive_rules.apply_exclusive_rules` 外层包一层观测封装 `observe_routing()`，不侵入路由核心逻辑。
**理由**：保持路由纯逻辑可测，观测为横切关注点。
**备选**：直接修改路由函数内联记录 —— 耦合度高、难以独立测试。

### 决策 3：混淆矩阵计算
**选择**：新增 `confusion_metrics()`，基于真实标签与预测 result 计算 TP/FP/FN/TN、正确率、混淆率，输出字典。
**理由**：test_question_type_keywords.py 已有正反例断言基础设施，可复用其数据构造。
**备选**：引入 sklearn —— 过重，且两组二元混淆无需外部库。

### 决策 4：看板输出形式
**选择**：CLI 汇总命令 `python -m framework.observability.dashboard`，读取日志/矩阵输出文本看板；同时支持导出 Markdown 报告。
**理由**：无前端依赖，可脚本化、可进 CI，符合项目现有脚本风格（scripts/ 下已有 gen_full_verification_report.py 等）。
**备选**：HTML/Web 看板 —— 需要前端服务，超出 P9 范围。

### 决策 5：结果追溯链
**选择**：每条路由/调用日志记录 `trace_id`（会话/请求级），看板与日志均可按 trace_id 串联出"数据版本 → Agent 版本 → 参数 → 调用时间"链。
**理由**：单一头传播（propagation）实现简单，满足验收场景 ⑤。

## Risks / Trade-offs

- [日志性能开销] → 观测为轻量同步写 JSON，仅记录元数据不记录大 payload；日志路径可配置并可关闭。
- [本地日志与远端 trace 口径不一致] → 两者记录同一 `trace_id`，看板标注来源，便于对账。
- [混淆矩阵样本偏好] → 正反例由 test_question_type_keywords.py 的既有词干扩展生成，且两组易混淆对各 ≥20 条，保证代表性。
- [日志文件膨胀] → 提供轮转策略（按天/按大小），P9 先实现按天文件命名。

## Migration Plan

- 新增 `framework/observability/` 模块、`tests/test_routing_observability.py`、`scripts/run_routing_regression.py`。
- 在 router/exclusive_rules 调用链注入观测点，不改变现有路由行为。
- 无数据库 schema 变更，无破坏性接口变更；可随时回滚移除观测点。

## Open Questions

- 本地日志默认目录是否纳入 `.gitignore`（建议纳入，避免提交运行日志）。
- 看板是否需要实时文件监听（P9 先提供按需刷新，不做常驻监听）。