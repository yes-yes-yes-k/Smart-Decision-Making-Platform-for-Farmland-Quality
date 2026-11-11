# Tasks: fix-chat-answer-quality

## Task 1: 修复酸化缺数据误报链路（Model-4 soil_ph 到达最终回答）

### Subtask 1.1 确认 model-4 参数传递
- [ ] 复核 `framework/function_calling/specialized_tools.py` `_model_4_wrapper` 的 `SJD` 参数注入路径；确认 `execute(task=payload)` 后 `SJD`（`soil_ph`）被带入 `_collect_inputs` 或 DB 读取回填
- [ ] 复核 `framework/domain/other_models/model_4.py` legacy 路径对 `SJD` 缺失的处理（`data_source != "db"` 时输出 `soil_ph` 是否为 legacy mock 值）
- **证据链接**：`openspec/changes/fix-chat-answer-quality/proposal.md`；DB 证 F1（`parcel_info.soil_indicators.soil_ph=5.1736` 实测）

### Subtask 1.2 结果契约携带实测字段
- [ ] 在 `framework/agents/output_contract.py` `_normalize_result` 的 model-4 分支确认：`soil_ph`/`acidification_level` 在 DB 实测输入存在时 SHALL 保留；仅 `background_acid`/`soil_conditioner_dosage`/`woody_peat_dosage` 在 imputed 时清空
- [ ] 若 `acidification_level` 为 None 且 `soil_ph` 非空，`classify_indicator("soil_ph", ...)` 已存在（`indicator_definitions.py`：<4.5 极强酸、[4.5,5.5) 强酸、[5.5,6.5) 酸）——验证该分类确实进入 `llm_context`
- **验收**：新增/更新测试 `tests/test_chat_schema_scenarios.py`：DB 存在 `soil_ph=5.17` 时回答不得出现「缺少实测酸碱度」

## Task 2: Model-1 稳定性路由保底（复合意图不被 LLM 初判吞掉）

- [ ] `framework/agents/routing.py` `identify_question_type` 增加稳定性复合意图保底：
  - 在 LLM 初判之后、`apply_exclusive_rules` 之前，若命中 type-1 强先验关键词（「稳不稳」「稳定吗」「退化风险」「等级稳定」「掉级」）则 `base_type` 强制回落到 1，`_last_router_method` 记录 `keyword_override_lm`
- [ ] 确认 `framework/agents/exclusive_rules.py` `PRIORITY_RESOLUTION`（`{model-1,model-2} → model-1`）在所有路由模式下生效
- **验收**：`pytest tests/test_agent_integration.py tests/test_role_based_routing.py`；问题「我的田质量等级稳不稳，退化风险高吗」最终 `question_type=1` 且 Model-1 执行

## Task 3: 正文兜底（空 LLM 总结不吞正文）

- [ ] `framework/agents/orchestrator.py` `run_stream` LLM 路径：`generate_stream` 返回空串或异常时，若 `full_answer` 仍为空，SHALL 以 `deterministic_answer` 拼接模型结果作为正文（现有异常分支已接，补齐「空流但无异常」场景）
- [ ] `framework/agents/nodes.py` `aggregate_results` 非流式路径同规则
- [ ] 复核「正文只有前缀（如 336/338/340 案例）」场景：`analysis_object` 前缀后必须拼接确定性正文或 field_query 直查文案
- **验收**：新增会话级断言：连续 4 问（稳不稳/等级/障碍度排序/酸化严重吗）每轮正文非空

## Task 4: 字段幻觉治理 + 障碍度排序有序渲染

- [ ] `framework/agents/parcel_field_query.py` `_format_value` 支持 Mapping：障碍度 dict 按权威键顺序渲染为「标签 数值」（禁止 `str(dict)` 字面量暴露 `{...}`）
- [ ] `build_professional_answer_prompt`（`nodes.py`）增加字段白名单约束：总结只能使用 `result` 实际存在的字段名；LLM 正文出现白名单外字段（如「耕作制度」→ 正确名「耕层质地」）SHALL 丢弃对应句子/回退确定性模板
- [ ] `framework/domain/public_field_labels.py` 复核 `GCZD`→「耕层质地」映射被正确使用；确认模型中不存在「耕作制度」键（幻觉来源）
- **验收**：`pytest tests/test_parcel_field_query.py`：障碍度输出无 `{`/`'` 字面量、顺序与权威 dict 一致；正文无「耕作制度」
- **预期行为**：答案渲染为「障碍度排序（数值=障碍贡献，0=暂无显著障碍）：① 质地构型 0.23、① 有机质 0.23（并列主要障碍）、③ 速效钾 0.19、④ 土壤酸碱度 0.14…」

## Task 5: Model-1 历史快照驱动稳定性结论

- [ ] 复核 `framework/agents/specialized/stability_agent.py` DB 路径：`parcel_history_snapshot` ≥2 期时 `stability_modules` 输出等级趋势/掉级风险结论（DB 实证 F2：3597 存在 2018/2021/2024 三期）
- [ ] `deterministic_answer`/prompt 稳定性规则保持：「历史不足时明确告知需补充 ≥2 期快照」；历史充足时禁止复述「暂无法判断」
- **验收**：3597「稳不稳定」重放后输出稳定性/退化风险结论，不是仅返回等级

## Task 6: 会话上下文已知前提注入（复用跨轮结果）

- [ ] `run_stream` 在最终 LLM 总结前，将同会话同地块上一轮已发布的模型结果（如障碍度中「土壤酸碱度 0.14」）作为「已知前提」注入 prompt，使本轮（如酸化）回答能区分「障碍度≠实测 pH」
- [ ] 仅当 `conversation_id` 相同且对象 id 相同才注入；禁止跨地块注入
- **验收**：Q3（障碍度）后接 Q4（酸化），回答说明「障碍度显示土壤酸碱度为影响因子（0.14），但无实测 pH，无法定级，建议补测」

## Task 7: 回归保护（会话级断言 + git 提交收口）

- [ ] 新增集成断言：
  - Q4 在 DB 存在 `soil_ph` 时回答不得含「缺少实测酸碱度」
  - Q1 稳定性复合提问路由为 type-1 且正文含稳定性/降级结论
  - Q3 障碍度无 dict 字面量、无「耕作制度」、字段与权威一致
  - 每轮正文非空
- [ ] `git add` 并提交本 change 涉及代码 + 当前工作区未提交的原有修复（nodes/orchestrator/output_contract/parcel_field_query/routing/manager/versioned_results/public_numbers.py），避免再次被 Revert 丢失
- [ ] 运行 `pytest` 全量确认无既有用例回归
- **验收**：`openspec verify --change fix-chat-answer-quality` 通过
