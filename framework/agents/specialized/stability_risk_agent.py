from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader


# 模拟数据：10 个县区的质量等级、稳定性评分、退化风险指数
MOCK_COUNTIES: List[Dict[str, Any]] = [
    {"name": "乐昌县", "quality_grade": 4, "stability_score": 78.5, "risk_index": 0.32, "area_mu": 320000},
    {"name": "南雄县", "quality_grade": 3, "stability_score": 65.2, "risk_index": 0.48, "area_mu": 280000},
    {"name": "仁化县", "quality_grade": 5, "stability_score": 82.1, "risk_index": 0.18, "area_mu": 210000},
    {"name": "始兴县", "quality_grade": 4, "stability_score": 70.0, "risk_index": 0.42, "area_mu": 190000},
    {"name": "翁源县", "quality_grade": 3, "stability_score": 58.4, "risk_index": 0.61, "area_mu": 250000},
    {"name": "新丰县", "quality_grade": 2, "stability_score": 50.3, "risk_index": 0.72, "area_mu": 160000},
    {"name": "乳源县", "quality_grade": 4, "stability_score": 75.6, "risk_index": 0.29, "area_mu": 180000},
    {"name": "浈江区", "quality_grade": 3, "stability_score": 62.8, "risk_index": 0.55, "area_mu": 95000},
    {"name": "武江区", "quality_grade": 4, "stability_score": 73.4, "risk_index": 0.35, "area_mu": 110000},
    {"name": "曲江区", "quality_grade": 3, "stability_score": 60.7, "risk_index": 0.58, "area_mu": 220000},
]

# 稳定性阈值规则
STABILITY_RULES = [
    (lambda v: v >= 75.0, "稳定"),
    (lambda v: 60.0 <= v < 75.0, "一般"),
    (lambda v: v < 60.0, "较弱"),
]


class StabilityRiskAgent(BaseAgent):
    """模型1：耕地质量等级稳定性与退化风险识别模型。"""

    def __init__(self):
        super().__init__(
            name="StabilityRiskAgent",
            description="评价耕地质量等级稳定性并识别退化风险",
            model_id="model-1",
            domain="stability",
        )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        counties = [dict(c) for c in MOCK_COUNTIES]
        for c in counties:
            c["stability"] = MockDataLoader.apply_threshold(c["stability_score"], STABILITY_RULES)

        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": {
                "counties": counties,
                "total_area_mu": sum(c["area_mu"] for c in counties),
            },
            "metadata": {"simulated": True},
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        counties = [dict(c) for c in MOCK_COUNTIES]
        for c in counties:
            c["stability"] = MockDataLoader.apply_threshold(c["stability_score"], STABILITY_RULES)

        total_area = sum(c["area_mu"] for c in counties)
        stable_area = sum(c["area_mu"] for c in counties if c["stability"] == "稳定")
        general_area = sum(c["area_mu"] for c in counties if c["stability"] == "一般")
        weak_area = sum(c["area_mu"] for c in counties if c["stability"] == "较弱")

        if "整体" in question or "稳定" in question:
            answer = (
                f"全省耕地质量稳定性总体评价：稳定占比 {stable_area/total_area*100:.1f}%，"
                f"一般占比 {general_area/total_area*100:.1f}%，"
                f"较弱占比 {weak_area/total_area*100:.1f}%。"
            )
            evidence = [
                {"metric": "稳定面积占比", "value": f"{stable_area/total_area*100:.1f}%"},
                {"metric": "一般面积占比", "value": f"{general_area/total_area*100:.1f}%"},
                {"metric": "较弱面积占比", "value": f"{weak_area/total_area*100:.1f}%"},
                {"recommendation": "对较弱区域优先纳入退化风险重点关注清单"},
            ]
            confidence = 0.85
        elif "退化风险" in question or "风险" in question:
            risk_counties = sorted(
                [c for c in counties if c["quality_grade"] >= 4 and c["risk_index"] >= 0.35],
                key=lambda c: c["risk_index"],
                reverse=True,
            )
            names = "、".join(c["name"] for c in risk_counties[:3])
            answer = f"高等级耕地存在退化风险的县区（按风险指数降序）：{names}。"
            evidence = [
                {"county": c["name"], "risk_index": c["risk_index"], "area_mu": c["area_mu"]}
                for c in risk_counties[:5]
            ]
            confidence = 0.82
        else:
            answer = "已返回全省 10 个县区的质量等级、稳定性评分与退化风险指数（模拟数据）。"
            evidence = [{"county": c["name"], "stability": c["stability"]} for c in counties[:5]]
            confidence = 0.75

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
        })
