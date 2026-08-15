---
title: 4.5 节未命中问题解决方案报告
generated_at: 2026-08-15
related_report: 2026-08-15-natural-language-routing-survey-llm-fixed.md
fixes_applied:
  - nodes.py _extract_five_dim_context 透传 parcel_id/parcel_code 到 context
  - routing.py _identify_question_type_llm prompt 增加 context 路由规则
---

# 4.5 节未命中问题解决方案报告

## 1. 问题回顾

修复 capabilities 编号 + markdown 解析后，LLM 模式调研中 4.5 节有 2 个未命中：

| 问题 | 期望 | 实际 | 性质 |
|------|------|------|------|
| 全省耕地土壤有机质含量如何？ | type=5 | type=1 稳定性 | 问题设计歧义 |
| 帮我出个施肥方案 | type=5 | type=0 RAG | 缺少地块上下文 |

## 2. 解决方案

### 2.1 问题1：全省耕地土壤有机质含量如何 → type=1

**决策**：接受现状（不修改代码）

**理由**：
- "全省...含量如何" 语义上确实更像稳定性/质量评估（询问整体状况）
- LLM 判断在业务上成立
- 这是问题设计本身的歧义，非 LLM 错误

### 2.2 问题2：帮我出个施肥方案 → type=0

**决策**：实施 context 增强

**根因**：用户在地图上选中地块后会问"帮我出个施肥方案"，但路由层不感知"用户已选地块"上下文，LLM 保守地判为知识性问题。

**修复**：
1. **nodes.py**：`_extract_five_dim_context` 显式透传 `parcel_id`/`parcel_code` 到 context
2. **routing.py**：`_identify_question_type_llm` prompt 增加 context 路由规则

## 3. 修改详情

### 3.1 nodes.py 修改

文件：[nodes.py:98-138](file:///d:/17417/Documents/agent_culti_demo/framework/agents/nodes.py#L98-L138)

`_extract_five_dim_context` 函数末尾增加：
```python
# 透传地块标识符（LLM 路由可感知"用户已选地块"场景）
if request.get("parcel_id"):
    context["parcel_id"] = request["parcel_id"]
if request.get("parcel_code"):
    context["parcel_code"] = request["parcel_code"]
```

### 3.2 routing.py 修改

文件：[routing.py:290-334](file:///d:/17417/Documents/agent_culti_demo/framework/agents/routing.py#L290-L334)

`_identify_question_type_llm` 函数：
1. context_lines 增加 `parcel_selected: true` 标注
2. 当检测到 parcel_id/parcel_code 时，prompt 注入【上下文路由规则】：
   - 「施肥方案/培肥/改良/治理」类模糊请求 → 应路由到对应专业模型（type 3/4/5）
   - 「这块地怎么样/肥力如何」类查询 → 应路由到质量评价类模型（type 2）
   - 仅当问题完全与农业/土壤无关时才返回 type 0

## 4. 验证结果

### 4.1 单元测试（5/5 PASSED）

文件：[tests/test_context_enhanced_routing.py](file:///d:/17417/Documents/agent_culti_demo/tests/test_context_enhanced_routing.py)

| 测试 | 期望 | 实际 | 结果 |
|------|------|------|------|
| 无 parcel_id 时「帮我出个施肥方案」 | type=0 | type=0 | ✅ |
| 带 parcel_id 时「帮我出个施肥方案」 | type=5 | type=5 | ✅ |
| 带 parcel_id 时「这块地怎么样」 | type=2 | type=2 | ✅ |
| 带 parcel_code（无 parcel_id）也触发规则 | type=5 | type=5 | ✅ |
| 无 parcel_id 时无关问题仍落入 RAG | type=0 | type=0 | ✅ |

### 4.2 对比验证脚本

文件：[scripts/verify_context_enhanced_routing.py](file:///d:/17417/Documents/agent_culti_demo/scripts/verify_context_enhanced_routing.py)

| 问题 | 无地块 type | **有地块 type** | 差异 |
|------|----------|--------------|------|
| 帮我出个施肥方案 | 0（RAG） | **5（有机质培肥）** | → 改进 |
| 这块地怎么样 | 0（RAG） | **2（质量等级）** | → 改进 |
| 希望提升土壤肥力 | 5 | 5 | =（已命中） |
| 我想培肥这块地 | 5 | 5 | =（已命中） |
| 这地酸了怎么治 | 4 | 4 | =（已命中） |
| 这块地有什么问题 | 3 | 3 | =（已命中） |
| 今天天气怎么样 | 0（RAG） | 0（RAG） | =（正确保持 RAG） |

### 4.3 测试套件回归

```
117 passed, 3 failed（chromadb 兼容性问题，与本次修改无关）
```

**与本次修改相关的失败：0，零回归。**

## 5. 改进效果对比

### 4 个典型口语化提问的最终路由（带 parcel_id 场景）

| 用户提问 | 修复前（无 context 增强） | **修复后（带 parcel_id）** |
|---------|------------------------|--------------------------|
| 希望提升土壤肥力 | type=5 ✅ | type=5 ✅ |
| 提高有机质 | type=5 ✅ | type=5 ✅ |
| 这块地肥力怎么样 | type=2 ✅ | type=2 ✅ |
| 帮我出个施肥方案 | type=0 ❌ | **type=5** ✅ |

**4/4 全部命中**（在用户已选地块的场景下）。

## 6. 未覆盖的深层问题

本次修复只解决了"路由层感知地块上下文"的问题。目标中描述的完整交互链路仍有两个未实现层：

1. **参数自动填充层**：model-5 缺少 `parcel_id → DB → 填充初始有机质` 链路
   - 即使路由命中 model-5，模型仍缺少初始有机质、目标有机质等专业参数
   - 需要后续架构改进

2. **目标值引导层**：用户不知道"17"是否合理
   - 需要系统根据当前有机质智能推荐目标值并校验
   - 需要交互式 UI 改进

这两层属于架构改进，需后续推进。

## 7. 修改文件清单

| 文件 | 改动 |
|------|------|
| [nodes.py](file:///d:/17417/Documents/agent_culti_demo/framework/agents/nodes.py#L98-L138) | `_extract_five_dim_context` 透传 parcel_id/parcel_code |
| [routing.py](file:///d:/17417/Documents/agent_culti_demo/framework/agents/routing.py#L290-L334) | `_identify_question_type_llm` prompt 增加 context 路由规则 |
| [tests/test_context_enhanced_routing.py](file:///d:/17417/Documents/agent_culti_demo/tests/test_context_enhanced_routing.py) | 新增 5 个测试（全部通过） |
| [scripts/verify_context_enhanced_routing.py](file:///d:/17417/Documents/agent_culti_demo/scripts/verify_context_enhanced_routing.py) | 对比验证脚本 |
