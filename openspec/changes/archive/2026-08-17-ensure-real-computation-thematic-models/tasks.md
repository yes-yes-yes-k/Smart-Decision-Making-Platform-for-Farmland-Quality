## 1. model-3 execute() 接入真实诊断路径

- [x] 1.1 修改 `framework/agents/specialized/problem_agent.py` 的 `execute()` 方法：在 `FARMland_DIAGNOSIS_AVAILABLE=True` 且 `parcel_id` 存在时调用 `_get_real_diagnosis()` 复用已有方法获取真实诊断结果
- [x] 1.2 移除 `MOCK_INDICATOR_GRADES` 字典和 `_severity_score()` 函数，不可用时返回统一降级响应
- [x] 1.3 确保 `execute()` 的 try/except 捕获 `query_parcel()` 异常，异常时返回降级结果
- [x] 1.4 验证 `execute()` 返回的真实结果中 `simulated` 为 `False`

## 2. model-4 移除误导性 simulated 标记

- [x] 2.1 修改 `framework/agents/specialized/acidification_agent.py` 的 `execute()` 方法：移除 `MockDataLoader.mark_simulated()` 包装，直接返回字典
- [x] 2.2 在 `execute()` 返回结果中设置 `simulated: False`（因 `model_4_execution()` 是真实计算）
- [x] 2.3 验证 `answer_question()` 中的 `simulated: False` 标记与 `execute()` 一致

## 3. model-1 移除 mock 并添加统一降级

- [x] 3.1 修改 `framework/agents/specialized/stability_agent.py` 的 `execute()`：移除硬编码 mock 数据，不可用时返回统一降级响应
- [x] 3.2 验证真实路径（`StabilityStorage.get_result()`）返回结果中 `simulated` 为 `False`

## 4. model-2 移除 mock 并添加统一降级

- [x] 4.1 修改 `framework/agents/specialized/grade_agent.py` 的 `execute()`：移除硬编码 mock 数据，不可用时返回统一降级响应
- [x] 4.2 验证真实路径（`run_grade_evaluation()`）返回结果中 `simulated` 为 `False`

## 5. model-5 添加 degraded 标记

- [x] 5.1 修改 `framework/agents/specialized/organic_matter_agent.py` 的 `_execute_rule_fallback()`：添加 `degraded: True`

## 6. 测试更新

- [x] 6.1 运行全部 agent 测试确认无回归
