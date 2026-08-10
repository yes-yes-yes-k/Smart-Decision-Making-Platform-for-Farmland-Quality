# 检查报告：五维路由规则 + 模型编号变更

- 检查日期：2026-08-07
- 检查范围：
  1. 五维路由规则（change `five-dim-routing-logic`，v1.1 维度驱动排他规则）
  2. 模型编号变更（change `renumber-models-to-thematic`，model-1~7 → model-1~5）
- 检查方式：实际代码核对 + 主 spec 核对 + 归档变更产物核对 + 新鲜测试证据

---

## 一、检查结论总览

| 检查项 | 状态 |
|--------|------|
| 五维路由规则正确性 | ✅ 通过 |
| 模型编号变更一致性 | ⚠️ 部分通过（主 spec 存在陈旧引用） |
| 路由测试套件 | ✅ 通过（79 passed） |

---

## 二、五维路由规则检查

### 2.1 五维维度定义与提取

实现位于 [nodes.py](file:///d:/17417/Documents/agent_culti_demo/framework/agents/nodes.py#L43-L128) 的 `_extract_five_dim_context`：

| 维度 | 提取来源 | 现状 |
|------|---------|------|
| 业务任务 | `BUSINESS_TASK_KEYWORDS` 关键词表 | ✅ 独立关键词表，含 5 个任务标签 |
| 分析尺度 | `request.scale` 或问题文本推断 | ✅ 省/县/片区/地块，缺省回退"县" |
| 数据类型 | `indicators`/`parcel_id`/问题文本推断 | ✅ 指标数据/评价结果/处方用量 |
| 预期输出 | `EXPECTED_OUTPUT_KEYWORDS` 关键词表 | ✅ 评价结果/处方用量/诊断报告 |
| 模型依赖 | 排他规则 `pair` 声明 | ✅ 间接参与，无独立判定步骤 |

**关键修复已落地**：`BUSINESS_TASK_KEYWORDS["障碍诊断"]` 仅含 `("诊断","毛病","障碍")`，已移除裸词「问题/现状」，避免酸化/有机质/稳定性等跨域问题被误判为障碍诊断（此前代码审查发现的 Critical 回归）。

### 2.2 排他规则结构

[exclusive_rules.py](file:///d:/17417/Documents/agent_culti_demo/framework/agents/exclusive_rules.py#L23-L35) 的 `ExclusiveRule` 已扩展 `dimension_conditions: Dict[str, str]`，匹配为 AND 逻辑（`_rule_matches`）。

**规则清单核对（8 条）**：

| # | pair | 判别维度 | 条件类型 | 目标 | 状态 |
|---|------|---------|---------|------|------|
| 1 | model-1/5 | 业务任务 | v1 关键词：现状评价 | model-1 | ✅ |
| 2 | model-2/3 | 业务任务 | v1 关键词：酸化调理剂 | model-2 | ✅ |
| 3 | model-4 | 业务任务 | v1 关键词：稳定性风险 | model-4 | ✅ |
| 4 | model-5 | 预期输出 | v1 关键词：质量等级评价 | model-5 | ✅ |
| 5 | model-1/5 | 四维 | 维度：scale=地块+data_type=评价结果+business_task=质量等级评价+expected_output=评价结果 | model-5 | ✅ |
| 6 | model-1/5 | 三维 | 维度：scale=地块+business_task=障碍诊断+expected_output=诊断报告 | model-1 | ✅ |
| 7 | model-2/3 | 二维 | 维度：data_type=处方用量+business_task=酸化改良 | model-2 | ✅ |
| 8 | model-2/3 | 二维 | 维度：data_type=处方用量+business_task=有机质培肥 | model-3 | ✅ |

**要点**：
- 规则 1-4 为 v1 纯关键词规则（`dimension_conditions` 为空），保持向后兼容
- 规则 5-8 为 v1.1 维度驱动规则（`condition=None`，仅依赖维度）
- 规则 5/6 的 `expected_output` 收敛为新增增量，使预期输出维度真正参与 model-1/5 判别并收窄裸词跨域误触面

### 2.3 路由主流程

[identify_question_node](file:///d:/17417/Documents/agent_culti_demo/framework/agents/nodes.py#L84-L95)：
1. `_extract_five_dim_context` 提取四维 context
2. `identify_question_type` 基础 question_type 判定
3. `apply_exclusive_rules` 叠加排他规则（AND 逻辑）
4. 返回 `final_type` + `routing_status`

**降级机制**：`matched_targets > 1 → boundary_pending`（模型边界待确认）；`matched_targets == 0 →` 回退原 type。TYPE_0(RAG) 与未知类型不应用排他规则。✅

---

## 三、模型编号变更检查

### 3.1 目标映射（归档 change 决策）

change `renumber-models-to-thematic`（已归档，`openspec/changes/archive/2026-08-06-renumber-models-to-thematic/`）定义的模型编号映射：

| 新 agent_id | 专题模型 | model_id（不变） | 原 agent_id |
|------------|---------|-----------------|-------------|
| model-1 | 障碍诊断 | obstacle-diagnosis | model-3 |
| model-2 | 酸化改良 | acidification-remediation | model-4 |
| model-3 | 有机质提升 | organic-matter-improvement | model-5 |
| model-4 | 稳定性风险 | stability-risk-evaluation | model-1 |
| model-5 | 质量等级 | quality-grade-evaluation | model-7 |

### 3.2 实现核对（capabilities.py）

[capabilities.py](file:///d:/17417/Documents/agent_culti_demo/framework/agents/capabilities.py#L27-L58) 的 `PROFESSIONAL_CAPABILITIES` 现有 **5 个**正式模型，与目标映射完全一致：

| agent_id | model_id | question_type | 分析尺度 | 数据类型 |
|---------|----------|---------------|---------|---------|
| model-1 | obstacle-diagnosis | 1 | 地块 | 指标数据 |
| model-2 | acidification-remediation | 2 | 地块 | 处方用量 |
| model-3 | organic-matter-improvement | 3 | 县 | 处方用量 |
| model-4 | stability-risk-evaluation | 4 | 地块 | 评价结果 |
| model-5 | quality-grade-evaluation | 5 | 地块 | 评价结果 |

- ✅ 5 个模型编号一一对应专题模型
- ✅ 占位符 model-2（PotentialAssessmentAgent）和 model-6（FertilityMLAgent）已从注册表移除
- ✅ question_type 1-5 与新编号对齐

### 3.3 路由与排他规则编号一致性

- [exclusive_rules.py](file:///d:/17417/Documents/agent_culti_demo/framework/agents/exclusive_rules.py#L46-L90)：排他规则引用的 model-1/2/3/4/5 均存在于注册表，无悬空引用。✅
- [routing.py](file:///d:/17417/Documents/agent_culti_demo/framework/agents/routing.py#L18-L43)：关键词映射覆盖 type 1-5。✅
- `model_id_to_question_type` 通过 `CAPABILITY_BY_AGENT_ID` 反查，与注册表一致。✅

---

## 四、发现的残留问题

### ⚠️ 4.1 主 spec 存在陈旧 model-6/model-7 引用

当前主 spec（`openspec/specs/`）中仍有旧编号引用，与模型编号变更后的现状不一致：

| 文件 | 行 | 陈旧内容 |
|------|-----|---------|
| [multi-agent-orchestrator/spec.md](file:///d:/17417/Documents/agent_culti_demo/openspec/specs/multi-agent-orchestrator/spec.md#L88-L123) | L88,90,95,103,107,113-123 | 多处引用 `model-7`（质量等级），并称 `TYPE_AGENTS` 将 type 5 映射到 `["model-7"]` |
| [routing-exclusive-rules/spec.md](file:///d:/17417/Documents/agent_culti_demo/openspec/specs/routing-exclusive-rules/spec.md#L69) | L69 | "未由专业团队确认 **model-3 与 model-7** 的评价维度分工" |
| [api-documentation-examples/spec.md](file:///d:/17417/Documents/agent_culti_demo/openspec/specs/api-documentation-examples/spec.md#L28) | L28 | "type 4/**model-6** 与 type 7/**model-5**" |
| [callable-thematic-model-stubs/spec.md](file:///d:/17417/Documents/agent_culti_demo/openspec/specs/callable-thematic-model-stubs/spec.md#L75) | L75 | "SHALL NOT 映射到 `model-6`" |

> 注：`openspec/specs/fertility-ml-prediction/`、`api-documentation-examples/` 等为历史归档遗留 spec，模型编号变更 change 未覆盖更新这些主 spec。

### ⚠️ 4.2 占位符 Agent 源文件与测试仍存在

- `framework/agents/specialized/fertility_ml_agent.py`（model-6，含 `model_id="model-6"`）
- `framework/agents/specialized/potential_agent.py`（PotentialAssessmentAgent）
- `tests/test_fertility_ml_prediction.py`（引用 `FertilityMLAgent`/`model_6_execution`）
- `scripts/verify_agent_capabilities.py` 仍 import `FertilityMLAgent`

这些文件**未被** `manager.py` 注册引用（manager 仅加载 5 个正式 Agent），属于死代码/陈旧测试，不影响实际路由，但未按 change 决策 3「移除占位符模型及其所有相关代码」完全清理。

---

## 五、测试证据

**命令**：`python -m pytest tests/test_exclusive_rules.py tests/test_question_type_keywords.py -q`

**结果**：**79 passed in 20.34s**（exit 0）✅

覆盖内容：
- 排他规则 v1 向后兼容
- 维度驱动规则正/反例批量断言（≥20 条/组）
- 跨域裸词不误路由 model-1
- 维度冲突 → boundary_pending 降级
- 维度缺失 → question_type 回退
- question_type 1-5 关键词映射

---

## 六、建议

| 优先级 | 建议 | 说明 |
|--------|------|------|
| 高 | 更新主 spec 的 model-6/model-7 陈旧引用为 model-5 | `multi-agent-orchestrator`、`routing-exclusive-rules`、`api-documentation-examples` 等 spec 与模型编号变更不一致 |
| 中 | 清理占位符 Agent 死代码 | `fertility_ml_agent.py`、`potential_agent.py` 及其测试未被注册引用，可删除以对齐 change 决策 3 |
| 低 | `verify_agent_capabilities.py` 移除 FertilityMLAgent import | 避免资源检查脚本误判 |

> 以上建议属于**一致性/清理**层面，不影响当前五维路由与模型编号的实际运行正确性（路由测试全绿，注册表无悬空引用）。
