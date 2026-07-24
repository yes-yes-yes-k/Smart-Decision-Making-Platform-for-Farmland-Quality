from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader

# 尝试导入实际exe模型实现
try:
    from ai_culti_demo.farmland_grade_eval import run_grade_evaluation
    GRADE_EVAL_AVAILABLE = True
except ImportError:
    GRADE_EVAL_AVAILABLE = False


class FarmlandGradeAgent(BaseAgent):
    """耕地质量等级评价智能体（调用Fortran exe）"""

    def __init__(self):
        super().__init__("FarmlandGradeAgent")

    def execute(self, data: Dict[str, Any] = None) -> Dict[str, Any]:
        if not data:
            data = {}

        # 尝试使用实际exe模型
        if GRADE_EVAL_AVAILABLE:
            parcel_code = data.get("parcel_code")
            exe_path = data.get("exe_path")
            dat_path = data.get("dat_path")

            if parcel_code:
                result = run_grade_evaluation(parcel_code, exe_path, dat_path)
                if result.get("status") == "ok":
                    return {"status": "ok", "result": result}

        # 模拟数据回退
        indicators = [
            {"name": "pH", "raw_value": 6.5, "membership": 0.95, "weight": 0.1},
            {"name": "有机质", "raw_value": 25.0, "membership": 0.85, "weight": 0.15},
            {"name": "有效磷", "raw_value": 30.0, "membership": 0.9, "weight": 0.12},
            {"name": "速效钾", "raw_value": 150.0, "membership": 0.88, "weight": 0.12},
        ]

        obstacle_degree = [
            {"rank": 1, "indicator": "有效磷", "degree": 0.15},
            {"rank": 2, "indicator": "速效钾", "degree": 0.12},
        ]

        return {
            "status": "ok",
            "result": {
                "parcel_code": data.get("parcel_code", "unknown"),
                "quality_grade": "3",
                "composite_index": 0.78,
                "indicators": indicators,
                "obstacle_degree": obstacle_degree,
            }
        }

    def _get_real_grade(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """尝试获取实际质量等级评价结果"""
        if not GRADE_EVAL_AVAILABLE:
            return {}

        parcel_code = context.get("parcel_code") or context.get("data", {}).get("parcel_code")
        exe_path = context.get("exe_path") or context.get("data", {}).get("exe_path")
        dat_path = context.get("dat_path") or context.get("data", {}).get("dat_path")

        if not parcel_code:
            return {}

        try:
            result = run_grade_evaluation(parcel_code, exe_path, dat_path)
            if result.get("status") == "ok":
                return result
        except Exception:
            pass

        return {}

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 尝试使用实际模型
        real_result = self._get_real_grade(context)

        if real_result:
            grade = real_result.get("quality_grade", "未知")
            composite_index = real_result.get("composite_index", 0)
            indicators = real_result.get("indicators", [])
            obstacle_degree = real_result.get("obstacle_degree", [])

            if "质量等级" in question or "等级评价" in question:
                answer = (
                    f"耕地质量等级评价结果：质量等级为{grade}级，"
                    f"综合指数：{composite_index}。"
                    f"共{len(indicators)}个指标参与评价。"
                )
                evidence = [
                    {"metric": "质量等级", "value": grade},
                    {"metric": "综合指数", "value": composite_index},
                ]
                confidence = 0.90
            elif "障碍度" in question or "障碍" in question:
                obstacle_str = "; ".join([f"{o['indicator']}({o['degree']})" for o in obstacle_degree]) or "无明显障碍"
                answer = (
                    f"障碍度排序结果：{obstacle_str}。"
                    f"质量等级为{grade}级。"
                )
                evidence = [
                    {"metric": "质量等级", "value": grade},
                    {"metric": "障碍度排序", "value": obstacle_str},
                ]
                confidence = 0.88
            elif "综合指数" in question:
                answer = (
                    f"综合指数评价结果：{composite_index}，"
                    f"对应质量等级为{grade}级。"
                )
                evidence = [
                    {"metric": "综合指数", "value": composite_index},
                    {"metric": "质量等级", "value": grade},
                ]
                confidence = 0.90
            else:
                answer = (
                    f"耕地质量等级评价结果：质量等级为{grade}级，"
                    f"综合指数：{composite_index}。"
                )
                evidence = [
                    {"metric": "质量等级", "value": grade},
                    {"metric": "综合指数", "value": composite_index},
                ]
                confidence = 0.88

            return {
                "answer": answer,
                "evidence": evidence,
                "confidence": confidence,
                "simulated": False,
                "grade_detail": real_result,
            }

        # 使用模拟数据回退
        result = self.execute(data=context.get("data"))["result"]
        grade = result["quality_grade"]
        composite_index = result["composite_index"]

        if "质量等级" in question or "等级评价" in question:
            answer = (
                f"耕地质量等级评价结果：质量等级为{grade}级，"
                f"综合指数：{composite_index}。"
            )
            evidence = [
                {"metric": "质量等级", "value": grade},
                {"metric": "综合指数", "value": composite_index},
            ]
            confidence = 0.85
        elif "障碍度" in question or "障碍" in question:
            obstacle_str = "; ".join([f"{o['indicator']}({o['degree']})" for o in result.get("obstacle_degree", [])]) or "无明显障碍"
            answer = (
                f"障碍度排序结果：{obstacle_str}。"
                f"质量等级为{grade}级。"
            )
            evidence = [
                {"metric": "质量等级", "value": grade},
                {"metric": "障碍度排序", "value": obstacle_str},
            ]
            confidence = 0.82
        else:
            answer = (
                f"耕地质量等级评价结果：质量等级为{grade}级，"
                f"综合指数：{composite_index}。"
            )
            evidence = [
                {"metric": "质量等级", "value": grade},
                {"metric": "综合指数", "value": composite_index},
            ]
            confidence = 0.85

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
        })
