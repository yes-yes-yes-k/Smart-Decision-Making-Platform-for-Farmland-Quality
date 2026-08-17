---
change: ensure-real-computation-thematic-models
design-doc: docs/superpowers/specs/2026-08-16-ensure-real-computation-design.md
base-ref: ecfc2e8a87314aeae19af21f1f7201b3c094b8e6
---

# 实施计划：确保专题模型使用真实计算逻辑

## 参考文档

- Design Doc: `docs/superpowers/specs/2026-08-16-ensure-real-computation-design.md`
- Delta Spec: `openspec/changes/ensure-real-computation-thematic-models/specs/professional-model-agents/spec.md`
- Tasks: `openspec/changes/ensure-real-computation-thematic-models/tasks.md`

## 统一降级响应结构

```python
def _degraded_response(agent_id, model_id, reason, message):
    return {
        "status": "degraded",
        "degraded": True,
        "reason": reason,
        "agent_id": agent_id,
        "model_id": model_id,
        "message": message,
    }
```

## Step 1：model-3 接入真实诊断路径

- [ ] 1.1 重写 `framework/agents/specialized/problem_agent.py` 的 `execute()` 方法：
  - 检查 `FARMland_DIAGNOSIS_AVAILABLE` 和 `parcel_id`
  - 可用时调用 `self._get_real_diagnosis(task)` 复用已有方法
  - 不可用时返回 `_degraded_response("model-3", "obstacle-diagnosis", reason, message)`
- [ ] 1.2 移除 `MOCK_INDICATOR_GRADES` 字典（L16-28）和 `_severity_score()` 函数（L31-37）
- [ ] 1.3 移除 `execute()` 中的 `MockDataLoader.mark_simulated()` 包装
- [ ] 1.4 验证真实结果返回 `simulated: False`

## Step 2：model-4 移除误导性 simulated 标记

- [ ] 2.1 修改 `framework/agents/specialized/acidification_agent.py` 的 `execute()` 方法：
  - 移除 `MockDataLoader.mark_simulated()` 包装（L38）
  - 直接返回字典，设置 `simulated: False`
- [ ] 2.2 验证 `answer_question()` 中的 `simulated: False` 与 `execute()` 一致

## Step 3：model-1 移除 mock 并添加统一降级

- [ ] 3.1 修改 `framework/agents/specialized/stability_agent.py` 的 `execute()` 方法：
  - 移除 L42-66 的硬编码 mock 数据
  - `STABILITY_MODEL_AVAILABLE=False` → 返回降级响应，reason=`model_unavailable`
  - 无 `parcel_id` → 返回降级响应，reason=`missing_input`
  - `get_result()` 返回 None/异常 → 返回降级响应，reason=`import_failed`
- [ ] 3.2 验证真实结果返回 `simulated: False`

## Step 4：model-2 移除 mock 并添加统一降级

- [ ] 4.1 修改 `framework/agents/specialized/grade_agent.py` 的 `execute()` 方法：
  - 移除 L42+ 的硬编码 mock 数据
  - `GRADE_EVAL_AVAILABLE=False` → 返回降级响应，reason=`model_unavailable`
  - 无 `parcel_code` → 返回降级响应，reason=`missing_input`
  - `run_grade_evaluation()` 失败 → 返回降级响应，reason=`import_failed`
- [ ] 4.2 验证真实结果返回 `simulated: False`

## Step 5：model-5 添加 degraded 标记

- [ ] 5.1 修改 `framework/agents/specialized/organic_matter_agent.py` 的 `_execute_rule_fallback()`：
  - 添加 `degraded: True` 到返回结构
- [ ] 5.2 验证 `model_5_execution()` 真实路径返回 `simulated: False`

## Step 6：测试更新

- [ ] 6.1 更新 model-3 测试：验证 `execute()` 真实路径调用 `_get_real_diagnosis()`，降级路径返回统一降级响应
- [ ] 6.2 更新 model-4 测试：验证 `execute()` 返回 `simulated: False`，无 `mark_simulated()` 包装
- [ ] 6.3 更新 model-1/2 测试：验证降级路径返回统一降级响应，无 mock 数据
- [ ] 6.4 运行全部 agent 测试确认无回归
