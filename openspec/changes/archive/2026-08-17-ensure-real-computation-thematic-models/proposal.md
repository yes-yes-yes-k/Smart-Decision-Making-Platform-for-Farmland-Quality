## Why

当前 5 个专题模型 agent 中，model-3 的 `execute()` 方法始终返回硬编码 mock 数据（`MOCK_INDICATOR_GRADES`），未接入真实诊断路径；model-4 的 `execute()` 虽然调用了真实 `model_4_execution()`，但用 `MockDataLoader.mark_simulated()` 在顶层添加了误导性的 `simulated: True` 标记。model-1/2 虽有真实计算路径，但导入失败时静默回退到 mock，未明确标注降级状态。这导致 API 返回的数据可信度不确定，下游消费者无法区分真实计算结果与模拟数据。

## What Changes

- **model-3 (problem_agent.py)**: 重写 `execute()` 方法，当 `FARMland_DIAGNOSIS_AVAILABLE=True` 且提供 `parcel_id` 时调用 `query_parcel()` 获取真实诊断结果；不可用时明确返回降级状态而非伪装成真实数据
- **model-4 (acidification_agent.py)**: 移除 `execute()` 中的 `MockDataLoader.mark_simulated()` 包装，改用 `simulated: False` 标记（因 `model_4_execution()` 已是真实计算）
- **model-1 (stability_agent.py)**: 在 mock 回退路径中添加明确的 `degraded: True` 标记，区分真实计算与降级模式
- **model-2 (grade_agent.py)**: 在 mock 回退路径中添加明确的 `degraded: True` 标记，区分真实计算与降级模式
- **model-5 (organic_matter_agent.py)**: 无需修改（已正确使用 `model_5_execution()` 并有明确的 rule fallback 标记）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `professional-model-agents`: 专题模型 agent 的执行行为变更 — model-3 execute() 接入真实诊断路径；model-4 移除误导性 simulated 标记；model-1/2 降级路径明确标注

## Impact

- **代码**: `framework/agents/specialized/stability_agent.py`, `grade_agent.py`, `problem_agent.py`, `acidification_agent.py`
- **API**: 不改变 API 接口，但响应体中 `simulated`/`degraded` 字段语义更准确
- **依赖**: 依赖 `ai_culti_demo.farmland_stability`、`ai_culti_demo.farmland_grade_eval`、`ai_culti_demo.farmland_diagnosis` 包的导入可用性
- **测试**: 需更新相关 agent 的单元测试，验证真实路径和降级路径的行为
