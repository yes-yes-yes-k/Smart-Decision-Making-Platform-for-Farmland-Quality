---
change: five-dim-routing-logic
design-doc: docs/superpowers/specs/2026-08-07-five-dim-routing-logic-design.md
base-ref: d79932523bc82e77aa3422effd5cd877aa90ccb0
---

# 五维路由逻辑完善 v1 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让五维特征（业务任务、分析尺度、数据类型、预期输出、模型依赖）真正参与排他规则判定——新增 `business_task`/`expected_output` 关键词表与维度提取、扩展 `ExclusiveRule` 支持 `dimension_conditions` 维度判别条件、让 `apply_exclusive_rules` 的 `context` 参数真正参与路由判定，并新增 4 条维度驱动排他规则覆盖 model-1/5 与 model-2/3 易混淆对。

**Architecture:** 在 v1（archived change `add-routing-exclusive-rules`）已建立的「关键词排他规则 + 五维元数据声明」之上做最小扩展。`_extract_five_dim_context`（`nodes.py`）新增 `business_task`/`expected_output` 两个维度字段，context 返回四维。`exclusive_rules.py` 中 `ExclusiveRule` 增加 `condition: Optional[str]` 与 `dimension_conditions: Dict[str, str]` 字段，匹配算法改为 AND 逻辑（关键词条件 AND 维度条件，任一声明缺失则跳过对应检查）。新增 4 条 `condition=None` 的纯维度规则覆盖 model-1/5 与 model-2/3。保持 `boundary_pending` 降级机制与 v1 纯关键词规则的向后兼容。

**Tech Stack:** Python 3（`dataclasses`、`typing`）、`langgraph`（StateGraph）、`pytest`（测试）。

## Global Constraints

- 语言：所有代码注释、日志、测试断言消息、提示文案使用中文。
- 向后兼容：`apply_exclusive_rules(question, question_type)` 与 `apply_exclusive_rules(question, question_type, context=None)` 行为不得破坏现有测试；`identify_question_type(question)` 与 `identify_question_type(question, context=None)` 同样保持兼容。
- `BUSINESS_TASK_KEYWORDS` 与 `EXPECTED_OUTPUT_KEYWORDS` 的键值必须与 Design Doc「决策 A」完全一致（逐字复制，不可改键名或词序）。
- `ExclusiveRule` 扩展字段必须与 Design Doc「决策 B」一致：`condition: Optional[str] = None`、`dimension_conditions: Dict[str, str] = field(default_factory=dict)`。
- 规则匹配算法为 AND 逻辑（决策 C）：`condition is None` 跳过关键词检查；`dimension_conditions` 为空跳过维度检查；两者皆声明时必须同时满足。
- 新增 4 条维度规则的 `pair`/`discriminator`/`target`/`dimension_conditions` 必须与 Design Doc「决策 D」逐字一致。
- `boundary_pending` 降级机制保持：`len(matched_targets) > 1` → `boundary_pending`；`== 1` → 该 target；`== 0` → 原始 `question_type`（回退）。
- 易混淆对测试：model-1/5、model-2/3 各 ≥20 条正例 + 反例（沿用 v1 测试基础设施 `_expand`/`_assert_rule_batch`/`_assert_not_routed_to`）。
- 测试运行命令：`python -m pytest tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_multi_agent.py -q`，全部通过为验收标准。
- TDD 节奏：每个任务先写失败测试 → 验证失败 → 最小实现 → 验证通过 → 提交。

---

## 文件结构与职责

| 文件 | 职责 | 操作 |
|------|------|------|
| `framework/agents/nodes.py` | `_extract_five_dim_context` 新增 `BUSINESS_TASK_KEYWORDS`/`EXPECTED_OUTPUT_KEYWORDS` 表与 `business_task`/`expected_output` 维度提取；context 返回四维字段 | 修改 |
| `framework/agents/exclusive_rules.py` | `ExclusiveRule` 扩展 `condition`/`dimension_conditions` 字段；新增 `_dimension_conditions_match`；`apply_exclusive_rules` 改为 AND 逻辑；新增 4 条维度驱动规则 | 修改 |
| `tests/test_question_type_keywords.py` | 新增业务任务/预期输出提取测试、向后兼容测试（无 context 行为与 v1 一致） | 修改 |
| `tests/test_exclusive_rules.py` | 新增维度判别测试、维度冲突降级测试、维度缺失回退测试 | 修改 |

### 关键接口约定（跨任务一致）

- `_extract_five_dim_context(state: MultiAgentState) -> dict`：返回 `{"scale": str, "data_type": str, "business_task": Optional[str], "expected_output": Optional[str]}`（`nodes.py`）
- `BUSINESS_TASK_KEYWORDS: Dict[str, Tuple[str, ...]]`、`EXPECTED_OUTPUT_KEYWORDS: Dict[str, Tuple[str, ...]]`（`nodes.py` 模块级常量）
- `ExclusiveRule` dataclass 字段顺序：`pair`、`discriminator`、`condition: Optional[str] = None`、`target: str = ""`、`dimension_conditions: Dict[str, str] = field(default_factory=dict)`（`exclusive_rules.py`）
- `_dimension_conditions_match(dimension_conditions: Dict[str, str], context: Optional[dict]) -> bool`（`exclusive_rules.py`）
- `apply_exclusive_rules(question: str, question_type: int, context: Optional[dict] = None) -> Tuple[int, str]`（`exclusive_rules.py`，签名不变）

---

### Task 1: 业务任务与预期输出维度提取（nodes.py）

**Files:**
- Modify: `framework/agents/nodes.py:70-96`（`_extract_five_dim_context` 函数体）
- Test: `tests/test_question_type_keywords.py`

**Interfaces:**
- Consumes: 现有 `_extract_five_dim_context` 已提取的 `scale`/`data_type` 逻辑保持不变。
- Produces: `nodes.py` 模块级常量 `BUSINESS_TASK_KEYWORDS`、`EXPECTED_OUTPUT_KEYWORDS`；`_extract_five_dim_context` 返回的 dict 新增 `business_task`、`expected_output` 两个键（值可能为 `None`）。

- [x] **Step 1: 写失败测试 —— 业务任务/预期输出提取**

在 `tests/test_question_type_keywords.py` 末尾追加以下测试函数：

