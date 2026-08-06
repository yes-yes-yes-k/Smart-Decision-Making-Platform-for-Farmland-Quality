## 1. 维度提取扩展

- [ ] 1.1 在 `framework/agents/nodes.py` 的 `_extract_five_dim_context` 中新增业务任务提取：定义 `BUSINESS_TASK_KEYWORDS` 关键词表（障碍诊断/酸化改良/有机质培肥/稳定性评价/质量等级评价），从问题文本提取 `business_task` 标签写入 context
- [ ] 1.2 在 `framework/agents/nodes.py` 的 `_extract_five_dim_context` 中新增预期输出提取：定义 `EXPECTED_OUTPUT_KEYWORDS` 关键词表（评价结果/处方用量/诊断报告），从问题文本提取 `expected_output` 标签写入 context
- [ ] 1.3 确认 `_extract_five_dim_context` 返回的 context 包含 `scale`、`data_type`、`business_task`、`expected_output` 四个维度字段

## 2. 排他规则结构扩展

- [ ] 2.1 在 `framework/agents/exclusive_rules.py` 的 `ExclusiveRule` dataclass 中新增 `dimension_conditions: Dict[str, str]` 字段（默认空 dict），用于声明维度判别条件（如 `{"scale": "地块", "data_type": "评价结果"}`）
- [ ] 2.2 新增 `_dimension_conditions_match(dimension_conditions, context)` 函数：检查 context 中对应维度值是否全部匹配 dimension_conditions
- [ ] 2.3 更新 `apply_exclusive_rules` 判定逻辑：一条规则匹配当且仅当 `condition` 匹配（如有）**且** `dimension_conditions` 全部匹配；无 `condition` 的规则仅依赖维度条件；无 `dimension_conditions` 的规则仅依赖关键词（向后兼容）

## 3. 排他规则覆盖新增场景

- [ ] 3.1 在 `EXCLUSIVE_RULES` 中新增 model-1/5 维度判别规则：`dimension_conditions={"scale":"地块","data_type":"评价结果","business_task":"质量等级评价"}` → model-5
- [ ] 3.2 在 `EXCLUSIVE_RULES` 中新增 model-1/5 维度判别规则：`dimension_conditions={"scale":"地块","business_task":"障碍诊断"}` → model-1
- [ ] 3.3 在 `EXCLUSIVE_RULES` 中新增 model-2/3 维度判别规则：`dimension_conditions={"data_type":"处方用量","business_task":"酸化改良"}` → model-2
- [ ] 3.4 在 `EXCLUSIVE_RULES` 中新增 model-2/3 维度判别规则：`dimension_conditions={"data_type":"处方用量","business_task":"有机质培肥"}` → model-3
- [ ] 3.5 确认现有纯关键词规则（无 dimension_conditions）保持向后兼容行为不变

## 4. 测试验证

- [ ] 4.1 在 `tests/test_exclusive_rules.py` 中新增维度判别测试：地块级质量等级评价 → model-5、地块级障碍诊断 → model-1、酸化调理剂用量 → model-2、有机肥施用量 → model-3
- [ ] 4.2 在 `tests/test_exclusive_rules.py` 中新增维度冲突降级测试：五维特征命中多条指向不同模型的规则 → boundary_pending
- [ ] 4.3 在 `tests/test_exclusive_rules.py` 中新增维度缺失回退测试：无 scale/data_type 时回退到 question_type 关键词路由
- [ ] 4.4 在 `tests/test_question_type_keywords.py` 中新增业务任务和预期输出提取测试
- [ ] 4.5 在 `tests/test_question_type_keywords.py` 中新增向后兼容测试：无 context 时行为与 v1 一致
- [ ] 4.6 运行 `python -m pytest tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_multi_agent.py -q`，全部通过为验收标准
