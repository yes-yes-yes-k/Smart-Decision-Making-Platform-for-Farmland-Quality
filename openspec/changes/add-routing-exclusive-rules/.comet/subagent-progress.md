# Comet Subagent Progress — add-routing-exclusive-rules

- Change: add-routing-exclusive-rules
- Phase: build
- review_mode: standard
- tdd_mode: tdd
- build_mode: subagent-driven-development
- Branch: feature/20260806/add-routing-exclusive-rules
- Base-ref: 574b1a8a86fba188e6c875072a75fa4130a1ad82

## Task 1: 五维路由特征扩展
- 状态: completed (review APPROVED)
- 实现提交: 713caf8
- 变更文件: capabilities.py / routing.py(新) / exclusive_rules.py(脚手架,新) / nodes.py / test_question_type_keywords.py
- RED/GREEN 证据: RED 2 失败(字段缺失+routing 导入失败); GREEN test_question_type_keywords 35 passed + 回归 82 passed
- 风险信号: 审查发现 Minor#1 —— test_keyword_match_priority_over_vector 补丁目标 nodes._identify_question_type_vector 迁移后失效(与 test_unrelated_question_returns_zero 同类), 需 Task 4 一并改为 routing.*
- 审查轮次: 1 (PASS)

## Task 2: 排他规则配置
- 状态: completed (review APPROVED)
- 实现提交: 2ac010c
- 变更文件: exclusive_rules.py(脚手架→完整实现) / tests/test_exclusive_rules.py(新)
- RED/GREEN 证据: RED 8 failed; GREEN exclusive_rules 9 passed + 回归 44 passed
- 风险信号: 审查确认必要偏差 —— model_id_to_question_type 改用 CAPABILITY_BY_AGENT_ID(brief 用 CAPABILITY_BY_MODEL_ID 会因 model-N 存于 agent_id 字段而返回 None)
- 审查轮次: 1 (PASS)

## Task 3: 路由集成与 API 响应
- 状态: completed (review APPROVED)
- 实现提交: 5915fc5
- 变更文件: state.py / nodes.py / orchestrator.py / chat.py / tests/test_exclusive_rules.py
- RED/GREEN 证据: RED 3 failed; GREEN exclusive_rules 19 passed + 回归 54 passed
- 风险信号: 无 Critical/Important; else 专业模型分支零漂移
- 审查轮次: 1 (PASS)

## Task 4: 路由测试集扩充
- 状态: completed (review APPROVED)
- 实现提交: 804f775 (+ 2733f27 文档修正)
- 变更文件: tests/test_question_type_keywords.py / routing-test-report.md(新)
- RED/GREEN 证据: 路由单文件 44 passed; 路由相关三文件 63 passed; 全量回归 460 passed/11 skipped/21 failed(均为既有无关问题)
- 风险信号: 用户批准修正 MODEL4_STEMS(去除用量措辞避免 boundary_pending); 修正两处失效补丁目标 nodes.*→routing.*; Minor#报告回归数据表述已修正
- 审查轮次: 1 (PASS)

## Final Review
- 状态: completed (APPROVED_WITH_MINORS)
- 终审提交: 62fb52d (设计文档 v1 口径说明) / 63d7f1d (移除 Any 导入) / 2733f27 (报告数据修正)
- 终审结论: 路由套件 63 passed; 全量回归 460/11/21(既有无关失败)
- Important#五维 context 未参与判定 → 用户批准「接受范围并如实文档化」，已写入设计文档「实现范围说明(v1 口径)」
- Minor#Any 未使用导入 → 已清理; #排他规则双重应用(冗余无害) → 接受; #缺换行(格式) → 接受