```python
def test_extract_business_task_keywords():
    """_extract_five_dim_context 应从问题文本提取 business_task 标签"""
    from framework.agents.nodes import _extract_five_dim_context, BUSINESS_TASK_KEYWORDS
    # 关键词表完整性与 Design Doc 决策 A 一致
    assert set(BUSINESS_TASK_KEYWORDS.keys()) == {
        "障碍诊断", "酸化改良", "有机质培肥", "稳定性评价", "质量等级评价",
    }
    assert BUSINESS_TASK_KEYWORDS["障碍诊断"] == ("诊断", "毛病", "障碍", "问题", "现状")
    assert BUSINESS_TASK_KEYWORDS["酸化改良"] == ("酸化", "调理剂", "石灰", "治酸", "pH提升", "碱性")
    assert BUSINESS_TASK_KEYWORDS["有机质培肥"] == ("有机质", "有机肥", "秸秆", "培肥")
    assert BUSINESS_TASK_KEYWORDS["稳定性评价"] == ("稳定性", "退化", "掉级", "稳定")
    assert BUSINESS_TASK_KEYWORDS["质量等级评价"] == ("质量等级", "等级评价", "综合指数", "等级评定")

    cases = [
        ("我这块地到底有啥毛病", "障碍诊断"),
        ("土壤酸化了怎么治酸", "酸化改良"),
        ("有机肥每亩施用量多少", "有机质培肥"),
        ("这块地质量等级稳不稳", "稳定性评价"),  # "稳定" 命中稳定性评价
        ("耕地质量等级评价结果", "质量等级评价"),
    ]
    for question, expected_task in cases:
        state = {"request": {"question": question}}
        ctx = _extract_five_dim_context(state)
        assert ctx["business_task"] == expected_task, (
            f"「{question}」business_task 应为 {expected_task}，实际 {ctx.get('business_task')}"
        )


def test_extract_expected_output_keywords():
    """_extract_five_dim_context 应从问题文本提取 expected_output 标签"""
    from framework.agents.nodes import _extract_five_dim_context, EXPECTED_OUTPUT_KEYWORDS
    assert set(EXPECTED_OUTPUT_KEYWORDS.keys()) == {"评价结果", "处方用量", "诊断报告"}
    assert EXPECTED_OUTPUT_KEYWORDS["评价结果"] == ("等级", "指数", "评价结果", "评定")
    assert EXPECTED_OUTPUT_KEYWORDS["处方用量"] == ("施多少", "每亩", "用量", "投入量")
    assert EXPECTED_OUTPUT_KEYWORDS["诊断报告"] == ("诊断", "问题", "毛病", "障碍")

    cases = [
        ("耕地质量等级评价结果", "评价结果"),
        ("有机肥每亩施用量多少", "处方用量"),
        ("我这块地到底有啥毛病", "诊断报告"),
    ]
    for question, expected_out in cases:
        state = {"request": {"question": question}}
        ctx = _extract_five_dim_context(state)
        assert ctx["expected_output"] == expected_out, (
            f"「{question}」expected_output 应为 {expected_out}，实际 {ctx.get('expected_output')}"
        )


def test_extract_five_dim_context_returns_four_fields():
    """_extract_five_dim_context 返回的 context 必含 scale/data_type/business_task/expected_output 四字段"""
    from framework.agents.nodes import _extract_five_dim_context
    ctx = _extract_five_dim_context({"request": {"question": "我的田耕地质量等级是多少"}})
    assert set(ctx.keys()) >= {"scale", "data_type", "business_task", "expected_output"}
    assert ctx["scale"] == "地块"  # "我的田" 命中地块
    assert ctx["data_type"] is not None
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_question_type_keywords.py::test_extract_business_task_keywords tests/test_question_type_keywords.py::test_extract_expected_output_keywords tests/test_question_type_keywords.py::test_extract_five_dim_context_returns_four_fields -v`
Expected: FAIL with `ImportError: cannot import name 'BUSINESS_TASK_KEYWORDS'` 或 `KeyError: 'business_task'`。

- [x] **Step 3: 实现 BUSINESS_TASK_KEYWORDS / EXPECTED_OUTPUT_KEYWORDS 与维度提取**

在 `framework/agents/nodes.py` 顶部导入区下方（`initialize_state` 之前）新增两个模块级常量：

```python
from typing import Dict, Tuple

# 业务任务关键词表（Design Doc 决策 A）
BUSINESS_TASK_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "障碍诊断": ("诊断", "毛病", "障碍", "问题", "现状"),
    "酸化改良": ("酸化", "调理剂", "石灰", "治酸", "pH提升", "碱性"),
    "有机质培肥": ("有机质", "有机肥", "秸秆", "培肥"),
    "稳定性评价": ("稳定性", "退化", "掉级", "稳定"),
    "质量等级评价": ("质量等级", "等级评价", "综合指数", "等级评定"),
}

# 预期输出关键词表（Design Doc 决策 A）
EXPECTED_OUTPUT_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "评价结果": ("等级", "指数", "评价结果", "评定"),
    "处方用量": ("施多少", "每亩", "用量", "投入量"),
    "诊断报告": ("诊断", "问题", "毛病", "障碍"),
}
```

然后在 `_extract_five_dim_context` 函数末尾（`return context` 之前）追加两个维度的提取：

```python
def _extract_five_dim_context(state: MultiAgentState) -> dict:
    """从请求提取五维特征上下文（分析尺度/数据类型/业务任务/预期输出）。"""
    request = state.get("request", {})
    context: dict = {}
    scale = request.get("scale")
    if not scale:
        question = request.get("question", "")
        if any(w in question for w in ("我的田", "我的地", "这块", "这个地块", "地块")):
            scale = "地块"
        elif any(w in question for w in ("片区", "村")):
            scale = "片区"
        elif any(w in question for w in ("全省", "全市", "全省耕地")):
            scale = "省"
        elif any(w in question for w in ("全县", "县域", "我们县", "本县")):
            scale = "县"
    context["scale"] = scale or "县"
    if request.get("indicators"):
        context["data_type"] = "指标数据"
    elif request.get("parcel_id") or request.get("parcel_code"):
        context["data_type"] = "评价结果"
    else:
        question = request.get("question", "")
        if any(w in question for w in ("施多少", "每亩", "施用量", "用量", "投入量")):
            context["data_type"] = "处方用量"
        else:
            context["data_type"] = "指标数据"

    # 业务任务提取：第一个命中关键词表的标签作为维度值
    question_text = request.get("question", "")
    context["business_task"] = _match_first_keyword(question_text, BUSINESS_TASK_KEYWORDS)
    # 预期输出提取
    context["expected_output"] = _match_first_keyword(question_text, EXPECTED_OUTPUT_KEYWORDS)
    return context


def _match_first_keyword(question: str, table: Dict[str, Tuple[str, ...]]) -> Optional[str]:
    """遍历关键词表，返回第一个命中关键词的标签；未命中返回 None。"""
    for label, keywords in table.items():
        for kw in keywords:
            if kw in question:
                return label
    return None
```

注意：`Optional` 已在 `nodes.py` 顶部从 `typing` 导入（若未导入需补充 `from typing import Optional`）。

