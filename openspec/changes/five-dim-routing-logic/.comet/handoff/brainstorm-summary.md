# Brainstorm Summary

- Change: five-dim-routing-logic
- Date: 2026-08-07

## 确认的技术方案

扩展 `ExclusiveRule` 结构新增 `dimension_conditions: Dict[str, str]` 字段，支持以分析尺度/数据类型/业务任务/预期输出作为判别条件。规则匹配采用 AND 逻辑：`condition`（关键词）和 `dimension_conditions`（维度）均需匹配（如有声明）。`condition=None` 的规则仅依赖维度条件；`dimension_conditions={}` 的规则仅依赖关键词（v1 向后兼容）。

新增 `BUSINESS_TASK_KEYWORDS` 和 `EXPECTED_OUTPUT_KEYWORDS` 关键词表，在 `_extract_five_dim_context` 中从问题文本提取业务任务和预期输出标签，写入 context。

新增 4 条维度驱动排他规则覆盖 model-1/5（地块评价 vs 地块诊断）和 model-2/3（处方用量区分）场景。

## 关键取舍与风险

- **维度提取精度**：关键词表覆盖度有限，可能漏判或误判。缓解：测试集覆盖正例反例 ≥20 条/组
- **规则冲突复杂度**：新增维度条件后规则间可能产生新的冲突路径。缓解：保持 `matched_targets > 1 → boundary_pending` 的冲突处理逻辑
- **向后兼容**：现有纯关键词规则需保持行为不变。缓解：无 `dimension_conditions` 的规则仅依赖关键词

## 测试策略

- 每组易混淆对（model-1/5、model-2/3）≥20 条正例 + 反例
- 维度冲突降级测试：多条规则命中不同 target → boundary_pending
- 维度缺失回退测试：无 scale/data_type → 回退到 question_type 关键词路由
- 无 context 向后兼容测试：context=None 时行为与 v1 一致
- 运行 `python -m pytest tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_multi_agent.py -q` 全部通过

## Spec Patch

无。delta spec 已包含全部验收场景，无需补充。
