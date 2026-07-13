from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader


# 模拟数据：11 个评价指标的当前值与潜在值
MOCK_INDICATORS: List[Dict[str, Any]] = [
    {"name": "pH", "current": 5.0, "potential": 6.5, "unit": ""},
    {"name": "有机质", "current": 22.0, "potential": 35.0, "unit": "g/kg"},
    {"name": "全氮", "current": 1.2, "potential": 2.0, "unit": "g/kg"},
    {"name": "有效磷", "current": 12.0, "potential": 25.0, "unit": "mg/kg"},
    {"name": "速效钾", "current": 80.0, "potential": 150.0, "unit": "mg/kg"},
    {"name": "阳离子交换量", "current": 8.5, "potential": 15.0, "unit": "cmol/kg"},
    {"name": "容重", "current": 1.45, "potential": 1.25, "unit": "g/cm³"},
    {"name": "孔隙度", "current": 45.0, "potential": 55.0, "unit": "%"},
    {"name": "黏粒含量", "current": 35.0, "potential": 35.0, "unit": "%"},
    {"name": "耕层厚度", "current": 15.0, "potential": 22.0, "unit": "cm"},
    {"name": "灌溉保证率", "current": 60.0, "potential": 90.0, "unit": "%"},
]

# 障碍度等级阈值
POTENTIAL_RULES = [
    (lambda v: v >= 75.0, "高潜力"),
    (lambda v: 40.0 <= v < 75.0, "中潜力"),
    (lambda v: v < 40.0, "低潜力"),
]


def _compute_obstacle_degree(current: float, potential: float, lower_is_better: bool = False) -> float:
    """计算障碍度值（0-100），值越大障碍越严重。"""
    if potential == current:
        return 0.0
    if lower_is_better:
        gap = max(0.0, current - potential)
        base = abs(current) if current != 0 else 1.0
    else:
        gap = max(0.0, potential - current)
        base = abs(potential) if potential != 0 else 1.0
    return round(min(100.0, gap / base * 100.0), 2)


class PotentialAssessmentAgent(BaseAgent):
    """模型2：耕地质量提升潜力评估模型。"""

    def __init__(self):
        super().__init__(
            name="PotentialAssessmentAgent",
            description="评估耕地质量提升潜力并计算障碍度值",
            model_id="model-2",
            domain="potential",
        )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        indicators = [dict(i) for i in MOCK_INDICATORS]
        for ind in indicators:
            lower_is_better = ind["name"] in ("容重",)
            ind["obstacle_degree"] = _compute_obstacle_degree(
                ind["current"], ind["potential"], lower_is_better
            )
            ind["potential_level"] = MockDataLoader.apply_threshold(
                100.0 - ind["obstacle_degree"], POTENTIAL_RULES
            )

        avg_obstacle = round(sum(i["obstacle_degree"] for i in indicators) / len(indicators), 2)
        overall_level = MockDataLoader.apply_threshold(100.0 - avg_obstacle, POTENTIAL_RULES)

        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": {
                "indicators": indicators,
                "average_obstacle_degree": avg_obstacle,
                "overall_potential_level": overall_level,
            },
            "metadata": {"simulated": True},
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        indicators = [dict(i) for i in MOCK_INDICATORS]
        for ind in indicators:
            lower_is_better = ind["name"] in ("容重",)
            ind["obstacle_degree"] = _compute_obstacle_degree(
                ind["current"], ind["potential"], lower_is_better
            )
            ind["potential_level"] = MockDataLoader.apply_threshold(
                100.0 - ind["obstacle_degree"], POTENTIAL_RULES
            )

        avg_obstacle = round(sum(i["obstacle_degree"] for i in indicators) / len(indicators), 2)
        overall_level = MockDataLoader.apply_threshold(100.0 - avg_obstacle, POTENTIAL_RULES)

        ph_indicator = next((i for i in indicators if i["name"] == "pH"), None)
        target_ph = ph_indicator["potential"] if ph_indicator else 6.5

        top_obstacles = sorted(indicators, key=lambda x: x["obstacle_degree"], reverse=True)[:3]

        answer = (
            f"耕地质量提升潜力等级为 {overall_level}，"
            f"平均障碍度值 {avg_obstacle}，"
            f"主要障碍因素：{', '.join(i['name'] for i in top_obstacles)}。"
        )
        evidence = [
            {"indicator": i["name"], "obstacle_degree": i["obstacle_degree"],
             "potential_level": i["potential_level"]}
            for i in top_obstacles
        ]
        evidence.append({"target_ph": target_ph, "recommendation": "目标 pH 供下游模型3使用"})

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": 0.80,
            "target_ph": target_ph,
        })