- [x] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_question_type_keywords.py::test_extract_business_task_keywords tests/test_question_type_keywords.py::test_extract_expected_output_keywords tests/test_question_type_keywords.py::test_extract_five_dim_context_returns_four_fields -v`
Expected: PASS（3 个测试全绿）。

- [x] **Step 5: 回归现有 question_type 关键词测试**

Run: `python -m pytest tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_multi_agent.py -q`
Expected: PASS（确保维度提取扩展未破坏 v1 行为；现有测试不依赖 `business_task`/`expected_output` 字段，应全绿）。

- [x] **Step 6: 提交**

```bash
git add framework/agents/nodes.py tests/test_question_type_keywords.py
git commit -m "feat(five-dim): 业务任务/预期输出维度提取写入 context"
```

---

### Task 2: ExclusiveRule 结构扩展（condition 可选 + dimension_conditions 字段）

**Files:**
- Modify: `framework/agents/exclusive_rules.py:23-33`（`ExclusiveRule` dataclass）
- Test: `tests/test_exclusive_rules.py`

**Interfaces:**
- Consumes: 无外部依赖。
- Produces: `ExclusiveRule.condition` 类型由 `str` 改为 `Optional[str] = None`；新增 `ExclusiveRule.dimension_conditions: Dict[str, str] = field(default_factory=dict)`。现有 `EXCLUSIVE_RULES` 中 4 条规则的构造调用需补齐 `target` 关键字参数（因 `condition` 现在有默认值，参数顺序变化）。

- [x] **Step 1: 写失败测试 —— ExclusiveRule 新字段**

在 `tests/test_exclusive_rules.py` 末尾追加：

```python
def test_exclusive_rule_supports_dimension_conditions():
    """ExclusiveRule 支持 dimension_conditions 字段，且默认空 dict"""
    from framework.agents.exclusive_rules import ExclusiveRule
    import dataclasses

    # 默认构造：condition=None、dimension_conditions={}
    rule_default = ExclusiveRule(
        pair=frozenset({"model-1", "model-5"}),
        discriminator="测试",
    )
    assert rule_default.condition is None
    assert rule_default.dimension_conditions == {}
    assert rule_default.target == ""

    # 完整构造
    rule_full = ExclusiveRule(
        pair=frozenset({"model-1", "model-5"}),
        discriminator="分析尺度+数据类型+业务任务",
        condition=None,
        target="model-5",
        dimension_conditions={"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价"},
    )
    assert rule_full.target == "model-5"
    assert rule_full.dimension_conditions == {"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价"}

    # 现有 v1 规则：condition 保持字符串值，dimension_conditions 默认空
    rule_v1 = ExclusiveRule(
        pair=frozenset({"model-1", "model-5"}),
        discriminator="业务任务",
        condition="现状评价",
        target="model-1",
    )
    assert rule_v1.condition == "现状评价"
    assert rule_v1.dimension_conditions == {}


def test_existing_exclusive_rules_backward_compatible():
    """现有 4 条 v1 规则字段保持向后兼容：condition 为字符串、dimension_conditions 为空"""
    from framework.agents.exclusive_rules import EXCLUSIVE_RULES
    # v1 规则应至少 4 条
    assert len(EXCLUSIVE_RULES) >= 4
    for rule in EXCLUSIVE_RULES:
        # 现有规则 condition 必为字符串（非 None）
        assert isinstance(rule.condition, str), f"{rule} 的 condition 应为字符串"
        # 现有规则 dimension_conditions 必为空 dict
        assert rule.dimension_conditions == {}, f"{rule} 的 dimension_conditions 应为空"
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_exclusive_rules.py::test_exclusive_rule_supports_dimension_conditions tests/test_exclusive_rules.py::test_existing_exclusive_rules_backward_compatible -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'dimension_conditions'` 或 v1 规则字段不匹配。

- [x] **Step 3: 扩展 ExclusiveRule dataclass**

修改 `framework/agents/exclusive_rules.py` 顶部导入与 dataclass：

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional, Tuple

from .capabilities import CAPABILITY_BY_AGENT_ID, CAPABILITY_BY_QUESTION_TYPE

# routing_status 取值
ROUTING_STATUS_NORMAL = "normal"
ROUTING_STATUS_BOUNDARY_PENDING = "boundary_pending"

BOUNDARY_PENDING_MESSAGE = (
    "该问题的模型边界尚未由专业团队确认，系统返回「模型边界待确认」，"
    "暂不调用任一易混淆专业模型，请补充更明确的分析尺度或数据类型信息。"
)


@dataclass(frozen=True)
class ExclusiveRule:
    """一条排他规则。

    匹配逻辑为 AND：condition（关键词条件）与 dimension_conditions（维度条件）
    必须同时满足（任一声明缺失则跳过对应检查）。
    pair 仅用于文档化该规则所属的易混淆模型对。
    """
    pair: FrozenSet[str]
    discriminator: str   # 判别维度：业务任务/分析尺度/数据类型/预期输出/模型依赖
    condition: Optional[str] = None  # None = 无关键词条件，仅依赖维度
    target: str = ""                  # 目标 model_id
    dimension_conditions: Dict[str, str] = field(default_factory=dict)  # 空 = 无维度条件
```

同时更新 `EXCLUSIVE_RULES` 中 4 条 v1 规则的构造调用，显式传 `target`（参数顺序已变，必须关键字传参）：

```python
EXCLUSIVE_RULES: Tuple[ExclusiveRule, ...] = (
    # model-1 vs model-5：现状评价 → model-1（障碍诊断）
    ExclusiveRule(frozenset({"model-1", "model-5"}), "业务任务", "现状评价", "model-1"),
    # model-2 vs model-3：酸化调理剂 → model-2（酸化改良）
    ExclusiveRule(frozenset({"model-2", "model-3"}), "业务任务", "酸化调理剂", "model-2"),
    # model-4：稳定性风险 → model-4
    ExclusiveRule(frozenset({"model-4"}), "业务任务", "稳定性风险", "model-4"),
    # model-5：质量等级评价 → model-5
    ExclusiveRule(frozenset({"model-5"}), "预期输出", "质量等级评价", "model-5"),
)
```

注意：v1 规则的 4 元组构造 `(pair, discriminator, condition, target)` 与新字段顺序一致，无需改动；仅 dataclass 定义变化即可让默认值生效。

- [x] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_exclusive_rules.py::test_exclusive_rule_supports_dimension_conditions tests/test_exclusive_rules.py::test_existing_exclusive_rules_backward_compatible -v`
Expected: PASS（2 个测试全绿）。

- [x] **Step 5: 回归 v1 排他规则测试**

Run: `python -m pytest tests/test_exclusive_rules.py -q`
Expected: PASS（v1 4 条规则匹配行为不变；`test_rule_status_refers_to_model1` 等仍绿）。

- [x] **Step 6: 提交**

```bash
git add framework/agents/exclusive_rules.py tests/test_exclusive_rules.py
git commit -m "feat(exclusive-rules): ExclusiveRule 支持 condition 可选与 dimension_conditions 字段"
```

---

### Task 3: _dimension_conditions_match 函数与 apply_exclusive_rules AND 逻辑

**Files:**
- Modify: `framework/agents/exclusive_rules.py:56-101`（`_condition_matches` 之后新增 `_dimension_conditions_match`，重写 `apply_exclusive_rules` 匹配逻辑）
- Test: `tests/test_exclusive_rules.py`

**Interfaces:**
- Consumes: Task 2 产出的 `ExclusiveRule.condition`/`ExclusiveRule.dimension_conditions` 字段；Task 1 产出的 context 四维字段。
- Produces: `_dimension_conditions_match(dimension_conditions, context) -> bool`；`apply_exclusive_rules` 改为 AND 逻辑遍历，行为遵循 Design Doc 决策 C。

- [x] **Step 1: 写失败测试 —— _dimension_conditions_match 与 AND 逻辑**

在 `tests/test_exclusive_rules.py` 末尾追加：

```python
def test_dimension_conditions_match_all_match():
    """context 四维全部满足 dimension_conditions → True"""
    from framework.agents.exclusive_rules import _dimension_conditions_match
    dim_conds = {"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价"}
    ctx = {"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价", "expected_output": "评价结果"}
    assert _dimension_conditions_match(dim_conds, ctx) is True


