# 路由测试集扩充报告

- model-3/7 易混淆对：正例 ≥20（现状评价→model-3；质量等级评价→model-7），反例 ≥20。
- model-2/7 易混淆对：正例 ≥20（潜力→model-2；质量等级评价→model-7），反例 ≥20。
- model-4/6 易混淆对：正例 ≥20（酸化调理剂→model-4；有机质投入量→model-6），反例 ≥20。
- 排他规则与「模型边界待确认」降级测试：`tests/test_exclusive_rules.py`。
- 路由相关三文件套件：`python -m pytest tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_multi_agent.py` 全部通过（63 项）。
- 全量回归：`python -m pytest tests/` 460 通过 / 11 跳过 / 21 失败。21 个失败均为既有问题、位于本次改动无关文件（酸化/质量/稳定性模型 `model_unavailable`、遗留 `StabilityStorage`/`run_grade_evaluation` patch 目标、rag 向量库、thematic_models），非本次路由改动引入。