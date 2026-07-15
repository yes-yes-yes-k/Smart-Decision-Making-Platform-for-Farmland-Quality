from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader


# 模拟数据：11 个指标的障碍等级频数分布（1~10 级）
MOCK_INDICATOR_GRADES: Dict[str, List[int]] = {
    "pH": [2, 5, 8, 15, 20, 18, 12, 10, 6, 4],
    "有机质": [1, 3, 6, 10, 15, 20, 22, 15, 6, 2],
    "全氮": [1, 2, 5, 12, 18, 22, 20, 12, 6, 2],
    "有效磷": [3, 8, 12, 18, 22, 15, 10, 7, 3, 2],
    "速效钾": [5, 10, 15, 20, 22, 15, 8, 3, 1, 1],
    "阳离子交换量": [4, 8, 12, 18, 22, 18, 10, 5, 2, 1],
    "容重": [2, 6, 10, 15, 22, 20, 15, 6, 3, 1],
    "孔隙度": [2, 5, 10, 15, 22, 20, 15, 8, 2, 1],
    "黏粒含量": [1, 3, 8, 15, 25, 22, 15, 7, 3, 1],
    "耕层厚度": [3, 7, 12, 18, 22, 18, 12, 5, 2, 1],
    "灌溉保证率": [8, 15, 20, 22, 18, 10, 5, 1, 1, 0],
}


def _severity_score(grades: List[int]) -> float:
    """障碍严重度得分：等级越高（10级）权重越大。"""
    total = sum(grades)
    if total == 0:
        return 0.0
    weighted = sum((i + 1) * g for i, g in enumerate(grades))
    return round(weighted / total, 2)


class ProblemIdentificationAgent(BaseAgent):
    """模型3：耕地质量主要问题精准识别模型。"""

    def __init__(self):
        super().__init__(
            name="ProblemIdentificationAgent",
            description="识别主要/次要障碍因素和障碍组合",
            model_id="model-3",
            domain="problem",
        )
        self.dependencies = ["model-2"]

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        scores = {name: _severity_score(grades) for name, grades in MOCK_INDICATOR_GRADES.items()}
        sorted_factors = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary = [name for name, score in sorted_factors if score >= 6.0]
        secondary = [name for name, score in sorted_factors if 4.0 <= score < 6.0]

        combinations = []
        if "pH" in primary and "有机质" in primary:
            combinations.append("酸化-有机质贫瘠复合障碍")
        if "阳离子交换量" in primary and "pH" in primary:
            combinations.append("酸化-保肥力下降复合障碍")
        if "容重" in primary and "孔隙度" in primary:
            combinations.append("板结-透气性差复合障碍")

        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": {
                "primary_factors": primary,
                "secondary_factors": secondary,
                "combinations": combinations,
                "indicator_grades": MOCK_INDICATOR_GRADES,
                "severity_scores": scores,
            },
            "metadata": {"simulated": True},
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        rag_result = self._generate_with_rag(question)

        result = self.execute({})["result"]
        primary = result["primary_factors"]
        secondary = result["secondary_factors"]
        combinations = result["combinations"]

        model2 = context.get("model-2") if isinstance(context, dict) else None

        if rag_result.get("success") and rag_result.get("answer"):
            evidence = rag_result.get("sources", [])
            if not evidence:
                evidence = []
            evidence.append({
                "primary_factors": primary[:3],
                "note": "参考主要障碍因素"
            })
            return {
                "answer": rag_result["answer"],
                "evidence": evidence,
                "confidence": 0.83,
                "simulated": False,
                "sources": rag_result.get("sources", []),
            }

        # 消费 model-2 的 target_ph
        target_ph_note = ""
        if isinstance(model2, dict) and "target_ph" in model2:
            target_ph_note = f" 结合模型2目标 pH={model2['target_ph']}，"

        answer = (
            f"主要障碍因素：{', '.join(primary) if primary else '无明显主要障碍'}；"
            f"次要障碍因素：{', '.join(secondary) if secondary else '无明显次要障碍'}。"
            f"{target_ph_note}"
            f"障碍组合：{', '.join(combinations) if combinations else '无明显复合障碍'}。"
        )
        evidence = [
            {"factor": f, "severity": result["severity_scores"][f], "type": "primary"}
            for f in primary[:3]
        ]
        evidence.extend([
            {"combination": c} for c in combinations
        ])
        if isinstance(model2, dict) and "target_ph" in model2:
            evidence.append({"target_ph_from_model2": model2["target_ph"]})

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": 0.83,
        })
