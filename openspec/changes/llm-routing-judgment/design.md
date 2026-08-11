## Context

当前路由流水线为确定性硬编码：`identify_question_type` → 关键词匹配 → embedding 向量阈值 → `apply_exclusive_rules` 排他规则兜底。该链路可测、确定性高，但无法理解自然语言语义变体。LLM 服务（`framework/llm/service.py`，SiliconFlow）已接入并用于结果总结，未参与路由判定。

本项目已实现完整的观测体系（`framework/observability/`）：本地 JSON 行式日志、混淆矩阵、路由回归、看板、trace 追溯链。引入 LLM 路由判定需与此观测体系无缝集成，保证可测性与可回滚性。

## Goals / Non-Goals

**Goals:**
- 新增 `ROUTING_MODE` 开关（`llm` / `keyword`），默认 `llm`，支持灰度与回滚。
- LLM 全量初判问题类型，返回 JSON（`question_type` + `reason`）。
- LLM 不可用 / JSON 解析失败 / 非法类型时，自动回退关键词判定，路由不中断。
- 排他规则在 LLM 判定后仍作为最终兜底，消解 model-3/2、model-4/5 易混淆对。
- 观测日志记录 `router_method`、LLM reason、LLM 耗时，保持与现有 trace 对账。
- 混淆矩阵回归适配 LLM 路由（mock LLM 固定输出）。
- docx 新增 P10 章节 + 混淆矩阵方法/结果 + 模型表同步为 6 模型编号。

**Non-Goals:**
- 不改变 5 个专业模型实现与排他规则语义。
- 不引入多 Agent 并行路由。
- 不改变结果生成链路（`llm_generate` / `aggregate_results`）。
- 不做 LLM 成本优化（如缓存、批量）——本次仅接入判定。

## Decisions

### D1: `ROUTING_MODE` 配置开关
- 决策：在 `Config` 新增 `ROUTING_MODE` 字段，读环境变量 `ROUTING_MODE`，默认 `llm`。
- 理由：可灰度切换与快速回滚；`keyword` 模式完全保留现有行为。
- 备选：自动判断无开关——放弃，因无法快速回滚。

### D2: 新增 `_identify_question_type_llm` 函数
- 决策：在 `routing.py` 新增 `_identify_question_type_llm(question, context) -> tuple[int, float, Optional[str]]`，返回 `(question_type, relevance, reason)`。
- 理由：保持 `identify_question_type` 对外签名向后兼容，LLM 路径作为内部实现。
- 决策：`identify_question_type` 在 keyword 判定后、排他规则前插入 LLM 判定（当 `ROUTING_MODE=llm` 且 LLM 可用时）。LLM 判定优先于关键词，关键词作为 LLM 失败/不可用时的回退。

### D3: LLM JSON 输出与严格解析回退
- 决策：prompt 要求 LLM 返回严格 JSON `{"question_type": 1..6 或 0, "reason": "..."}`，禁用 markdown 代码块。
- 决策：解析失败（非 JSON / 字段缺失 / 类型越界）时，`_safe_parse_llm_result` 返回 `None`，调用方回退关键词判定。
- 理由：LLM 是概率性输出，必须强容错，绝不能因 LLM 异常导致路由中断或抛出到主流程。

### D4: 排他规则兜底不变
- 决策：LLM 判定结果（`refined_type`）仍传入 `apply_exclusive_rules(question, llm_type, context)`。
- 理由：排他规则是确定性数据驱动，能消解 LLM 在易混淆对上的潜在误判，保障混淆率 ≤ 3% 目标。

### D5: 观测日志增强
- 决策：`observe.py` 的日志 entry 新增字段：`router_method`（llm/keyword）、`llm_reason`、`llm_duration_ms`。
- 理由：`ROUTING_RESULT_VERSION` 递增至 `v1.2`，标识 LLM 判定签名引入。
- 决策：混淆矩阵回归脚本支持对 LLM 路由 mock 固定输出，保持可测。

### D6: 文档更新策略
- 决策：docx 使用 pandoc 转换 + OOXML 编辑（redlining 保留跟踪记录），新增 P10 章节，补充混淆矩阵方法说明与结果表，同步 P1-P9 模型表为新 6 模型编号。
- 理由：文档需与代码重排后的 6 模型体系一致，并记录 LLM 判断演进。

## Risks / Trade-offs

- [LLM 每次请求延迟与成本增加] → 提供 `ROUTING_MODE=keyword` 回退；LLM 超时配置已在 `Config.SILICONFLOW_LLM_TIMEOUT`。
- [LLM 输出不稳定（非 JSON / 越界类型）] → 严格解析 + 回退关键词，路由不中断（D3）。
- [LLM 在易混淆对误判] → 排他规则确定性兜底 + 混淆矩阵回归监控（D4）。
- [回归测试受 LLM 概率性影响] → 测试 mock LLM 固定输出，LLM 路径与 keyword 路径分别断言。
- [docx 编辑破坏格式] → 使用 pandoc 提取 + OOXML 精确编辑 + pack 后 pandoc 复核。