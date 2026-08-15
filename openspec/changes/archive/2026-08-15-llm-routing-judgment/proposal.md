## Why

当前五维路由完全基于硬编码关键词、embedding 向量阈值与排他规则，无法理解自然语言的语义变体（如口语化、同义表达、隐含意图），易在边界场景误判。LLM 已接入（`framework/llm/service.py`）但仅用于结果总结，未参与路由判定。引入 LLM 全量初判可显著提升路由对语义的理解能力，同时保留关键词与排他规则作为确定性兜底。

## What Changes

- **新增 `ROUTING_MODE` 配置开关**（`llm` / `keyword`），默认 `llm`，可回退纯关键词模式。
- **新增 LLM 路由判定函数**：在 `identify_question_type` 中，当 `ROUTING_MODE=llm` 且 LLM 可用时，先调用 LLM 判定问题类型（`question_type` + `reason`，JSON 输出）。
- **LLM 输出解析与回退**：LLM 不可用、JSON 解析失败或返回非法类型时，自动回退到关键词判定，路由不中断。
- **排他规则兜底不变**：LLM 判定结果仍叠加 `apply_exclusive_rules` 消解 model-3/2、model-4/5 易混淆对。
- **观测日志增强**：`observe.py` 记录 `router_method`（llm/keyword）、LLM reason、LLM 耗时。
- **混淆矩阵文档化**：在《大模型开发团队下一步工作建议》docx 中补充混淆矩阵方法说明与结果表，并将 P1-P9 模型表同步为当前 6 模型编号（model-1..model-6）。
- **新增 P10 章节**：文档新增「P10 LLM 路由判断」章节。

## Capabilities

### New Capabilities
- `llm-routing-judgment`: 基于 LLM 的路由判定能力，含 `ROUTING_MODE` 开关、JSON 输出与解析回退、排他规则兜底、观测日志增强。

### Modified Capabilities
- `role-based-routing`: 路由判定新增 LLM 初判路径与 `ROUTING_MODE` 配置，仍保留关键词/向量/排他规则兜底。

## Impact

- 代码：`framework/agents/routing.py`、`framework/config.py`、`framework/agents/nodes.py`、`framework/observability/observe.py`、`framework/llm/service.py`（prompt 辅助）。
- 测试：`tests/test_question_type_keywords.py`、`tests/test_routing_observability.py`、新增 LLM 路由测试。
- 文档：《大模型开发团队下一步工作建议.docx》（P10 章节 + 混淆矩阵 + 模型表同步）。
- 依赖：LLM 服务（SiliconFlow），需配置 `SILICONFLOW_KEY`。