---
comet_change: ensure-real-computation-thematic-models
role: technical-design
canonical_spec: openspec
---

# Design Doc: 确保专题模型使用真实计算逻辑

## 1. 背景与目标

### 1.1 问题

当前 5 个专题模型 agent 的 `execute()` 方法存在真实计算与 mock 数据混淆：

- **model-3** (`problem_agent.py`): `execute()` 始终返回硬编码 `MOCK_INDICATOR_GRADES`，未接入真实诊断路径
- **model-4** (`acidification_agent.py`): `execute()` 调用真实 `model_4_execution()` 但用 `MockDataLoader.mark_simulated()` 包装，顶层 `simulated: True` 误导
- **model-1** (`stability_agent.py`): 导入失败时静默回退到硬编码 mock 数据
- **model-2** (`grade_agent.py`): 同上，静默回退到 mock
- **model-5** (`organic_matter_agent.py`): 已正确实现（真实 `model_5_execution()` + rule fallback）

### 1.2 目标

- 所有 agent 的 `execute()` 方法优先使用真实计算逻辑
- 真实计算不可用时返回**统一降级响应**，不返回 mock 数据
- `simulated`/`degraded` 字段语义一致：真实计算 `False`/不设置，降级 `True`

### 1.3 非目标

- 不修改 model-5 的 `model_5_execution()` 本身
- 不修改 `ai_culti_demo` 包
- 不修改 API 接口签名
- 不修改数据库 schema

## 2. 统一降级响应结构

所有 agent 在真实计算不可用时返回此结构：

```python
DEGRADED_RESPONSE = {
    "status": "degraded",
    "degraded": True,
    "reason": "model_unavailable" | "missing_input" | "import_failed",
    "agent_id": "<agent_id>",
    "model_id": "<model_id>",
    "message": "<人类可读说明>"
}
```

### reason 枚举

| reason | 含义 | 触发条件 |
|--------|------|----------|
| `model_unavailable` | 模型包导入失败 | `STABILITY_MODEL_AVAILABLE=False` 等 |
| `missing_input` | 缺少必要输入 | 无 `parcel_id` / `parcel_code` |
| `import_failed` | 真实调用失败 | `query_parcel()` / `run_grade_evaluation()` 抛异常 |

## 3. 各 Agent 改动详情

### 3.1 model-1 StabilityRiskAgent

**文件**: `framework/agents/specialized/stability_agent.py`

**改动**:
1. 移除 L42-66 的硬编码 mock 数据（risk_levels, risk_types, stability_score 等）
2. 当 `STABILITY_MODEL_AVAILABLE=False` → 返回 `DEGRADED_RESPONSE`，reason=`model_unavailable`
3. 当 `parcel_id` 缺失 → 返回 `DEGRADED_RESPONSE`，reason=`missing_input`
4. 当 `StabilityStorage.get_result()` 返回 None 或抛异常 → 返回 `DEGRADED_RESPONSE`，reason=`import_failed`
5. 真实结果返回 `simulated: False`

**移除内容**:
- `risk_levels = ["低风险", "中风险", "高风险", "极高风险"]`
- `risk_types = ["掉级风险", "关键因子退化", "退化集聚", "持续低质"]`
- 9 个 modules 的硬编码分数
- `MockDataLoader.mark_simulated()` 包装

### 3.2 model-2 FarmlandGradeAgent

**文件**: `framework/agents/specialized/grade_agent.py`

**改动**:
1. 移除 L42+ 的硬编码 mock 数据（indicators, obstacle_degree 等）
2. 当 `GRADE_EVAL_AVAILABLE=False` → 返回 `DEGRADED_RESPONSE`，reason=`model_unavailable`
3. 当 `parcel_code` 缺失 → 返回 `DEGRADED_RESPONSE`，reason=`missing_input`
4. 当 `run_grade_evaluation()` 失败 → 返回 `DEGRADED_RESPONSE`，reason=`import_failed`
5. 真实结果返回 `simulated: False`

**移除内容**:
- 硬编码 indicators 列表（pH, 有机质, 有效磷, 速效钾）
- 硬编码 obstacle_degree 列表
- `MockDataLoader.mark_simulated()` 包装

