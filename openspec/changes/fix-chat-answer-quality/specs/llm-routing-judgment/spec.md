## ADDED Requirements

### Requirement: 稳定性复合意图路由保底

当用户问题命中稳定性/退化风险强先验关键词（「稳不稳」「稳定吗」「退化风险」「掉级」「等级稳定」）时，系统 SHALL 无论 LLM 初判结果如何，最终路由 SHALL 至少包含 Model-1（稳定性与退化风险评价）；LLM 初判不得将此类复合意图降级为单一质量等级（Type-2）或其他类型。关键词保底 SHALL 在 LLM 初判之后、排他规则之前生效。

#### Scenario: 「稳不稳 + 退化风险」复合提问路由到 Model-1

- **WHEN** 问题同时包含「质量等级」与「稳不稳/退化风险」且 LLM 初判结果为 Type-2
- **THEN** 路由保底 SHALL 将最终类型改为稳定性类（Type-1）
- **AND** 执行列表 SHALL 包含 Model-1（联动 Model-2 字段直查）
- **AND** 回答 SHALL 输出稳定性/退化风险结论（历史充足时）

#### Scenario: LLM 初判不覆盖强先验关键词

- **WHEN** LLM 初判返回 Type-2 且问题命中「稳不稳/退化风险/等级稳定」关键词
- **THEN** 关键词保底 SHALL 覆盖 LLM 初判
- **AND** `router_method` 观测 SHALL 记录为 `keyword_override_lm`（可追溯）
