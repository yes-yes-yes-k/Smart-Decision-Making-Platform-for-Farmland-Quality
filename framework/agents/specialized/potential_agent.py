from __future__ import annotations

from typing import Any, Dict

from ai_culti_demo.farmland_grade_eval import (
    run_county_potential,
    run_grade_evaluation,
    run_potential_analysis,
)

from ..base import BaseAgent


class PotentialAssessmentAgent(BaseAgent):
    """模型2：耕地质量等级与提升潜力真实评估。"""

    def __init__(self):
        super().__init__(
            name="PotentialAssessmentAgent",
            description="调用耕地质量评价引擎完成等级、障碍度和提升潜力评估",
            model_id="model-2",
            domain="potential",
        )

    @staticmethod
    def _error(code: str, message: str) -> Dict[str, Any]:
        return {
            "status": "error",
            "error": {"code": code, "message": message},
            "metadata": {"simulated": False},
        }

    @staticmethod
    def _wrap_engine_result(engine_result: Dict[str, Any]) -> Dict[str, Any]:
        if engine_result.get("status") != "ok":
            return {
                "status": "error",
                "error": engine_result.get("error", {
                    "code": "ENGINE_ERROR",
                    "message": "耕地质量评价引擎未返回有效结果。",
                }),
                "metadata": {"simulated": False},
            }

        return {
            "status": "ok",
            "result": {
                key: value for key, value in engine_result.items() if key != "status"
            },
            "metadata": {"simulated": False},
        }

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """根据问题类型调度真实质量等级或提升潜力计算。"""
        task = task or {}
        question_type = task.get("question_type")
        parcel_code = task.get("parcel_code")
        csv_path = task.get("csv_path")

        if question_type == 5:
            if not parcel_code:
                return self._error("MISSING_PARCEL_CODE", "质量等级评价需要提供 parcel_code。")
            return self._wrap_engine_result(
                run_grade_evaluation(parcel_code, dat_path=csv_path)
            )

        if question_type == 6:
            if parcel_code:
                return self._wrap_engine_result(
                    run_potential_analysis(parcel_code, csv_path=csv_path)
                )

            xqmc_code = task.get("xqmc_code")
            if xqmc_code is None:
                return self._error(
                    "MISSING_PARCEL_CODE",
                    "单地块提升潜力评估需要提供 parcel_code；县域评估请提供 xqmc_code。",
                )

            scenario = task.get("scenario")
            if scenario is None:
                return self._error("MISSING_SCENARIO", "县域提升潜力评估需要提供 scenario。")
            return self._wrap_engine_result(
                run_county_potential(xqmc_code, scenario, csv_path=csv_path)
            )

        return self._error(
            "UNSUPPORTED_QUESTION_TYPE",
            "模型2仅支持 question_type=5 或 question_type=6。",
        )

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """为直接调用者提供基于真实计算结果的简要答复。"""
        payload = dict(context or {})
        if isinstance(payload.get("data"), dict):
            payload = {**payload["data"], **payload}
        result = self.execute(payload)

        if result["status"] != "ok":
            error = result["error"]
            return {
                "answer": error["message"],
                "evidence": [{"code": error["code"]}],
                "confidence": 0.0,
                "simulated": False,
                "error": error,
            }

        data = result["result"]
        if "quality_grade" in data:
            answer = (
                f"耕地质量等级为{data['quality_grade']}，"
                f"综合指数为{data['composite_index']}。"
            )
            evidence = [
                {"metric": "质量等级", "value": data["quality_grade"]},
                {"metric": "综合指数", "value": data["composite_index"]},
            ]
        elif "full_potential" in data:
            answer = "已完成单地块耕地质量提升潜力评估。"
            evidence = [
                {"metric": "原始质量等级", "value": data["original"]["grade"]},
                {"metric": "全改良质量等级", "value": data["full_potential"]["grade"]},
            ]
        else:
            answer = "已完成县域耕地质量提升潜力情景评估。"
            evidence = [
                {"metric": "县域代码", "value": data["county_code"]},
                {"metric": "情景", "value": data["scenario"]},
            ]

        return {
            "answer": answer,
            "evidence": evidence,
            "confidence": 0.9,
            "simulated": False,
            "analysis": data,
        }