### 3.3 model-3 ProblemIdentificationAgent

**文件**: `framework/agents/specialized/problem_agent.py`

**改动**:
1. 重写 `execute()` 方法：
   - 检查 `FARMland_DIAGNOSIS_AVAILABLE` 和 `parcel_id`
   - 可用时调用 `self._get_real_diagnosis(task)` 复用已有方法
   - 不可用时返回 `DEGRADED_RESPONSE`，reason 对应
2. 移除 `MOCK_INDICATOR_GRADES` 字典（L16-28）
3. 移除 `_severity_score()` 函数（L31-37）— 仅用于 mock 数据
4. 移除 `execute()` 中的 `MockDataLoader.mark_simulated()` 包装
5. 真实结果返回 `simulated: False`

**关键决策**: 复用 `_get_real_diagnosis()` 方法（已调用 `query_parcel()`），避免重复代码，保持 `execute()` 与 `answer_question()` 一致。

### 3.4 model-4 AcidificationRemediationAgent

**文件**: `framework/agents/specialized/acidification_agent.py`

**改动**:
1. 移除 `execute()` 中的 `MockDataLoader.mark_simulated()` 包装（L38）
2. 直接返回字典，设置 `simulated: False`
3. `model_4_execution()` 始终是真实计算，无降级路径

**移除内容**:
- `MockDataLoader.mark_simulated()` 在 execute() 中的调用
- 顶层 `simulated: True` 标记

### 3.5 model-5 OrganicMatterAgent

**文件**: `framework/agents/specialized/organic_matter_agent.py`

**改动**: 无（已正确实现）
- `model_5_execution()` 为真实 ML 计算
- rule fallback 已标注 `simulated: True`
- 补充 `degraded: True` 到 rule fallback 路径以保持一致性

## 4. 数据流

### 4.1 真实计算路径

```
chat.py → nodes.py → manager.py → _analysis_payload → BaseAgent.analyze() → execute()
  model-1: StabilityStorage.get_result(parcel_id)
  model-2: run_grade_evaluation(parcel_code)
  model-3: _get_real_diagnosis() → query_parcel(parcel_id)
  model-4: model_4_execution()
  model-5: model_5_execution()
→ 返回 {status: "ok", simulated: False, result: {...}}
```

### 4.2 降级路径

```
execute() 检查条件 → 不可用 → 返回 DEGRADED_RESPONSE
  {status: "degraded", degraded: True, reason: "...", message: "..."}
```

## 5. 测试策略

### 5.1 单元测试

| 测试 | 验证点 |
|------|--------|
| model-1 真实路径 | `STABILITY_MODEL_AVAILABLE=True` + `parcel_id` → `simulated: False` |
| model-1 降级 | `STABILITY_MODEL_AVAILABLE=False` → `degraded: True` |
| model-2 真实路径 | `GRADE_EVAL_AVAILABLE=True` + `parcel_code` → `simulated: False` |
| model-2 降级 | 缺少 `parcel_code` → `degraded: True` |
| model-3 真实路径 | `FARMland_DIAGNOSIS_AVAILABLE=True` + `parcel_id` → `simulated: False` |
| model-3 降级 | 无 `parcel_id` → `degraded: True` |
| model-4 真实路径 | `model_4_execution()` → `simulated: False` |
| model-4 无 mark_simulated | 顶层无 `simulated: True` |
| model-5 rule fallback | 缺少特征 → `degraded: True` |

### 5.2 回归测试

- 运行全部 agent 测试确认无回归
- 验证 `answer_question()` 与 `execute()` 行为一致

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 移除 mock 数据是破坏性变更 | 统一降级响应让下游消费者可处理 |
| `ai_culti_demo` 导入失败 | 降级响应明确告知原因 |
| 现有测试期望 mock 数据 | 更新测试以验证降级响应 |
| model-3 `execute()` 变更影响 `answer_question()` | 复用 `_get_real_diagnosis()` 保持一致 |

## 7. Spec Patch

需更新 delta spec `specs/professional-model-agents/spec.md`：
- 将"降级模式标注"场景改为"统一降级响应"场景
- 明确降级响应的 `status`、`degraded`、`reason`、`message` 字段
