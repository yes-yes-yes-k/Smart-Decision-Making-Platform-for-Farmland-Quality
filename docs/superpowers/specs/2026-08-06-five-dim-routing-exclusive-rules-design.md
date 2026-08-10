---
comet_change: add-routing-exclusive-rules
role: technical-design
canonical_spec: openspec
archived-with: 2026-08-06-add-routing-exclusive-rules
status: final
---

# 五维路由升级与排他规则建立 — 技术设计

## Context

现有路由为两阶段路由（关键词优先 + 向量回退），实现在 `framework/agents/nodes.py` 的 `identify_question_type` 中。路由仅依赖 `question_type`（1-7 与 0=RAG）做 1:1 映射到单一 Agent，缺少对重叠模型之间判别所必需的路由特征。易混淆对包括 model-3/7、model-2/7、model-4/6。

`ProfessionalCapability` 目前仅含 question_type、minimal_inputs 等元数据，无分析尺度（省/县/片区/地块）与数据类型（指标数据/评价结果/处方用量）维度。路由逻辑与图节点耦合在 nodes.py 中，不利于版本管理和回归测试。

## Goals / Non-Goals

**Goals:**
- 将路由升级为五维路由：业务任务、分析尺度、数据类型、预期输出、模型依赖。
- 建立可维护、可版本化的排他规则配置，消除三组易混淆对误选。
- 对未由专业团队确认的重叠关系返回「模型边界待确认」显式降级状态。
- 将路由判定逻辑从 nodes.py 模块化为独立路由模块。
- 扩充三组易混淆对测试集（各 ≥20 条正例与反例）。

**Non-Goals:**
- 不实现工具注册中心（4.2）、统一数据对象与适配器（4.3）、任务编排器（4.4）、调用状态机（4.5）、结果保护 Guardrails（4.6）、可观测性（4.7）、端到端流程（4.8）。
- 不改变 `question_type` 到 Agent 的既有 1:1 映射数据结构，仅在其之上叠加五维特征与排他规则。

## 架构

```
问题文本 + 请求上下文 (parcel_id/area_code/scale)
        │
        ▼
┌─────────────────────────────┐
│ 五维特征提取 (routing.py)   │
│ 业务任务 │ 分析尺度 │ 数据类型 │ 预期输出 │ 模型依赖 │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ 排他规则判定 (exclusive_    │
│ rules.py) 数据驱动配置       │
└─────────────────────────────┘
    │ 命中且可消解        │ 无法消解
    ▼                    ▼
  路由到目标 Agent    边界待确认降级
```

## 决策

### 决策 A：路由函数签名扩展（保持向后兼容）
`identify_question_type(question)` 扩展为 `identify_question_type(question, context=None)`。
- `context` 为可选参数，携带 `parcel_id`、`area_code`、`scale` 等。
- 现有 470 个测试只传 question，不加 context 时行为完全不变。
- **理由**：向后兼容，避免破坏现有测试；同时为五维特征提供上下文来源。

### 决策 B：五维特征来源
| 维度 | 来源 |
|------|------|
| 业务任务 | 现有 question_type 关键词/向量判定 |
| 分析尺度 | context.scale / 问题文本（"全省/全县/我的田"） |
| 数据类型 | 上下文 indicators/parcel_id 推断 |
| 预期输出 | 关键词（"等级/指数"→评价结果；"施多少"→处方用量） |
| 模型依赖 | 排他规则配置声明 |

- **理由**：将可提取的维度显式建模，无法确定的维度回退到现有 question_type 行为。

### 决策 C：排他规则数据驱动
`exclusive_rules.py` 声明规则列表，每条含 `pair`（易混淆模型对）、`discriminator`（判别维度）、`condition`（判定条件）、`target`（目标 Agent）。
- 覆盖：现状评价→model-3；潜力→model-2；有机质投入量→model-6；酸化调理剂→model-4；稳定性风险→model-1；质量等级评价→model-7。
- **理由**：将规则从 nodes.py 硬编码判断中解耦，便于专业团队确认后增量维护并独立单测。

### 决策 D：边界待确认降级
排他规则无法消解重叠（优先级冲突或未配置）时，返回 `routing_status: "boundary_pending"` + 「模型边界待确认」提示，不调用任何易混淆专业 Agent。
- **理由**：符合 docx 要求"对未确认的重叠关系系统返回'模型边界待确认'而非自行选择"。

### 决策 E：路由逻辑模块化
新建 `framework/agents/routing.py`（判定逻辑，迁移 `identify_question_type`、`_identify_question_type_keyword`、`_identify_question_type_vector`、`check_relevance`）+ `framework/agents/exclusive_rules.py`（规则配置）。nodes.py 保留图节点状态组装与分支调度。
- **理由**：独立模块便于版本管理、回归测试，符合 docx 4.1 任务 5。

## 数据流

1. `identify_question_node` 从 request 提取 question 与 context，调用 `identify_question_type(question, context)`。
2. 五维特征提取 → 排他规则判定 → 得到 `question_type` + `routing_status`。
3. `route_models` 依据 `routing_status` 分支：
   - `boundary_pending` → 走降级提示，不调用 Agent。
   - 正常 → 走 `execute_models`。
4. `execute_models` 依据 `question_type` 调用 AgentManager 对应 Agent。
5. `aggregate_results` 透传 `routing_status` 与降级提示到 API 响应。

## 错误处理

- 排他规则冲突 → 返回「模型边界待确认」，不静默选择。
- 维度缺失 → 回退现有 question_type 路由。
- Agent 执行失败 → 沿用现有错误降级结构，不调用额外 Agent。

## 实现范围说明（v1 口径）

终审确认：v1 实现为「关键词排他规则 + 五维元数据声明」。

- 六条排他规则判别（现状评价/潜力/有机质投入量/酸化调理剂/稳定性风险/质量等级评价）完全由问题文本关键词子串匹配驱动，判定结果正确且测试通过。
- 五维特征中「分析尺度」「数据类型」已由 `_extract_five_dim_context` 提取并注入 `context`，`ProfessionalCapability` 已声明 `analysis_scale`/`data_type` 字段，但 `apply_exclusive_rules` 的 `context` 参数当前**未参与路由判定**——该参数为兼容 `routing.py` 调用签名而保留，供后续版本按分析尺度/数据类型精化规则时消费。
- 因此「五维路由」在 v1 中如实表述为「关键词驱动排他规则 + 五维特征的元数据声明与上下文预留」，而非五维特征全量参与判定。后续如需让分析尺度/数据类型真正影响路由，需退回设计阶段扩展排他规则与测试。

## 测试策略

- model-3/7、model-2/7、model-4/6 三组易混淆对，各 ≥20 条正例 + 反例。
- 排他规则单元测试 + 边界待确认降级测试。
- 现有约 470 个测试回归通过。

## Open Questions

- 「模型边界待确认」在 API 响应中的具体字段命名与结构（建议 `routing_status` + `degradation` 提示），待与专业团队确认重叠边界后收敛。
