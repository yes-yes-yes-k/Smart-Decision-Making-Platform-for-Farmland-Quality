"""数据驱动的排他规则配置与判定。

用于消除 model-2/3、model-4/5 两组易混淆对的误选。
排他规则无法消解重叠（优先级冲突）时返回「模型边界待确认」显式降级，
不自行选择任一易混淆专业 Agent。
"""
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


# 条件短语 → 触发关键词（子串匹配）
EXCLUSIVE_CONDITION_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "现状评价": ("现状评价", "现状如何", "现状诊断", "现状评估"),
    "酸化调理剂": ("调理剂", "石灰", "碱性材料", "木本泥炭", "酸性改良"),
    "稳定性风险": ("稳定性", "退化风险", "掉级", "重点关注清单", "等级稳定"),
    "质量等级评价": ("质量等级", "等级评价", "综合指数", "等级评定", "评价结果"),
}

EXCLUSIVE_RULES: Tuple[ExclusiveRule, ...] = (
    # ===== v1 纯关键词规则（向后兼容，dimension_conditions 为空）=====
    # model-2 vs model-3：现状评价 → model-3（障碍诊断）
    ExclusiveRule(frozenset({"model-2", "model-3"}), "业务任务", "现状评价", "model-3"),
    # model-4 vs model-5：酸化调理剂 → model-4（酸化改良）
    ExclusiveRule(frozenset({"model-4", "model-5"}), "业务任务", "酸化调理剂", "model-4"),
    # model-1：稳定性风险 → model-1
    ExclusiveRule(frozenset({"model-1"}), "业务任务", "稳定性风险", "model-1"),
    # model-2：质量等级评价 → model-2
    ExclusiveRule(frozenset({"model-2"}), "预期输出", "质量等级评价", "model-2"),

    # ===== v1.1 维度驱动规则（condition=None，仅依赖 dimension_conditions）=====
    # model-2/3：地块级质量等级评价 → model-2（五维全量参与：scale+data_type+business_task+expected_output）
    ExclusiveRule(
        frozenset({"model-2", "model-3"}),
        "分析尺度+数据类型+业务任务+预期输出",
        None,
        "model-2",
        dimension_conditions={"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价", "expected_output": "评价结果"},
    ),
    # model-2/3：地块级障碍诊断 → model-3（加 expected_output 收敛，避免裸词跨域误触）
    ExclusiveRule(
        frozenset({"model-2", "model-3"}),
        "分析尺度+业务任务+预期输出",
        None,
        "model-3",
        dimension_conditions={"scale": "地块", "business_task": "障碍诊断", "expected_output": "诊断报告"},
    ),
    # model-4/5：酸化调理剂用量 → model-4
    ExclusiveRule(
        frozenset({"model-4", "model-5"}),
        "数据类型+业务任务",
        None,
        "model-4",
        dimension_conditions={"data_type": "处方用量", "business_task": "酸化改良"},
    ),
    # model-4/5：有机肥施用量 → model-5
    ExclusiveRule(
        frozenset({"model-4", "model-5"}),
        "数据类型+业务任务",
        None,
        "model-5",
        dimension_conditions={"data_type": "处方用量", "business_task": "有机质培肥"},
    ),
)


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
    - routing_status == "boundary_pending"：规则优先级冲突、重叠无法消解，显式降级，
      不调用任何易混淆专业 Agent。
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