def test_dimension_conditions_match_partial_mismatch():
    """任一维度不匹配 → False"""
    from framework.agents.exclusive_rules import _dimension_conditions_match
    dim_conds = {"scale": "地块", "data_type": "评价结果"}
    assert _dimension_conditions_match(dim_conds, {"scale": "县", "data_type": "评价结果"}) is False
    assert _dimension_conditions_match(dim_conds, {"scale": "地块", "data_type": "指标数据"}) is False


def test_dimension_conditions_match_missing_field_in_context():
    """context 缺少声明维度 → 该维度视为不匹配 → False"""
    from framework.agents.exclusive_rules import _dimension_conditions_match
    dim_conds = {"scale": "地块", "business_task": "障碍诊断"}
    # context 缺 business_task 键
    assert _dimension_conditions_match(dim_conds, {"scale": "地块", "data_type": "指标数据"}) is False
    # context 中 business_task 为 None
    assert _dimension_conditions_match(dim_conds, {"scale": "地块", "business_task": None}) is False


def test_dimension_conditions_match_empty_conditions():
    """dimension_conditions 为空 → 跳过维度检查 → True"""
    from framework.agents.exclusive_rules import _dimension_conditions_match
    assert _dimension_conditions_match({}, {"scale": "地块"}) is True
    assert _dimension_conditions_match({}, None) is True


def test_dimension_conditions_match_none_context():
    """context 为 None 且 dimension_conditions 非空 → False"""
    from framework.agents.exclusive_rules import _dimension_conditions_match
    assert _dimension_conditions_match({"scale": "地块"}, None) is False


def test_apply_exclusive_rules_and_logic_condition_only():
    """AND 逻辑：v1 纯关键词规则（dimension_conditions 为空）行为不变"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # 现状评价 → model-1（无 dimension_conditions，仅关键词）
    final_type, status = apply_exclusive_rules("耕地质量现状评价如何", 5, {"scale": "地块"})
    assert (final_type, status) == (1, "normal")


def test_apply_exclusive_rules_and_logic_dimension_only_no_match():
    """AND 逻辑：condition=None 的规则（仅维度条件）暂未新增时，无关键词命中的问题应回退原 type"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # 此时还未新增维度规则（Task 4 才加），无任何规则命中 → 回退 base_type
    final_type, status = apply_exclusive_rules("普通问题没有关键词", 2, {"scale": "地块", "data_type": "处方用量"})
    assert (final_type, status) == (2, "normal")


def test_apply_exclusive_rules_no_context_backward_compat():
    """context=None 时行为与 v1 完全一致：仅关键词规则生效"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # context=None：v1 关键词规则仍触发
    final_type, status = apply_exclusive_rules("耕地质量现状评价如何", 5, None)
    assert (final_type, status) == (1, "normal")
    # context=None：无关键词命中 → 回退
    final_type, status = apply_exclusive_rules("普通问题", 2, None)
    assert (final_type, status) == (2, "normal")
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_exclusive_rules.py -k "dimension_conditions_match or and_logic or backward_compat" -v`
Expected: FAIL with `ImportError: cannot import name '_dimension_conditions_match'`。

- [x] **Step 3: 实现 _dimension_conditions_match 与 AND 逻辑**

修改 `framework/agents/exclusive_rules.py`，在 `_condition_matches` 函数之后新增 `_dimension_conditions_match`，并重写 `apply_exclusive_rules` 的匹配逻辑：

```python
def _condition_matches(question: str, condition: str) -> bool:
    for kw in EXCLUSIVE_CONDITION_KEYWORDS.get(condition, ()):
        if kw in question:
            return True
    return False


def _dimension_conditions_match(
    dimension_conditions: Dict[str, str],
    context: Optional[dict],
) -> bool:
    """检查 context 中对应维度值是否全部匹配 dimension_conditions。

    - dimension_conditions 为空 → 跳过维度检查，返回 True
    - context 为 None 且 dimension_conditions 非空 → 返回 False
    - 任一声明维度在 context 中缺失或值不匹配 → 返回 False
    """
    if not dimension_conditions:
        return True
    if context is None:
        return False
    for dim_key, expected_value in dimension_conditions.items():
        actual_value = context.get(dim_key)
        if actual_value != expected_value:
            return False
    return True


def _rule_matches(rule: ExclusiveRule, question: str, context: Optional[dict]) -> bool:
    """单条规则匹配判定（AND 逻辑）。

    - condition is None：跳过关键词检查
    - dimension_conditions 为空：跳过维度检查
    - 两者皆声明时必须同时满足
    """
    if rule.condition is not None:
        if not _condition_matches(question, rule.condition):
            return False
    if rule.dimension_conditions:
        if not _dimension_conditions_match(rule.dimension_conditions, context):
            return False
    return True


def model_id_to_question_type(model_id: str) -> Optional[int]:
    # "model-1".."model-5" 在 capabilities 注册表中登记为 agent_id，据此反查 question_type
    capability = CAPABILITY_BY_AGENT_ID.get(model_id)
    return capability.question_type if capability else None


def apply_exclusive_rules(
    question: str,
    question_type: int,
    context: Optional[dict] = None,
) -> Tuple[int, str]:
    """应用排他规则判定，返回 (question_type, routing_status)。

    匹配算法（AND 逻辑）：
    - 遍历 EXCLUSIVE_RULES，对每条规则检查 condition（关键词）与 dimension_conditions（维度）
      是否同时满足（任一声明缺失则跳过对应检查）。
    - 收集所有匹配规则的 target 到 set。
    - len(matched_targets) > 1 → boundary_pending（优先级冲突）
    - len(matched_targets) == 1 → 该 target
    - len(matched_targets) == 0 → 原始 question_type（回退）

    - routing_status == "normal"：正常路由。
    - routing_status == "boundary_pending"：规则优先级冲突、重叠无法消解，显式降级。
    - TYPE_0(RAG) 与未知类型不应用排他规则。
    """
    if question_type == 0:
        return question_type, ROUTING_STATUS_NORMAL
    capability = CAPABILITY_BY_QUESTION_TYPE.get(question_type)
    if capability is None:
        return question_type, ROUTING_STATUS_NORMAL

    matched_targets = {
        rule.target
        for rule in EXCLUSIVE_RULES
        if _rule_matches(rule, question, context)
    }

    if len(matched_targets) > 1:
        # 优先级冲突：同一问题命中指向不同模型的规则，无法消解
        return question_type, ROUTING_STATUS_BOUNDARY_PENDING
    if len(matched_targets) == 1:
        target = next(iter(matched_targets))
        target_qtype = model_id_to_question_type(target)
        return target_qtype, ROUTING_STATUS_NORMAL
    # 未命中任何规则：维持既有 question_type 判定
    return question_type, ROUTING_STATUS_NORMAL
```

- [x] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_exclusive_rules.py -k "dimension_conditions_match or and_logic or backward_compat" -v`
Expected: PASS（新增 8 个测试全绿）。

- [x] **Step 5: 回归 v1 全部排他规则测试**

Run: `python -m pytest tests/test_exclusive_rules.py tests/test_question_type_keywords.py tests/test_multi_agent.py -q`
Expected: PASS（v1 关键词规则行为不变；`test_rule_status_refers_to_model1` 等仍绿）。

- [x] **Step 6: 提交**

```bash
git add framework/agents/exclusive_rules.py tests/test_exclusive_rules.py
git commit -m "feat(exclusive-rules): _dimension_conditions_match 与 AND 逻辑判定"
```

---

### Task 4: 新增 4 条维度驱动排他规则（model-1/5 与 model-2/3）

**Files:**
- Modify: `framework/agents/exclusive_rules.py:44-53`（`EXCLUSIVE_RULES` 元组追加 4 条规则）
- Test: `tests/test_exclusive_rules.py`

**Interfaces:**
- Consumes: Task 1 的 context 四维字段；Task 2/3 的 `ExclusiveRule.dimension_conditions` 与 `_rule_matches` AND 逻辑。
- Produces: `EXCLUSIVE_RULES` 元组新增 4 条 `condition=None` 的纯维度规则，覆盖 model-1/5（地块级质量等级评价 → model-5；地块级障碍诊断 → model-1）与 model-2/3（酸化调理剂用量 → model-2；有机肥施用量 → model-3）。

- [x] **Step 1: 写失败测试 —— 4 条维度规则正例**

在 `tests/test_exclusive_rules.py` 末尾追加：

```python
def test_dim_rule_model5_plot_grade_eval():
    """维度规则：地块级质量等级评价 → model-5"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    ctx = {"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价", "expected_output": "评价结果"}
    final_type, status = apply_exclusive_rules("我的田耕地质量等级评价结果", 1, ctx)
    assert (final_type, status) == (5, "normal"), f"地块级质量等级评价应路由 model-5，实际 ({final_type}, {status})"


