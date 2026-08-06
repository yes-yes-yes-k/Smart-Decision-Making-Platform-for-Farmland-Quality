"""排他规则模块（Task 2 将实现完整逻辑，此处为满足 routing 导入的最小脚手架）。"""
from __future__ import annotations
from typing import Optional, Tuple

ROUTING_STATUS_NORMAL = "normal"
ROUTING_STATUS_BOUNDARY_PENDING = "boundary_pending"

BOUNDARY_PENDING_MESSAGE = (
    "该问题的模型边界尚未由专业团队确认，系统返回「模型边界待确认」，"
    "暂不调用任一易混淆专业模型，请补充更明确的分析尺度或数据类型信息。"
)


def apply_exclusive_rules(
    question: str,
    question_type: int,
    context: Optional[dict] = None,
) -> Tuple[int, str]:
    """脚手架：暂不改变既有判定，返回 (question_type, ROUTING_STATUS_NORMAL)。"""
    return question_type, ROUTING_STATUS_NORMAL