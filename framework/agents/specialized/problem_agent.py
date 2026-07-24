from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader

# 尝试导入实际模型3实现
try:
    from ai_culti_demo.farmland_diagnosis import query_parcel, diagnose, DiagnosisStorage
    FARMland_DIAGNOSIS_AVAILABLE = True
except ImportError:
    FARMland_DIAGNOSIS_AVAILABLE = False


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

    def _get_real_diagnosis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """尝试获取实际诊断结果"""
        if not FARMland_DIAGNOSIS_AVAILABLE:
            return {}

        parcel_id = context.get("parcel_id") or context.get("data", {}).get("parcel_id")
        db_path = context.get("db_path") or context.get("data", {}).get("db_path")

        if not parcel_id:
            return {}

        try:
            result = query_parcel(parcel_id, db_path)
            if result.get("status") == "ok":
                return result
        except Exception:
            pass

        return {}

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 检测实际模型可用但缺少地块 ID 的情况（用于附加提示）
        need_parcel_hint = False
        if FARMland_DIAGNOSIS_AVAILABLE:
            parcel_id = context.get("parcel_id") or context.get("data", {}).get("parcel_id")
            if not parcel_id:
                need_parcel_hint = True

        # 尝试使用实际诊断模型
        real_result = self._get_real_diagnosis(context)

        if real_result:
            diagnosis = real_result.get("diagnosis", {})
            evaluation = real_result.get("evaluation", {})
            obstacle_type = diagnosis.get("obstacle_type", "无明显障碍")
            main_factors = diagnosis.get("main_factors", [])
            secondary_factors = diagnosis.get("secondary_factors", [])
            grade = evaluation.get("grade", "未知")

            if "有没有问题" in question or ("我这块地" in question and "问题" in question):
                answer = (
                    f"您的地块耕地质量诊断结果：障碍类型为{obstacle_type}。"
                    f"主要障碍因素：{'; '.join(main_factors) if main_factors else '无'}。"
                    f"耕地质量等级：{grade}级。"
                )
                evidence = [
                    {"factor": f, "type": "primary"}
                    for f in main_factors[:3]
                ]
                evidence.append({"grade": grade})
                confidence = 0.85
            elif "县" in question or "乡镇" in question or "方面" in question:
                answer = (
                    f"障碍诊断结果：障碍类型为{obstacle_type}；"
                    f"主要障碍因素：{'; '.join(main_factors) if main_factors else '无'}；"
                    f"次要障碍因素：{'; '.join(secondary_factors) if secondary_factors else '无'}。"
                    f"耕地质量等级：{grade}级。"
                )
                evidence = [
                    {"factor": f, "type": "primary"}
                    for f in main_factors[:3]
                ]
                evidence.extend([{"factor": f, "type": "secondary"} for f in secondary_factors[:3]])
                confidence = 0.88
            else:
                answer = (
                    f"主要障碍因素：{'; '.join(main_factors) if main_factors else '无'}；"
                    f"次要障碍因素：{'; '.join(secondary_factors) if secondary_factors else '无'}。"
                    f"障碍类型：{obstacle_type}。"
                    f"耕地质量等级：{grade}级。"
                )
                evidence = [
                    {"factor": f, "type": "primary"}
                    for f in main_factors[:3]
                ]
                evidence.extend([{"factor": f, "type": "secondary"} for f in secondary_factors[:3]])
                confidence = 0.88

            return {
                "answer": answer,
                "evidence": evidence,
                "confidence": confidence,
                "simulated": False,
                "diagnosis_detail": diagnosis,
                "evaluation_detail": evaluation,
            }

        # 使用模拟数据回退
        result = self.execute({})["result"]
        primary = result["primary_factors"]
        secondary = result["secondary_factors"]
        combinations = result["combinations"]

        # 消费 model-2 的 target_ph
        target_ph_note = ""
        model2 = context.get("model-2") if isinstance(context, dict) else None
        if isinstance(model2, dict) and "target_ph" in model2:
            target_ph_note = f" 结合模型2目标 pH={model2['target_ph']}，"

        # 农户端：简单语言说明
        if "有没有问题" in question or ("我这块地" in question and "问题" in question):
            answer = (
                f"您的地块耕地质量等级诊断：主要障碍为 {', '.join(primary) if primary else '无明显主要障碍'}。"
                f"低等级指标：{', '.join(primary[:3]) if primary else '无'}。"
            )
            evidence = [
                {"factor": f, "severity": result["severity_scores"][f], "type": "primary"}
                for f in primary[:3]
            ]
            confidence = 0.80
        # 县域端：障碍诊断统计
        elif "县" in question or "乡镇" in question or "方面" in question:
            answer = (
                f"县域障碍诊断：主要障碍因素 {', '.join(primary) if primary else '无明显主要障碍'}；"
                f"次要障碍因素 {', '.join(secondary) if secondary else '无明显次要障碍'}。"
                f"{target_ph_note}"
                f"每个指标按 1~10 级频数统计，最后一列标注是否主要/次要障碍因素。"
                f"障碍组合：{', '.join(combinations) if combinations else '无明显复合障碍'}。"
            )
            evidence = [
                {"factor": f, "severity": result["severity_scores"][f], "type": "primary"}
                for f in primary[:3]
            ]
            evidence.extend([{"combination": c} for c in combinations])
            if isinstance(model2, dict) and "target_ph" in model2:
                evidence.append({"target_ph_from_model2": model2["target_ph"]})
            confidence = 0.83
        # 省市端：主要问题/障碍因素识别
        else:
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
            evidence.extend([{"combination": c} for c in combinations])
            if isinstance(model2, dict) and "target_ph" in model2:
                evidence.append({"target_ph_from_model2": model2["target_ph"]})
            confidence = 0.83

        response = {
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
        }
        # 实际模型可用但缺少地块 ID 时，附加提示（不阻断模拟回退）
        if need_parcel_hint:
            response["need_input"] = "parcel_id"
            response["hint"] = (
                "当前为模拟数据。提供地块 ID（parcel_id）后可获取真实诊断结果，"
                "例如：'诊断地块 110105001 的障碍因素'。"
            )

        return MockDataLoader.mark_simulated(response)
