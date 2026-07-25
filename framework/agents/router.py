from __future__ import annotations
from typing import Dict, List


# question_type → 单一智能体的 1:1 映射
# - type 1: 稳定性/退化风险 → model-1 (StabilityRiskAgent)
# - type 2: 酸化改良 → model-4 (AcidificationRemediationAgent)
# - type 3: 障碍诊断 → model-3 (ProblemIdentificationAgent)
# - type 4: 肥力/SOC/Dose → model-6 (FertilityMLAgent)
# - type 5: 耕地质量等级评价 → model-7 (FarmlandGradeAgent)
TYPE_AGENTS: Dict[int, List[str]] = {
    1: ["model-1"],
    2: ["model-4"],
    3: ["model-3"],
    4: ["model-6"],
    5: ["model-7"],
}


class QuestionTypeRouter:
    """基于问题类型的路由器，1:1 映射 question_type 到单一智能体。"""

    TYPE_AGENTS = TYPE_AGENTS

    def get_agents_for_type(self, question_type: int) -> List[str]:
        """返回该问题类型对应的智能体 ID 列表。未知类型返回空列表。"""
        return list(self.TYPE_AGENTS.get(question_type, []))
