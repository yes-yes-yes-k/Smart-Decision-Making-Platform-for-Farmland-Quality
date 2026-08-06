"""数据驱动的排他规则配置与判定。

用于消除 model-3/7、model-2/7、model-4/6 三组易混淆对的误选。
排他规则无法消解重叠（优先级冲突）时返回「模型边界待确认」显式降级，
不自行选择任一易混淆专业 Agent。
"""
from __future__ import annotations
from dataclasses import dataclass
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

    当问题命中 condition 时，将易混淆对判定到 target 模型。
    pair 仅用于文档化该规则所属的易混淆模型对。
    """
    pair: FrozenSet[str]
    discriminator: str   # 判别维度：业务任务/分析尺度/数据类型/预期输出/模型依赖
    condition: str       # 条件短语（对应 EXCLUSIVE_CONDITION_KEYWORDS 中的键）
    target: str          # 目标 model_id


# 条件短语 → 触发关键词（子串匹配）
EXCLUSIVE_CONDITION_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "现状评价": ("现状评价", "现状如何", "现状诊断", "现状评估"),
    "潜力": ("潜力", "提升空间", "增产潜力", "目标等级"),
    "有机质投入量": ("施多少", "每亩施", "施用量", "投入量", "用量"),
    "酸化调理剂": ("调理剂", "石灰", "碱性材料", "木本泥炭", "酸性改良"),
    "稳定性风险": ("稳定性", "退化风险", "掉级", "重点关注清单", "等级稳定"),
    "质量等级评价": ("质量等级", "等级评价", "综合指数", "等级评定", "评价结果"),
}

EXCLUSIVE_RULES: Tuple[ExclusiveRule, ...] = (
    # model-3 vs model-7：现状评价 → model-3（障碍诊断）
    ExclusiveRule(frozenset({"model-3", "model-7"}), "业务任务", "现状评价", "model-3"),
    # model-2 vs model-7：潜力 → model-2（潜力评估）
    ExclusiveRule(frozenset({"model-2", "model-7"}), "业务任务", "潜力", "model-2"),
    # model-4 vs model-6：有机质投入量 → model-6（SOC/Dose 预测）
    ExclusiveRule(frozenset({"model-4", "model-6"}), "预期输出", "有机质投入量", "model-6"),
    # model-4 vs model-6：酸化调理剂 → model-4（酸化改良）
    ExclusiveRule(frozenset({"model-4", "model-6"}), "业务任务", "酸化调理剂", "model-4"),
    # model-1：稳定性风险 → model-1
    ExclusiveRule(frozenset({"model-1"}), "业务任务", "稳定性风险", "model-1"),
    # model-7：质量等级评价 → model-7
    ExclusiveRule(frozenset({"model-7"}), "预期输出", "质量等级评价", "model-7"),
)


def _condition_matches(question: str, condition: str) -> bool:
    for kw in EXCLUSIVE_CONDITION_KEYWORDS.get(condition, ()):
        if kw in question:
            return True
    return False


def model_id_to_question_type(model_id: str) -> Optional[int]:
    # "model-1".."model-7" 在 capabilities 注册表中登记为 agent_id，据此反查 question_type
    capability = CAPABILITY_BY_AGENT_ID.get(model_id)
    return capability.question_type if capability else None


def apply_exclusive_rules(
    question: str,
    question_type: int,
    context: Optional[dict] = None,
) -> Tuple[int, str]:
    """应用排他规则判定，返回 (question_type, routing_status)。

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
        if _condition_matches(question, rule.condition)
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