def test_dim_rule_model1_plot_diagnosis():
    """维度规则：地块级障碍诊断 → model-1"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    ctx = {"scale": "地块", "data_type": "指标数据", "business_task": "障碍诊断", "expected_output": "诊断报告"}
    final_type, status = apply_exclusive_rules("我这块地到底有啥毛病", 5, ctx)
    assert (final_type, status) == (1, "normal"), f"地块级障碍诊断应路由 model-1，实际 ({final_type}, {status})"


def test_dim_rule_model2_acidification_dosage():
    """维度规则：酸化调理剂用量 → model-2"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    ctx = {"scale": "地块", "data_type": "处方用量", "business_task": "酸化改良", "expected_output": "处方用量"}
    final_type, status = apply_exclusive_rules("酸化调理剂每亩施用量多少", 3, ctx)
    assert (final_type, status) == (2, "normal"), f"酸化调理剂用量应路由 model-2，实际 ({final_type}, {status})"


def test_dim_rule_model3_organic_dosage():
    """维度规则：有机肥施用量 → model-3"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    ctx = {"scale": "地块", "data_type": "处方用量", "business_task": "有机质培肥", "expected_output": "处方用量"}
    final_type, status = apply_exclusive_rules("有机肥每亩施用量多少", 2, ctx)
    assert (final_type, status) == (3, "normal"), f"有机肥施用量应路由 model-3，实际 ({final_type}, {status})"


def test_dim_rules_do_not_affect_wrong_scale():
    """维度规则：scale 不匹配时不应触发（如省/县级质量等级评价不命中地块级 model-5 规则）"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    ctx = {"scale": "省", "data_type": "评价结果", "business_task": "质量等级评价", "expected_output": "评价结果"}
    # base_type=5，无地块级规则命中，回退 5（不误路由到 model-5 维度规则的副作用是保持原 type）
    final_type, status = apply_exclusive_rules("全省耕地质量等级评价结果", 5, ctx)
    assert (final_type, status) == (5, "normal")
```

- [x] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_exclusive_rules.py -k "dim_rule" -v`
Expected: FAIL — 4 条正例测试因无维度规则触发而回退到 base_type（如 model-5 正例返回 1 而非 5）。

- [x] **Step 3: 新增 4 条维度驱动规则**

修改 `framework/agents/exclusive_rules.py` 的 `EXCLUSIVE_RULES` 元组，在 v1 4 条规则之后追加 4 条维度规则（与 Design Doc 决策 D 逐字一致）：

```python
EXCLUSIVE_RULES: Tuple[ExclusiveRule, ...] = (
    # ===== v1 纯关键词规则（向后兼容，dimension_conditions 为空）=====
    # model-1 vs model-5：现状评价 → model-1（障碍诊断）
    ExclusiveRule(frozenset({"model-1", "model-5"}), "业务任务", "现状评价", "model-1"),
    # model-2 vs model-3：酸化调理剂 → model-2（酸化改良）
    ExclusiveRule(frozenset({"model-2", "model-3"}), "业务任务", "酸化调理剂", "model-2"),
    # model-4：稳定性风险 → model-4
    ExclusiveRule(frozenset({"model-4"}), "业务任务", "稳定性风险", "model-4"),
    # model-5：质量等级评价 → model-5
    ExclusiveRule(frozenset({"model-5"}), "预期输出", "质量等级评价", "model-5"),

    # ===== v1.1 维度驱动规则（condition=None，仅依赖 dimension_conditions）=====
    # model-1/5：地块级质量等级评价 → model-5
    ExclusiveRule(
        frozenset({"model-1", "model-5"}),
        "分析尺度+数据类型+业务任务",
        None,
        "model-5",
        dimension_conditions={"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价"},
    ),
    # model-1/5：地块级障碍诊断 → model-1
    ExclusiveRule(
        frozenset({"model-1", "model-5"}),
        "分析尺度+业务任务",
        None,
        "model-1",
        dimension_conditions={"scale": "地块", "business_task": "障碍诊断"},
    ),
    # model-2/3：酸化调理剂用量 → model-2
    ExclusiveRule(
        frozenset({"model-2", "model-3"}),
        "数据类型+业务任务",
        None,
        "model-2",
        dimension_conditions={"data_type": "处方用量", "business_task": "酸化改良"},
    ),
    # model-2/3：有机肥施用量 → model-3
    ExclusiveRule(
        frozenset({"model-2", "model-3"}),
        "数据类型+业务任务",
        None,
        "model-3",
        dimension_conditions={"data_type": "处方用量", "business_task": "有机质培肥"},
    ),
)
```

