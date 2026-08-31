---
role: technical-design
status: approved
---

# 测试套件保守清理设计

## 1. 目标

在不降低业务行为、公开接口、兼容性和规范一致性保障的前提下，删除已经明确无断言、只服务于已完成迁移或与其他测试重复的 pytest 用例。生产代码不在本次变更范围内。

当前基线为 791 个用例：766 通过、22 跳过、3 失败。3 个失败均来自 `test_stability_and_grade_integration.py` 中对同一稳定性模型公开入口的重复验证，失败原因是测试缺少 Flask application context，导致持久化失败后响应降级。

## 2. 删除范围

删除以下 8 个测试：

1. `tests/test_multi_agent.py::test_question_type_identification`
   - 仅调用函数并打印结果，没有断言，无法阻止回归。
2. `tests/test_agent_manager.py::test_should_execute_agent_method_removed`
3. `tests/test_agent_manager.py::test_fertility_keywords_constant_removed`
4. `tests/test_agent_manager.py::test_grade_keywords_constant_removed`
5. `tests/test_question_type_router.py::test_role_router_removed`
   - 以上 4 个用例只断言迁移前的私有符号已经不存在；当前路由行为已有正向测试覆盖。
6. `tests/test_question_type_keywords.py::test_confusing_pair_positive_and_negative_batches_ge_20`
   - 与紧邻的 `test_all_confusing_pair_batches_size_ge_20` 检查完全相同的四组测试数据规模。
7. `tests/test_stability_and_grade_integration.py::TestCoreEngineDispatch::test_dispatch_stability_with_parcel_id`
8. `tests/test_stability_and_grade_integration.py::TestEndToEndIntegration::test_e2e_stability_full_pipeline`
   - 两者与 `TestStabilityOnlineQuery::test_normal_query_returns_ok` 使用相同入口、相同 mock 数据和相同核心断言；保留后者作为唯一的稳定性模型成功路径测试。

删除测试后，同步移除相关 `if __name__ == "__main__"` 手工调用，避免引用不存在的函数。

## 3. 保留与修正

保留 `TestStabilityOnlineQuery::test_normal_query_returns_ok`，并复用文件现有的 `flask_app_context` fixture。该测试继续覆盖：

- `run_thematic_model` 对稳定性模型的公开调度入口；
- 成功状态和 `real_model` 可靠性等级；
- 标准模型标识；
- `stability_modules` 分析结果。

保留以下测试类别：

- OpenSpec 文本同步测试；
- 公开 API 和兼容性契约；
- PostgreSQL 等外部条件不足时的条件跳过测试；
- 通过辅助函数内部断言的批量路由测试；
- 业务边界、失败路径和数据完整性测试。

## 4. 验证

1. 对涉及的 5 个测试文件运行定向 pytest。
2. 运行完整 `tests/` 测试套件。
3. 预期收集 783 个用例，除环境条件跳过外全部通过。
4. 检查 `git diff` 和 `git status`，确认没有生产代码改动，也没有包含用户原有的两份文档改动。

## 5. 风险控制

- 不以“当前失败”为删除理由；失败的重复测试只有在保留一个等价成功路径后才删除。
- 不删除仅因 PostgreSQL、GeoPandas 或其他环境条件而跳过的测试。
- 不删除规范同步和兼容性测试，即使其断言偏结构化。
- 若完整测试暴露新的失败，先判断是否由本次清理引起，不通过继续删除测试来获得绿色结果。
