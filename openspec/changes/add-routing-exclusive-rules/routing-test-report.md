# 路由测试集扩充报告

- model-3/7 易混淆对：正例 ≥20（现状评价→model-3；质量等级评价→model-7），反例 ≥20。
- model-2/7 易混淆对：正例 ≥20（潜力→model-2；质量等级评价→model-7），反例 ≥20。
- model-4/6 易混淆对：正例 ≥20（酸化调理剂→model-4；有机质投入量→model-6），反例 ≥20。
- 排他规则与「模型边界待确认」降级测试：`tests/test_exclusive_rules.py`。
- 全量回归：`python -m pytest tests/` 通过（约 470 个测试）。