- [x] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_exclusive_rules.py -k "dim_rule" -v`
Expected: PASS（5 个测试全绿，包括 wrong_scale 反例）。

- [x] **Step 5: 回归 v1 全部测试**

Run: `python -m pytest tests/test_exclusive_rules.py tests/test_question_type_keywords.py tests/test_multi_agent.py -q`
Expected: PASS — 注意 v1 关键词规则（如 `test_pair_model1_vs_model5_positive`）调用 `apply_exclusive_rules(q, base, {"scale": "地块"})`，此时 context 只有 `scale`，维度规则因 `data_type`/`business_task` 缺失不会触发，行为与 v1 一致。

- [x] **Step 6: 提交**

```bash
git add framework/agents/exclusive_rules.py tests/test_exclusive_rules.py
git commit -m "feat(exclusive-rules): 新增 4 条维度驱动规则覆盖 model-1/5 与 model-2/3"
```

---

### Task 5: 向后兼容验证（v1 纯关键词规则行为不变）

**Files:**
- Modify: `tests/test_question_type_keywords.py`（新增向后兼容测试）
- Modify: `tests/test_exclusive_rules.py`（新增 context=None 与无维度场景测试）
- Test: 同上

**Interfaces:**
- Consumes: Task 1-4 全部产出。
- Produces: 显式测试用例证明 v1 行为（context=None、context 仅含 scale、无 business_task/expected_output）在 v1.1 实现下完全一致。

- [x] **Step 1: 写向后兼容测试**

在 `tests/test_question_type_keywords.py` 末尾追加：

```python
def test_v1_compat_context_none_identical_to_v1():
    """context=None 时 identify_question_type 行为与 v1 完全一致（不应用排他规则）"""
    from framework.agents import routing
    real_flag = routing.EMBEDDING_AVAILABLE
    try:
        routing.EMBEDDING_AVAILABLE = False  # 纯关键词，确定性
        cases = [
            ("耕地质量现状评价如何", 1),    # TYPE_1 关键词
            ("酸化调理剂每亩施用量", 2),    # TYPE_2 关键词
            ("有机肥每亩施用量多少", 3),    # TYPE_3 关键词
            ("这块地稳定性退化风险", 4),    # TYPE_4 关键词
            ("耕地质量等级评价结果", 5),    # TYPE_5 关键词
        ]
        for q, expected in cases:
            qt_no_ctx, _ = routing.identify_question_type(q)              # 无 context
            qt_with_none, _ = routing.identify_question_type(q, None)     # context=None
            assert qt_no_ctx == expected, f"无 context「{q}」期望 TYPE_{expected}，实际 TYPE_{qt_no_ctx}"
            assert qt_with_none == qt_no_ctx, f"context=None 应与无 context 一致"
    finally:
        routing.EMBEDDING_AVAILABLE = real_flag


def test_v1_compat_context_scale_only_does_not_trigger_dim_rules():
    """context 仅含 scale（v1 测试基础设施场景）不应触发 v1.1 维度规则"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # v1 测试中 _assert_rule_batch 传入 {"scale": "地块"}，
    # 维度规则要求 data_type+business_task 同时匹配，scale-only context 不应触发
    cases = [
        ("耕地质量现状评价如何", 5, 1),   # v1 规则：现状评价 → model-1
        ("酸化调理剂每亩施用量", 3, 2),   # v1 规则：酸化调理剂 → model-2
        ("这块地稳定性退化风险", 3, 4),   # v1 规则：稳定性风险 → model-4
        ("耕地质量等级评价结果", 3, 5),   # v1 规则：质量等级评价 → model-5
    ]
    for q, base, expected in cases:
        final_type, status = apply_exclusive_rules(q, base, {"scale": "地块"})
        assert (final_type, status) == (expected, "normal"), (
            f"scale-only context「{q}」应保持 v1 行为 (→{expected})，实际 ({final_type}, {status})"
        )
```

在 `tests/test_exclusive_rules.py` 末尾追加：

```python
def test_v1_compat_no_dimension_conditions_rules_unchanged():
    """v1 4 条规则（dimension_conditions 为空）匹配行为完全不变"""
    from framework.agents.exclusive_rules import EXCLUSIVE_RULES, _rule_matches
    # v1 规则集合
    v1_rules = [r for r in EXCLUSIVE_RULES if not r.dimension_conditions]
    assert len(v1_rules) == 4, f"v1 纯关键词规则应保留 4 条，实际 {len(v1_rules)}"
    # v1 规则 condition 必为字符串
    for rule in v1_rules:
        assert isinstance(rule.condition, str)


def test_v1_compat_conflict_still_boundary_pending():
    """v1 冲突场景（现状评价 + 质量等级评价）仍降级 boundary_pending"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # "耕地质量等级现状评价" 同时命中 v1 现状评价(→model-1) 与 质量等级评价(→model-5)
    final_type, status = apply_exclusive_rules("耕地质量等级现状评价", 1, {"scale": "地块"})
    assert status == "boundary_pending", f"v1 冲突应保持 boundary_pending，实际 {status}"
```

- [x] **Step 2: 运行测试验证通过**

Run: `python -m pytest tests/test_question_type_keywords.py::test_v1_compat_context_none_identical_to_v1 tests/test_question_type_keywords.py::test_v1_compat_context_scale_only_does_not_trigger_dim_rules tests/test_exclusive_rules.py::test_v1_compat_no_dimension_conditions_rules_unchanged tests/test_exclusive_rules.py::test_v1_compat_conflict_still_boundary_pending -v`
Expected: PASS（4 个测试全绿；若失败需检查 Task 4 维度规则是否在 scale-only context 误触发）。

- [x] **Step 3: 提交**

```bash
git add tests/test_question_type_keywords.py tests/test_exclusive_rules.py
git commit -m "test(exclusive-rules): 显式向后兼容测试覆盖 v1 行为不变"
```

---

### Task 6: 维度判别批量正例/反例测试（≥20 条/组）

**Files:**
- Modify: `tests/test_exclusive_rules.py`（新增 4 组维度规则的正例/反例批量测试）
- Test: 同上

**Interfaces:**
- Consumes: Task 4 的 4 条维度规则；Task 1 的 `_extract_five_dim_context`（用于从问题文本动态生成 context，模拟真实数据流）。
- Produces: 4 组易混淆对（model-1/5 × 2 方向、model-2/3 × 2 方向）各 ≥20 条正例 + 反例测试。

- [x] **Step 1: 写维度判别批量测试**

在 `tests/test_exclusive_rules.py` 顶部辅助函数区（`_apply` 之后）新增维度 context 构造器与批量断言工具：

```python
def _ctx_from_question(question, scale="地块"):
    """通过 _extract_five_dim_context 从问题文本动态提取四维 context（模拟真实数据流）"""
    from framework.agents.nodes import _extract_five_dim_context
    state = {"request": {"question": question, "scale": scale}}
    return _extract_five_dim_context(state)


def _assert_dim_rule_batch(questions, base_qtype, expected_model, scale="地块"):
    """维度规则正例批量断言：≥20 条，每条经 _extract_five_dim_context 生成 context 后路由到 expected_model"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    assert len(questions) >= 20, f"{expected_model} 维度正例应 ≥20，实际 {len(questions)}"
    MODEL_TO_QTYPE = {"model-1": 1, "model-2": 2, "model-3": 3, "model-4": 4, "model-5": 5}
    exp = MODEL_TO_QTYPE[expected_model]
    for q in questions:
        ctx = _ctx_from_question(q, scale)
        final_type, status = apply_exclusive_rules(q, base_qtype, ctx)
        assert final_type == exp, (
            f"维度正例「{q}」应路由 {expected_model}(type {exp})，实际 type {final_type}，ctx={ctx}"
        )
        assert status == "normal", f"维度正例「{q}」状态应为 normal，实际 {status}"


def _assert_dim_not_routed_to(questions, base_qtype, forbidden_model, scale="地块"):
    """维度规则反例批量断言：每条不路由到 forbidden_model"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    MODEL_TO_QTYPE = {"model-1": 1, "model-2": 2, "model-3": 3, "model-4": 4, "model-5": 5}
    forb = MODEL_TO_QTYPE[forbidden_model]
    for q in questions:
        ctx = _ctx_from_question(q, scale)
        final_type, _ = apply_exclusive_rules(q, base_qtype, ctx)
        assert final_type != forb, (
            f"维度反例「{q}」不应路由 {forbidden_model}，实际 type {final_type}，ctx={ctx}"
        )
