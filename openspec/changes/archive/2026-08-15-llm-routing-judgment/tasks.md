## 1. 配置与 LLM 路由核心

- [x] 1.1 在 `Config` 新增 `ROUTING_MODE` 字段（环境变量 `ROUTING_MODE`，默认 `llm`） — commit 980e22b
- [x] 1.2 在 `routing.py` 新增 `_identify_question_type_llm(question, context)`，返回 `(question_type, relevance, reason)`，构造 LLM prompt 要求返回严格 JSON — commit bf0aaea
- [x] 1.3 新增 `_safe_parse_llm_result` 解析函数：JSON 解析失败、字段缺失、类型越界（非 0..6）时返回 `None` — commit 3925ad5
- [x] 1.4 修改 `identify_question_type`：当 `ROUTING_MODE=llm` 且 LLM 可用时，先 LLM 初判，失败回退关键词/向量判定，再叠加排他规则 — commit 0f6abde

## 2. 观测与可测性

- [x] 2.1 修改 `observe.py`：日志 entry 新增 `router_method`、`llm_reason`、`llm_duration_ms`，`ROUTING_RESULT_VERSION` 递增至 `v1.2` — commit 36071d4
- [x] 2.2 更新 `nodes.py` 相关调用，确保观测字段透传 — commit d9ddf9a（端到端验证透传）
- [x] 2.3 混淆矩阵回归脚本（`scripts/run_routing_regression.py`）支持 mock LLM 固定输出，验证 LLM 路由与 keyword 路由一致 — commit c4f73bc

## 3. 测试

- [x] 3.1 新增 `tests/test_llm_routing.py`：覆盖开关、LLM 可用/不可用、JSON 解析失败回退、越界类型回退、排他规则叠加 — commit 0f6abde
- [x] 3.2 更新 `tests/test_question_type_keywords.py` 与 `test_routing_observability.py` 适配 `router_method` 字段 — commit d9ddf9a
- [x] 3.3 运行全部相关测试，确认 LLM 路由与 keyword 路由下混淆率均 ≤ 3% — 见下方回归验证

## 4. 文档更新

- [x] 4.1 更新《大模型开发团队下一步工作建议.docx》：新增 P10 章节（LLM 路由判断） — commit 46278ed
- [x] 4.2 文档补充混淆矩阵方法说明与结果表 — commit 46278ed
- [x] 4.3 将 docx P1-P9 模型表同步为当前 6 模型编号（model-1..model-6） — commit 46278ed