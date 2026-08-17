## Context

当前 5 个专题模型 agent 的 `execute()` 方法存在真实计算与 mock 数据混淆的问题。model-3 始终返回硬编码 mock，model-4 用 `MockDataLoader.mark_simulated()` 包装真实结果，model-1/2 在导入失败时静默回退到 mock。BaseAgent.analyze() 流程中 execute() 和 answer_question() 都会被调用，两者对真实/mock 的处理需要一致。

## Goals / Non-Goals

**Goals:**
- model-3 execute() 接入 `query_parcel()` 真实诊断路径
- model-4 execute() 移除误导性 `simulated: True` 包装
- model-1/2 mock 回退路径添加 `degraded: True` 标记
- 所有 agent 的 `simulated`/`degraded` 字段语义一致：真实计算=False/不设置，降级=True

**Non-Goals:**
- 不修改 model-5（已正确实现）
- 不修改 API 接口签名
- 不修改数据库 schema
- 不修改 `ai_culti_demo` 包本身
- 不修改 BaseAgent 基类

## Decisions

### D1: model-3 execute() 直接调用 query_parcel()

**选择**: 在 `ProblemIdentificationAgent.execute()` 中添加 `FARMland_DIAGNOSIS_AVAILABLE` 检查，当 True 且有 `parcel_id` 时调用 `query_parcel(parcel_id, db_path)`。

**理由**: `answer_question()` 已有 `_get_real_diagnosis()` 调用 `query_parcel()` 的逻辑，execute() 应保持一致。现有 `MOCK_INDICATOR_GRADES` 保留为降级路径数据源。

**替代方案**: 将 execute() 和 answer_question() 合并为统一入口 — 否决，因为基类 analyze() 依赖两者分离。

### D2: model-4 移除 mark_simulated() 包装

**选择**: 在 `AcidificationRemediationAgent.execute()` 中将 `MockDataLoader.mark_simulated({...})` 改为直接返回字典，设置 `simulated: False`。

**理由**: `model_4_execution()` 是真实计算，不应在顶层标记 `simulated: True`。`answer_question()` 已正确设置 `simulated: False`。

### D3: model-1/2 降级标记用 `degraded` 而非 `simulated`

**选择**: 在 model-1/2 的 mock 回退路径中添加 `degraded: True`，保留 `simulated: True` 标记。

**理由**: `simulated` 表示"数据是模拟的"，`degraded` 表示"因条件不足而降级"。两者语义不同，同时保留可让下游消费者更精确判断。model-4/5 的真实计算路径设置 `simulated: False`，降级路径设置 `degraded: True`。

### D4: 不修改 MockDataLoader.mark_simulated() 本身

**选择**: 保留 `mark_simulated()` 工具方法不变，仅在 agent 调用层调整。

**理由**: `mark_simulated()` 是通用工具，其他代码可能依赖其行为。修改调用方更安全。

## Risks / Trade-offs

- [ai_culti_demo 导入失败] → 降级路径用 `degraded: True` 标记，下游可识别
- [现有测试期望 `simulated: True`] → 需更新 test_stability_agent.py、test_grade_agent.py 等测试文件
- [model-3 execute() 行为变更影响 answer_question()] → execute() 返回真实结果后，answer_question() 的 `_get_real_diagnosis()` 会获取相同数据，不会冲突
- [query_parcel() 可能抛异常] → execute() 内 try/except 捕获，异常时返回降级结果