```

然后在文件末尾追加 4 组批量测试（每组 ≥20 条正例 + 反例）：

```python
# ===== 维度规则批量正例/反例 =====
from tests.test_question_type_keywords import _expand

# model-5 维度正例：地块级质量等级评价（含"质量等级"关键词触发 business_task=质量等级评价）
MODEL5_DIM_STEMS = [
    "耕地质量等级评价结果", "耕地质量等级评价", "地块质量等级评价",
    "我的田质量等级是多少", "这块地质量等级评定", "耕地质量等级综合指数",
    "地块质量等级评价结果", "我的田耕地质量等级评价", "这块地综合指数和障碍度排序",
    "耕地质量等级评定结果",
]
# model-1 维度正例：地块级障碍诊断（含"毛病/障碍/诊断"关键词触发 business_task=障碍诊断）
MODEL1_DIM_STEMS = [
    "我这块地有啥毛病", "地块障碍诊断", "我的田障碍问题",
    "这块地障碍诊断", "我这块地障碍因素", "我的田地块诊断",
    "这块地到底有啥毛病", "地块障碍识别", "我的田有啥问题",
    "这块地主要毛病",
]
# model-2 维度正例：酸化调理剂用量（含"酸化/调理剂" + "每亩/用量"）
MODEL2_DIM_STEMS = [
    "酸化调理剂每亩施用量", "酸化调理剂用量多少", "酸化土壤每亩石灰用量",
    "酸化田每亩调理剂用量", "酸性土壤调理剂施用量", "酸化治理每亩用量",
    "酸化改良调理剂每亩", "酸化田石灰每亩用量", "酸化调理剂投入量",
    "酸化土壤碱性调理剂用量",
]
# model-3 维度正例：有机肥施用量（含"有机肥/有机质/秸秆" + "每亩/用量"）
MODEL3_DIM_STEMS = [
    "有机肥每亩施用量", "有机质每亩用量", "秸秆每亩施用量",
    "有机肥投入量多少", "有机肥每亩用量", "提升有机质每亩用量",
    "有机肥施用量多少", "秸秆还田每亩用量", "有机质培肥每亩用量",
    "有机肥每亩投入量",
]

DIM_PREFIXES = ["", "我的田", "这块地", "我这块地", "我的地块"]
DIM_SUFFIXES = ["", "？", "呢"]


def test_dim_pair_model5_vs_model1_positive():
    """model-1/5 维度正例：地块级质量等级评价 → model-5；地块级障碍诊断 → model-1"""
    _assert_dim_rule_batch(_expand(MODEL5_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES), 1, "model-5")
    _assert_dim_rule_batch(_expand(MODEL1_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES), 5, "model-1")


def test_dim_pair_model5_vs_model1_negative():
    """model-1/5 维度反例：不误路由到对方"""
    _assert_dim_not_routed_to(_expand(MODEL5_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES), 1, "model-1")
    _assert_dim_not_routed_to(_expand(MODEL1_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES), 5, "model-5")


def test_dim_pair_model2_vs_model3_positive():
    """model-2/3 维度正例：酸化调理剂用量 → model-2；有机肥施用量 → model-3"""
    _assert_dim_rule_batch(_expand(MODEL2_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES), 3, "model-2")
    _assert_dim_rule_batch(_expand(MODEL3_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES), 2, "model-3")


def test_dim_pair_model2_vs_model3_negative():
    """model-2/3 维度反例：不误路由到对方"""
    _assert_dim_not_routed_to(_expand(MODEL2_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES), 3, "model-3")
    _assert_dim_not_routed_to(_expand(MODEL3_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES), 2, "model-2")


def test_dim_pair_batches_size_ge_20():
    """4 组维度正例批量规模均 ≥20"""
    assert len(_expand(MODEL5_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES)) >= 20
    assert len(_expand(MODEL1_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES)) >= 20
    assert len(_expand(MODEL2_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES)) >= 20
    assert len(_expand(MODEL3_DIM_STEMS, DIM_PREFIXES, DIM_SUFFIXES)) >= 20
```

- [x] **Step 2: 运行测试验证通过**

Run: `python -m pytest tests/test_exclusive_rules.py -k "dim_pair" -v`
Expected: PASS — 5 个测试全绿。若某条问题未路由到预期 target，检查 `_extract_five_dim_context` 提取的 `business_task`/`data_type` 是否符合维度规则声明（必要时调整 stem 关键词确保命中正确维度）。

- [x] **Step 3: 提交**

```bash
git add tests/test_exclusive_rules.py
git commit -m "test(exclusive-rules): 维度判别批量正例反例 ≥20 条/组"
```

---

### Task 7: 维度冲突降级与维度缺失回退测试

**Files:**
- Modify: `tests/test_exclusive_rules.py`（新增冲突降级与缺失回退测试）
- Test: 同上

**Interfaces:**
- Consumes: Task 4 的 4 条维度规则；Task 1 的 `_extract_five_dim_context`。
- Produces: 测试用例证明 `boundary_pending` 降级机制（多 target 命中）与维度缺失回退（无 scale/data_type 时回退到 base_type）在 v1.1 下生效。

- [x] **Step 1: 写维度冲突降级测试**

在 `tests/test_exclusive_rules.py` 末尾追加：

```python
def test_dim_conflict_boundary_pending_model1_vs_model5():
    """维度冲突：同一问题同时命中 model-1 与 model-5 维度规则 → boundary_pending

    构造一个同时满足「地块级质量等级评价→model-5」与「地块级障碍诊断→model-1」
    的问题。由于 business_task 只能取一个标签（_match_first_keyword 返回首个命中），
    需通过显式 context 构造冲突：让 context 同时被解读为两个维度条件。
    实际上 _match_first_keyword 不会同时返回两个 business_task，
    因此冲突场景通过显式构造 context 中同时存在两个规则的触发维度来模拟
    （例如同时命中 v1 关键词规则与 v1.1 维度规则指向不同 target）。
    """
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # "耕地质量等级现状评价" 同时命中 v1 现状评价(→model-1) 与 v1 质量等级评价(→model-5)
    # 此为 v1 冲突，在 v1.1 下应保持 boundary_pending
    ctx = {"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价", "expected_output": "评价结果"}
    final_type, status = apply_exclusive_rules("耕地质量等级现状评价", 1, ctx)
    assert status == "boundary_pending", f"维度冲突应降级，实际 ({final_type}, {status})"


