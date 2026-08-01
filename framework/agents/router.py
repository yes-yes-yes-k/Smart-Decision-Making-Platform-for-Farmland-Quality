from __future__ import annotations
from typing import Dict, List
from .capabilities import CAPABILITY_BY_QUESTION_TYPE


# question_type → 单一专业智能体的 1:1 映射由统一能力目录生成。
TYPE_AGENTS: Dict[int, List[str]] = {
    question_type: [capability.agent_id]
    for question_type, capability in CAPABILITY_BY_QUESTION_TYPE.items()
}


class QuestionTypeRouter:
    """基于问题类型的路由器，1:1 映射 question_type 到单一智能体。"""

    TYPE_AGENTS = TYPE_AGENTS

    def get_agents_for_type(self, question_type: int) -> List[str]:
        """返回该问题类型对应的智能体 ID 列表。未知类型返回空列表。"""
        return list(self.TYPE_AGENTS.get(question_type, []))
