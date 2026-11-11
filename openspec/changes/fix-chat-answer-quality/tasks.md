# Tasks: fix-chat-answer-quality

> 依据 design.md 的 D1–D6 决策与 delta spec 实施。全部任务已完成，代码已提交（d137c7f）。

## Task 1: 修复酸化缺数据误报链路（Model-4 soil_ph 到达最终回答）

- [x] 复核 `framework/function_calling/specialized_tools.py` `_model_4_wrapper` 的 `SJD` 参数注入路径；确认 `execute(task=payload)` 后 `SJD`（`soil_ph`）被带入 `_collect_inputs` 或 DB 读取回填
- [x] 复核 `framework/domain/other_models/model_4.py` legacy 路径对 `SJD` 缺失的处理（`data_source != "db"` 时输出 `soil_ph` 是否为 legacy mock 值）
- [x] 在 `framework/agents/output_contract.py` `_normalize_result` 的 model-4 分支确认：`soil_ph`/`acidification_level` 在 DB 实测输入存在时保留；仅 `background_acid`/`soil_conditioner_dosage`/`woody_peat_dosage` 在 imputed 时清空
- [x] `classify_indicator("soil_ph", ...)` 已存在（<4.5 极强酸、[4.5,5.5) 强酸、[5.5,6.5) 酸），并已在 `framework/agents/nodes.py` 新增 `build_acidification_state_prefix` 确定性前缀（有实测报 pH+分级；无实测给补测引导），修复链路丢字段断点

## Task 2: Model-1 稳定性路由保底（复合意图不被 LLM 初判吞掉）

- [x] `framework/agents/routing.py` `identify_question_type` 增加稳定性复合意图保底：命中「稳不稳/稳定吗/退化风险/等级稳定/掉级/稳定性」时，LLM 初判后强制回落到 type-1，`_last_router_method` 记录 `keyword_override_llm`
- [x] 确认 `framework/agents/exclusive_rules.py` `PRIORITY_RESOLUTION`（`{model-1,model-2} → model-1`）在所有路由模式下生效
- **验收**：`tests/test_chat_answer_quality.py` 中 mock LLM 判 type-2 时最终回落 type=1（已验证通过）

## Task 3: 正文兜底（空 LLM 总结不吞正文）

- [x] `framework/agents/orchestrator.py` `run_stream` LLM 路径：`generate_stream` 空流/失败时用 `deterministic_answer` 拼接模型结果作为正文（不再只剩前缀）
- [x] `framework/agents/nodes.py` `aggregate_results` 非流式路径同规则（正文空或含幻觉字段时兜底）
- [x] 复核「正文只有前缀」场景：`analysis_object` 前缀后必须拼接确定性正文或 field_query 直查文案（已覆盖）

## Task 4: 字段幻觉治理 + 障碍度排序有序渲染

- [x] `framework/agents/parcel_field_query.py` `_format_value` 支持 Mapping：障碍度 dict 按权威键顺序渲染为「标签 数值」（禁止 `str(dict)` 字面量）
- [x] `build_professional_answer_prompt` 增加字段白名单约束；新增 `has_prohibited_field_name`（拦截「耕作制度」）并在流式/非流式出口回退确定性模板
- [x] 复核 `framework/domain/public_field_labels.py`：`GCZD→耕层质地` 映射正确，模型无「耕作制度」键（幻觉来源已确认）
- **验收**：`tests/test_chat_answer_quality.py` 断言障碍度渲染无 `{`/`'`、`has_prohibited_field_name("耕作制度")` 为真

## Task 5: Model-1 历史快照驱动稳定性结论

- [x] 复核 `framework/agents/specialized/stability_agent.py` DB 路径：`parcel_history_snapshot` ≥2 期时 `stability_modules` 计算等级趋势/掉级风险（DB 实证 3597 存在 2018/2021/2024 三期）
- [x] `deterministic_answer`/prompt 稳定性规则：历史不足时明确告知需补充 ≥2 期快照；prompt 新增「历史充足时禁止复述暂无法判断」规则

## Task 6: 会话上下文已知前提注入（复用跨轮结果）

- [x] `framework/agents/nodes.py` 新增 `extract_prior_knowledge`；`run_stream` 在最终 LLM 总结前将同会话同地块上一轮结论（如障碍度中「土壤酸碱度 0.14」）注入「已知前提」
- [x] 仅当 `conversation_id` 相同且对象 id 相同才注入；禁止跨地块注入（测试断言跨地块返回空）
- **验收**：`tests/test_chat_answer_quality.py` `test_extract_prior_knowledge_same_parcel` / `test_extract_prior_knowledge_cross_parcel_blocked` 通过

## Task 7: 回归保护（会话级断言 + git 提交收口）

- [x] 新增集成断言（`tests/test_chat_answer_quality.py`，8 passed）：酸化实测前缀、稳定性路由保底、障碍度渲染、幻觉字段拦截、已知前提注入
- [x] `git add` 并提交本 change 代码 + 原有未提交修复（nodes/orchestrator/output_contract/parcel_field_query/routing/manager/versioned_results/public_numbers.py），提交 `d137c7f`，防再次 Revert 丢失
- [ ] 运行 `pytest` 全量确认无既有用例回归（全量受本机 pandas/numpy 版本冲突限制，受影响模块子集 169 passed + 新增 8 passed；`test_soil_depth_and_plow_depth_are_not_confused` 为既有失败，与本次改动无关）