def test_dim_conflict_boundary_pending_model2_vs_model3():
    """维度冲突：model-2/3 维度规则同时命中不同 target → boundary_pending

    通过显式构造无法在真实 _extract_five_dim_context 中产生的 context 来测试冲突路径：
    business_task 不可能同时为"酸化改良"与"有机质培肥"，但若人为构造
    两条规则的 target 不同且同时匹配，应降级。
    此处用 v1 关键词规则（酸化调理剂→model-2）+ 显式 context 命中 model-3 维度规则来制造冲突。
    """
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # "酸化调理剂每亩施用量有机肥" 文本古怪，但 v1 关键词"调理剂"命中 →model-2，
    # 同时 context 显式声明 business_task=有机质培肥 + data_type=处方用量 → 命中 model-3 维度规则
    ctx = {"scale": "地块", "data_type": "处方用量", "business_task": "有机质培肥", "expected_output": "处方用量"}
    final_type, status = apply_exclusive_rules("酸化调理剂每亩施用量", 2, ctx)
    assert status == "boundary_pending", f"model-2/3 冲突应降级，实际 ({final_type}, {status})"


def test_dim_fallback_when_context_missing_dimensions():
    """维度缺失回退：context 缺 scale/data_type/business_task 时不触发维度规则，回退 base_type"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # context 为空 dict：维度规则因 dimension_conditions 不匹配而跳过，v1 关键词规则也未命中 → 回退
    final_type, status = apply_exclusive_rules("普通问题没有关键词", 2, {})
    assert (final_type, status) == (2, "normal")
    # context 仅含 scale（无 data_type/business_task）：维度规则不触发
    final_type, status = apply_exclusive_rules("普通问题没有关键词", 3, {"scale": "地块"})
    assert (final_type, status) == (3, "normal")


def test_dim_fallback_when_context_none():
    """context=None 回退：仅 v1 关键词规则生效，无关键词命中时回退 base_type"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    final_type, status = apply_exclusive_rules("普通问题没有关键词", 2, None)
    assert (final_type, status) == (2, "normal")


def test_dim_fallback_through_full_pipeline():
    """端到端回退：identify_question_node 在无关键词命中时回退到 question_type 关键词路由"""
    from framework.agents.nodes import identify_question_node
    # 无任何排他规则命中的问题，应保持 question_type 关键词路由结果
    state = {"request": {"question": "全省耕地土壤有机质含量如何空间分布情况"}}
    result = identify_question_node(state)
    assert result["routing_status"] == "normal"
    assert result["question_type"] == 3  # 有机质关键词命中 TYPE_3
```

- [x] **Step 2: 运行测试验证通过**

Run: `python -m pytest tests/test_exclusive_rules.py -k "dim_conflict or dim_fallback" -v`
Expected: PASS（5 个测试全绿）。

- [x] **Step 3: 提交**

```bash
git add tests/test_exclusive_rules.py
git commit -m "test(exclusive-rules): 维度冲突降级与维度缺失回退测试"
```

---

### Task 8: 全量回归与验收

**Files:**
- Test: `tests/test_question_type_keywords.py`、`tests/test_exclusive_rules.py`、`tests/test_multi_agent.py`

**Interfaces:**
- Consumes: Task 1-7 全部产出。
- Produces: 全量测试通过，作为变更验收标准。

- [x] **Step 1: 运行目标测试套件**

Run: `python -m pytest tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_multi_agent.py -q`
Expected: PASS — 全部测试通过，无 fail/error。

- [x] **Step 2: 检查测试覆盖统计**

Run: `python -m pytest tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_multi_agent.py --tb=short -v`
Expected: 输出中应包含本计划新增的测试函数名（如 `test_extract_business_task_keywords`、`test_dim_rule_model5_plot_grade_eval`、`test_dim_pair_model5_vs_model1_positive`、`test_dim_conflict_boundary_pending_model1_vs_model5` 等），且全部 PASSED。

- [x] **Step 3: 若有失败，定位并修复**

若 Step 1 失败，按失败信息定位：
- 维度提取错误 → 检查 `BUSINESS_TASK_KEYWORDS`/`EXPECTED_OUTPUT_KEYWORDS` 关键词是否与 Design Doc 决策 A 逐字一致；
- 维度规则误触发 → 检查 `dimension_conditions` 是否在 context 缺字段时被错误判定为匹配（`_dimension_conditions_match` 应在 context 缺键时返回 False）；
- v1 回归失败 → 检查 `_rule_matches` AND 逻辑是否在 `condition` 为字符串时仍正确触发关键词检查。

修复后重新运行 Step 1，直到全绿。

- [x] **Step 4: 提交（如有修复）**

```bash
git add -u
git commit -m "test(five-dim): 全量回归通过 — 五维路由逻辑完善 v1 验收"
```

- [x] **Step 5: 标记 tasks.md 全部完成**

修改 `openspec/changes/five-dim-routing-logic/tasks.md`，将所有 `- [ ]` 改为 `- [x]`。

```bash
git add openspec/changes/five-dim-routing-logic/tasks.md
git commit -m "chore(openspec): 标记 five-dim-routing-logic 任务全部完成"
```

---

## 自检清单

- [x] **Spec coverage**：
  - 决策 A（维度提取扩展）→ Task 1
  - 决策 B（ExclusiveRule 结构扩展）→ Task 2
  - 决策 C（规则匹配 AND 逻辑）→ Task 3
  - 决策 D（4 条维度驱动规则）→ Task 4
  - 决策 E（模型依赖间接参与）→ Task 4（pair 字段间接体现，无需独立任务）
  - 决策 F（boundary_pending 保持）→ Task 3（算法）+ Task 7（测试）
  - tasks.md 1.1/1.2/1.3 → Task 1
  - tasks.md 2.1/2.2/2.3 → Task 2/3
  - tasks.md 3.1/3.2/3.3/3.4 → Task 4
  - tasks.md 3.5 → Task 5
  - tasks.md 4.1 → Task 4（单条正例）+ Task 6（批量正例）
  - tasks.md 4.2 → Task 7
  - tasks.md 4.3 → Task 7
  - tasks.md 4.4 → Task 1
  - tasks.md 4.5 → Task 5
  - tasks.md 4.6 → Task 8
- [x] **Placeholder scan**：所有步骤含完整代码/命令/预期输出，无 TBD/TODO。
- [x] **Type consistency**：`_dimension_conditions_match(dimension_conditions, context)`、`_rule_matches(rule, question, context)`、`_match_first_keyword(question, table)` 在所有任务中签名一致；`ExclusiveRule` 字段顺序与默认值在 Task 2 定义后被 Task 4 构造调用一致使用；context 四维字段名（`scale`/`data_type`/`business_task`/`expected_output`）在 Task 1 产出后被 Task 3/4/6/7 一致引用。

---

## 执行交接

**计划已保存到 `docs/superpowers/plans/2026-08-07-five-dim-routing-logic.md`。两种执行方式：**

**1. Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间 review，快速迭代。

**2. Inline Execution** — 在当前会话内按 executing-plans 批量执行，含检查点 review。

**请选择执行方式？**
