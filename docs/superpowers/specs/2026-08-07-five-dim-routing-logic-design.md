---
comet_change: five-dim-routing-logic
role: technical-design
canonical_spec: openspec
---

# 五维路由逻辑完善 v1 — 技术设计

## Context

五维路由在 v1（archived change `add-routing-exclusive-rules`）中实现为「关键词排他规则 + 五维元数据声明」。`_extract_five_dim_context` 提取了 `scale`（省/县/片区/地块）和 `data_type`（指标数据/评价结果/处方用量），`ProfessionalCapability` 声明了 `analysis_scale`/`data_type` 字段，但 `apply_exclusive_rules` 的 `context` 参数完全未参与路由判定。

当前 `apply_exclusive_rules` 仅使用 `EXCLUSIVE_CONDITION_KEYWORDS` 的问题文本关键词子串匹配，覆盖四组条件：现状评价、酸化调理剂、稳定性风险、质量等级评价。`ExclusiveRule` 有 `discriminator` 字段声明判别维度，但判定逻辑不读取该字段，也不读取 `context` 中的维度值。

v1 设计文档明确记录：「后续如需让分析尺度/数据类型真正影响路由，需退回设计阶段扩展排他规则与测试」。本次变更完成该升级。

## Goals / Non-Goals

**Goals:**
- 让五维特征（业务任务、分析尺度、数据类型、预期输出、模型依赖）真正参与排他规则判定
- 新增业务任务和预期输出关键词表，从问题文本独立提取维度标签
- 扩展 `ExclusiveRule` 支持 `dimension_conditions` 维度判别条件
- 让 `apply_exclusive_rules` 的 `context` 参数真正参与路由判定
- 覆盖 model-1/5（地块评价 vs 地块诊断）和 model-2/3（处方用量区分）判别场景
- 保持 `boundary_pending` 降级机制

**Non-Goals:**
- 不改变 `question_type` 关键词/向量路由基础逻辑（作为兜底）
- 不引入机器学习模型做维度提取
- 不修改 API 响应结构
- 不新增独立的模型依赖判定步骤

## Decisions

### 决策 A：维度提取扩展

在 `_extract_five_dim_context`（`nodes.py`）中新增业务任务和预期输出的提取。

**业务任务关键词表：**

```python
BUSINESS_TASK_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "障碍诊断": ("诊断", "毛病", "障碍", "问题", "现状"),
    "酸化改良": ("酸化", "调理剂", "石灰", "治酸", "pH提升", "碱性"),
    "有机质培肥": ("有机质", "有机肥", "秸秆", "培肥"),
    "稳定性评价": ("稳定性", "退化", "掉级", "稳定"),
    "质量等级评价": ("质量等级", "等级评价", "综合指数", "等级评定"),
}
```

**预期输出关键词表：**

```python
EXPECTED_OUTPUT_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "评价结果": ("等级", "指数", "评价结果", "评定"),
    "处方用量": ("施多少", "每亩", "用量", "投入量"),
    "诊断报告": ("诊断", "问题", "毛病", "障碍"),
}
```

提取逻辑：遍历关键词表，第一个命中关键词的标签作为维度值。分析尺度和数据类型沿用现有提取逻辑。context 返回 `scale`、`data_type`、`business_task`、`expected_output` 四个字段。

**理由**：用户确认业务任务和预期输出均通过新增关键词表独立提取，不从 data_type 推导。

### 决策 B：ExclusiveRule 结构扩展

```python
@dataclass(frozen=True)
class ExclusiveRule:
    pair: FrozenSet[str]
    discriminator: str
    condition: Optional[str] = None           # None = 无关键词条件
    target: str = ""
    dimension_conditions: Dict[str, str] = field(default_factory=dict)  # 空 = 无维度条件
```

- `condition` 改为 `Optional[str]`，`None` 表示不检查关键词
- `dimension_conditions` 新增字段，声明维度判别条件（如 `{"scale": "地块", "data_type": "评价结果"}`）
- 向后兼容：现有规则的 `condition` 保持字符串值，`dimension_conditions` 默认空 dict

### 决策 C：规则匹配算法（AND 逻辑）

