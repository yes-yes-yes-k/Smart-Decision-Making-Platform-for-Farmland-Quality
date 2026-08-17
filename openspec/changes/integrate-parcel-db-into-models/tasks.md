## 1. 基础设施

- [x] 1.1 新增 `framework/domain/data/parcel_data_accessor.py`，实现 `ParcelDataAccessor` 类：`get_parcel_indicators(parcel_id)` 方法查询 `parcel_info` 表 `soil_indicators` JSON 字段，返回 dict 或 None；DB 异常时返回 None 并记录 WARNING
- [x] 1.2 在 `framework/agents/base.py` 的 `BaseAgent` 增加 `_persist_result(agent_id, parcel_id, inputs, outputs, status)` 方法：同一事务内先写 `model_execution_log` 获取 `execution_id`，再写结果表；失败时记录 ERROR 但不抛异常
- [x] 1.3 在 `BaseAgent` 增加 `_build_result_record(execution_id, outputs)` 钩子方法（默认返回 None），子类 override 返回对应 ORM 结果表记录实例

## 2. Model-1 StabilityRiskAgent 改造

- [ ] 2.1 将 `stability_risk_agent.py` 的 `_collect_inputs` 重构为 DB 优先：先调 `ParcelDataAccessor.get_parcel_indicators(parcel_id)`，命中时用 DB 指标；未命中时降级到 `MOCK_COUNTIES` 并记录 WARNING
- [ ] 2.2 在 `StabilityRiskAgent` override `_get_result_model_class()` 返回 `StabilityRiskResult`
- [ ] 2.3 在 `execute()` 成功路径调用 `_persist_result()`，返回结果中增加 `data_source` 和 `persisted` 标识

## 3. Model-2 FarmlandGradeAgent 改造

- [ ] 3.1 将 `grade_agent.py` 的 `_collect_inputs` 重构为 DB 优先：先查 `parcel_info`，未命中时降级到 CSV `run_grade_evaluation` 并记录 WARNING
- [ ] 3.2 在 `FarmlandGradeAgent`（或 `FarmlandGradeObstacleAgent`）override `_get_result_model_class()` 返回 `QualityGradeResult`
- [ ] 3.3 在 `execute()` 成功路径调用 `_persist_result()`

## 4. Model-3 ProblemIdentificationAgent 改造

- [ ] 4.1 将 `problem_agent.py` 的 `_collect_inputs` 重构为 DB 优先：先查 `parcel_info`，未命中时降级到 SQLite `query_parcel` 并记录 WARNING
- [ ] 4.2 在 `ProblemIdentificationAgent`（或 `ObstacleDiagnosisAgent`）override `_get_result_model_class()` 返回 `ObstacleDiagnosisResult`
- [ ] 4.3 在 `execute()` 成功路径调用 `_persist_result()`

## 5. Model-4 AcidificationRemediationAgent 改造

- [ ] 5.1 将 `acidification_agent.py` 和 `model_4.py` 的数据获取重构为 DB 优先：先查 `parcel_info` 的 `soil_ph`/`exchangeable_hydrogen` 等字段，未命中时降级到 SQLite `_query_sjd_by_parcel_id` 并记录 WARNING
- [ ] 5.2 在 `AcidificationRemediationAgent` override `_get_result_model_class()` 返回 `AcidificationRemediationResult`
- [ ] 5.3 在 `execute()` 成功路径调用 `_persist_result()`

## 6. Model-5 OrganicMatterAgent 改造

- [ ] 6.1 将 `organic_matter_agent.py` 的 `_collect_inputs` 增加 DB 优先路径：先查 `parcel_info` 获取 `soil_ph`/`organic_matter`/`available_potassium` 等字段，未命中时降级到用户传入参数并记录 WARNING
- [ ] 6.2 在 `OrganicMatterAgent` override `_get_result_model_class()` 返回 `OrganicMatterResult`
- [ ] 6.3 在 `execute()` 成功路径调用 `_persist_result()`（注意 Model-5 为县级分析，`parcel_id` 可为空）

## 7. 测试

- [ ] 7.1 新增 `tests/test_parcel_data_accessor.py`：测试 DB 命中、DB 未命中、DB 异常三种场景
- [ ] 7.2 新增 `tests/test_base_agent_persist.py`：测试 `_persist_result()` 成功写入 execution_log + 结果表、写入失败时不阻断返回、事务 rollback 一致性
- [ ] 7.3 更新 5 个 Agent 的现有测试：验证 DB 优先 + fallback 降级路径、`data_source` 标识、`persisted` 标识
- [ ] 7.4 运行完整测试套件验证无回归
