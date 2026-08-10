## Why

五维路由（业务任务、分析尺度、数据类型、预期输出、模型依赖）在 v1 中仅为「关键词排他规则 + 五维元数据声明」：`_extract_five_dim_context` 提取了分析尺度和数据类型，`ProfessionalCapability` 声明了 `analysis_scale`/`data_type` 字段，但 `apply_exclusive_rules` 的 `context` 参数完全未参与路由判定。spec 要求"五维路由判定 SHALL 逐级缩小候选 Agent 集合"，当前实现不满足该要求。本次变更让五维特征真正参与路由判定，完善 v1 版本。

## What Changes

- 新增**业务任务关键词表**，从问题文本独立提取业务任务标签（障碍诊断/酸化改良/有机质培肥/稳定性评价/质量等级评价）
- 新增**预期输出关键词表**，从问题文本独立提取预期输出标签（评价结果/处方用量/诊断报告）
- 扩展 `ExclusiveRule` 数据结构，支持以分析尺度/数据类型/业务任务/预期输出作为判别条件（当前仅支持问题文本关键词子串匹配）
- 更新 `apply_exclusive_rules`，让 `context` 参数（含 scale/data_type）真正参与路由判定
- 更新 `_extract_five_dim_context`，增加业务任务和预期输出的提取
- 扩展排他规则覆盖两组新增判别场景：地块评价 vs 地块诊断（model-1/5）、处方用量区分（model-2/3）
- 保持 `boundary_pending` 降级机制：维度无法消解歧义时仍返回降级状态

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `routing-exclusive-rules`: 更新「五维路由特征判定」需求，从"元数据声明与上下文预留"升级为"五维特征全量参与判定"；扩展排他规则判别条件支持分析尺度/数据类型/业务任务/预期输出维度

## Impact

- **代码**：`framework/agents/exclusive_rules.py`（扩展规则结构与判定逻辑）、`framework/agents/routing.py`（维度提取与集成）、`framework/agents/nodes.py`（`_extract_five_dim_context` 扩展）、`framework/agents/capabilities.py`（维度字段确认）
- **测试**：`tests/test_exclusive_rules.py`（新增维度判别测试）、`tests/test_question_type_keywords.py`（新增五维路由场景测试）
- **API**：不修改 API 响应结构，`routing_status`/`boundary_pending` 机制不变