```python
def _rule_matches(rule, question, context):
    # 关键词条件检查（condition=None 时跳过）
    if rule.condition is not None:
        if not _condition_matches(question, rule.condition):
            return False
    # 维度条件检查（dimension_conditions 为空时跳过）
    if rule.dimension_conditions:
        if not _dimension_conditions_match(rule.dimension_conditions, context):
            return False
    return True
```

`apply_exclusive_rules` 遍历所有规则，收集匹配规则的 target 到 set：
- `len(matched_targets) > 1` → `boundary_pending`
- `len(matched_targets) == 1` → 该 target
- `len(matched_targets) == 0` → 原始 question_type（回退）

**关键特性：**
- `condition=None` 的规则仅依赖维度条件（新增维度规则）
- `dimension_conditions={}` 的规则仅依赖关键词（v1 向后兼容）
- 同一 target 被多条规则命中不冲突（set 去重）
- 不同 target 被命中 → boundary_pending

### 决策 D：新增维度驱动排他规则

```python
# model-1/5：地块级质量等级评价 → model-5
ExclusiveRule(frozenset({"model-1", "model-5"}), "分析尺度+数据类型+业务任务", None, "model-5",
              dimension_conditions={"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价"}),

# model-1/5：地块级障碍诊断 → model-1
ExclusiveRule(frozenset({"model-1", "model-5"}), "分析尺度+业务任务", None, "model-1",
              dimension_conditions={"scale": "地块", "business_task": "障碍诊断"}),

# model-2/3：酸化调理剂用量 → model-2
ExclusiveRule(frozenset({"model-2", "model-3"}), "数据类型+业务任务", None, "model-2",
              dimension_conditions={"data_type": "处方用量", "business_task": "酸化改良"}),

# model-2/3：有机肥施用量 → model-3
ExclusiveRule(frozenset({"model-2", "model-3"}), "数据类型+业务任务", None, "model-3",
              dimension_conditions={"data_type": "处方用量", "business_task": "有机质培肥"}),
```

### 决策 E：模型依赖间接参与

模型依赖维度通过排他规则的 `pair` 声明间接参与——规则匹配过程本身就是模型依赖的体现。不新增独立判定步骤。

### 决策 F：boundary_pending 保持

当维度条件无法消解歧义（多条规则命中不同 target），仍返回 `routing_status: "boundary_pending"`。

## 数据流

```
用户问题 + 请求上下文
      │
      ▼
_extract_five_dim_context(state)
      │ 提取 scale, data_type, business_task, expected_output
      ▼
identify_question_type(question, context)
      │ 关键词/向量路由 → base_type
      ▼
apply_exclusive_rules(question, base_type, context)
      │ 遍历 EXCLUSIVE_RULES：
      │   keyword_match = (condition is None) or _condition_matches(...)
      │   dim_match = (not dim_conds) or _dimension_conditions_match(...)
      │   if keyword_match AND dim_match → matched_targets.add(target)
      │
      │ len(targets) > 1 → boundary_pending
      │ len(targets) == 1 → 该 target
      │ len(targets) == 0 → 原始 base_type（回退）
      ▼
question_type + routing_status
```

## 测试策略

- **正例测试**：每组易混淆对（model-1/5、model-2/3）≥20 条正例，断言路由到正确 target
- **反例测试**：每组 ≥20 条反例，断言不误选到易混淆对
- **维度冲突降级**：构造同时命中不同 target 的问题 → boundary_pending
- **维度缺失回退**：无 scale/data_type → 回退到 question_type 关键词路由
- **向后兼容**：context=None 时行为与 v1 完全一致
- **回归**：运行 `python -m pytest tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_multi_agent.py -q` 全部通过

## Risks / Trade-offs

- **[维度提取精度]** → 关键词表覆盖度有限，可能漏判或误判。缓解：测试集覆盖正例反例 ≥20 条/组
- **[规则冲突复杂度]** → 新增维度条件后规则间可能产生新的冲突路径。缓解：保持 `matched_targets > 1 → boundary_pending` 的冲突处理逻辑
- **[向后兼容]** → 现有纯关键词规则需保持行为不变。缓解：无 `dimension_conditions` 的规则仅依赖关键词
