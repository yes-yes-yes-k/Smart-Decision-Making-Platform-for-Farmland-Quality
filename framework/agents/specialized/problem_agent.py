from __future__ import annotations
from typing import Any, Dict

from ..base import BaseAgent

# 尝试导入实际模型3实现
try:
    from ai_culti_demo.farmland_diagnosis import query_parcel, diagnose, DiagnosisStorage
    FARMland_DIAGNOSIS_AVAILABLE = True
except ImportError:
    FARMland_DIAGNOSIS_AVAILABLE = False


def _degraded_response(reason: str, message: str) -> Dict[str, Any]:
    """返回统一降级响应结构。"""
    return {
        "status": "degraded",
        "degraded": True,
        "reason": reason,
        "agent_id": "model-3",
        "model_id": "obstacle-diagnosis",
        "message": message,
    }


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
        if not FARMland_DIAGNOSIS_AVAILABLE:
            return _degraded_response(
                "model_unavailable",
                "模型3诊断模块未安装，无法执行真实诊断",
            )

        parcel_id = task.get("parcel_id") or task.get("data", {}).get("parcel_id")
        if not parcel_id:
            return _degraded_response(
                "missing_input",
                "缺少 parcel_id，无法查询真实诊断结果",
            )

        real_result = self._get_real_diagnosis(task)
        if not real_result:
            return _degraded_response(
                "import_failed",
                f"地块 {parcel_id} 的诊断数据未就绪或查询失败",
            )

        return {
            "status": "ok",
            "simulated": False,
            "result": real_result,
        }

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
        # 尝试使用实际诊断模型
        real_result = self._get_real_diagnosis(context)

        if real_result:
            diagnosis = real_result.get("diagnosis", {})
            evaluation = real_result.get("evaluation", {})
            obstacle_type = diagnosis.get("ZALX", "无明显障碍")
            main_factors_str = diagnosis.get("ZYZAYS", "")
            secondary_factors_str = diagnosis.get("CYZAYS", "")
            grade = evaluation.get("GDZLDJ", "未知")
            main_factors = [f for f in main_factors_str.split('；') if f and f != '无'] if main_factors_str else []
            secondary_factors = [f for f in secondary_factors_str.split('；') if f and f != '无'] if secondary_factors_str else []

            if "有没有问题" in question or ("我这块地" in question and "问题" in question):
                answer = (
                    f"您的地块耕地质量诊断结果：障碍类型为{obstacle_type}。"
                    f"主要障碍因素：{main_factors_str or '无'}。"
                    f"耕地质量等级：{grade}级。"
                )
                evidence = [{"factor": f, "type": "primary"} for f in main_factors[:3]]
                evidence.append({"grade": grade})
                confidence = 0.85
            elif "县" in question or "乡镇" in question or "方面" in question:
                answer = (
                    f"障碍诊断结果：障碍类型为{obstacle_type}；"
                    f"主要障碍因素：{main_factors_str or '无'}；"
                    f"次要障碍因素：{secondary_factors_str or '无'}。"
                    f"耕地质量等级：{grade}级。"
                )
                evidence = [{"factor": f, "type": "primary"} for f in main_factors[:3]]
                evidence.extend([{"factor": f, "type": "secondary"} for f in secondary_factors[:3]])
                confidence = 0.88
            else:
                answer = (
                    f"主要障碍因素：{main_factors_str or '无'}；"
                    f"次要障碍因素：{secondary_factors_str or '无'}。"
                    f"障碍类型：{obstacle_type}。"
                    f"耕地质量等级：{grade}级。"
                )
                evidence = [{"factor": f, "type": "primary"} for f in main_factors[:3]]
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

        # 真实诊断不可用时返回降级响应
        if not FARMland_DIAGNOSIS_AVAILABLE:
            reason = "model_unavailable"
            hint = "模型3诊断模块未安装"
        else:
            parcel_id = context.get("parcel_id") or context.get("data", {}).get("parcel_id")
            if not parcel_id:
                reason = "missing_input"
                hint = "提供地块 ID（parcel_id）后可获取真实诊断结果"
            else:
                reason = "import_failed"
                hint = f"地块 {parcel_id} 的诊断数据未就绪"

        return {
            "answer": f"当前无法提供真实诊断结果：{hint}。",
            "evidence": [],
            "confidence": 0.0,
            "simulated": False,
            "degraded": True,
            "reason": reason,
            "need_input": "parcel_id" if reason == "missing_input" else None,
        }
