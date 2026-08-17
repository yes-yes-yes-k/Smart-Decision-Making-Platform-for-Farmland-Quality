from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader

# 尝试导入实际 Python 模型实现
try:
    from ai_culti_demo.farmland_grade_eval import run_grade_evaluation
    GRADE_EVAL_AVAILABLE = True
except ImportError:
    GRADE_EVAL_AVAILABLE = False


class FarmlandGradeAgent(BaseAgent):
    """耕地质量等级评价智能体（Python 模型实现）"""

    def __init__(self):
        super().__init__(
            name="FarmlandGradeAgent",
            description="通过 Python 模型进行耕地质量等级评价",
            model_id="quality-grade-evaluation",
            domain="grade",
        )

    def execute(self, data: Dict[str, Any] = None) -> Dict[str, Any]:
        if not data:
            data = {}

        if not GRADE_EVAL_AVAILABLE:
            return {
                "status": "degraded",
                "degraded": True,
                "reason": "model_unavailable",
                "agent_id": "model-2",
                "model_id": "quality-grade-evaluation",
                "message": "模型2质量等级评价模块未安装，无法执行真实评价",
            }

        parcel_code = data.get("parcel_code")
        if not parcel_code:
            return {
                "status": "degraded",
                "degraded": True,
                "reason": "missing_input",
                "agent_id": "model-2",
                "model_id": "quality-grade-evaluation",
                "message": "缺少 parcel_code，无法查询真实质量等级结果",
            }

        exe_path = data.get("exe_path")
        dat_path = data.get("dat_path")
        try:
            result = run_grade_evaluation(parcel_code, exe_path, dat_path)
            if result.get("status") == "ok":
                return {"status": "ok", "simulated": False, "result": result}
        except Exception:
            pass

        return {
            "status": "degraded",
            "degraded": True,
            "reason": "import_failed",
            "agent_id": "model-2",
            "model_id": "quality-grade-evaluation",
            "message": f"地块 {parcel_code} 的质量等级数据未就绪或查询失败",
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
        # 检测实际模型可用但缺少地块代码的情况（用于附加提示）
        need_parcel_hint = False
        if GRADE_EVAL_AVAILABLE:
            parcel_code = context.get("parcel_code") or context.get("data", {}).get("parcel_code")
            if not parcel_code:
                need_parcel_hint = True

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

        # 真实质量等级结果不可用时返回统一降级响应
        if not GRADE_EVAL_AVAILABLE:
            reason = "model_unavailable"
            hint = "模型2质量等级评价模块未安装"
        else:
            parcel_code = context.get("parcel_code") or context.get("data", {}).get("parcel_code")
            if not parcel_code:
                reason = "missing_input"
                hint = "提供地块代码（parcel_code）后可获取真实质量等级评价结果"
            else:
                reason = "import_failed"
                hint = f"地块 {parcel_code} 的质量等级数据未就绪"

        return {
            "answer": f"当前无法提供真实质量等级评价结果：{hint}。",
            "evidence": [],
            "confidence": 0.0,
            "simulated": False,
            "degraded": True,
            "reason": reason,
            "need_input": "parcel_code" if reason == "missing_input" else None,
        }
