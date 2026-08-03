from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader

# 尝试导入实际模型1实现
try:
    from ai_culti_demo.farmland_stability import StabilityStorage, get_parcel_result
    STABILITY_MODEL_AVAILABLE = True
except ImportError:
    STABILITY_MODEL_AVAILABLE = False


class StabilityRiskAgent(BaseAgent):
    """模型1：耕地质量稳定性与退化风险评价智能体"""

    def __init__(self):
        super().__init__(
            name="StabilityRiskAgent",
            description="评价耕地质量等级稳定性并识别退化风险",
            model_id="stability-risk-evaluation",
            domain="stability",
        )

    def execute(self, data: Dict[str, Any] = None) -> Dict[str, Any]:
        if not data:
            data = {}

        # 尝试使用实际模型
        if STABILITY_MODEL_AVAILABLE:
            parcel_id = data.get("parcel_id")
            db_path = data.get("db_path")

            if parcel_id:
                storage = StabilityStorage(db_path)
                result = storage.get_result(parcel_id)
                if result:
                    return {"status": "ok", "result": result}

        # 模拟数据回退
        risk_levels = ["低风险", "中风险", "高风险", "极高风险"]
        risk_types = ["掉级风险", "关键因子退化", "退化集聚", "持续低质"]

        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": {
                "risk_level": risk_levels[0],
                "risk_score": 0.15,
                "risk_types": [risk_types[0]],
                "stability_score": 0.85,
                "stability_level": "稳定",
                "modules": {
                    1: {"name": "等级边界安全度", "score": 0.9},
                    2: {"name": "指标支撑均衡度", "score": 0.85},
                    3: {"name": "关键指标临界度", "score": 0.8},
                    4: {"name": "空间邻域一致性", "score": 0.95},
                    5: {"name": "历史变化趋势", "score": 0.88},
                    6: {"name": "掉级风险", "score": 0.15},
                    7: {"name": "关键因子退化", "score": 0.2},
                    8: {"name": "退化空间集聚", "score": 0.1},
                    9: {"name": "持续低质风险", "score": 0.05},
                }
            },
            "metadata": {"simulated": True},
        })

    def _get_real_stability(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """尝试获取实际稳定性评价结果"""
        if not STABILITY_MODEL_AVAILABLE:
            return {}

        parcel_id = context.get("parcel_id") or context.get("data", {}).get("parcel_id")
        db_path = context.get("db_path") or context.get("data", {}).get("db_path")

        if not parcel_id:
            return {}

        try:
            storage = StabilityStorage(db_path)
            if not storage.is_ready():
                return {}
            result = storage.get_result(parcel_id)
            if result:
                return result
        except Exception:
            pass

        return {}

    @staticmethod
    def _module_metric(
        result: Dict[str, Any], module: int, metric: str, default: float,
    ) -> float:
        """从稳定性结果库的模块分组结构读取数值指标。"""
        value = result.get(f"module_{module}", {}).get(metric, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 尝试使用实际模型
        real_result = self._get_real_stability(context)

        if real_result:
            stability_score = self._module_metric(
                real_result, 2, '指标支撑均衡度_绝对', 0.0,
            )
            drop_risk = self._module_metric(
                real_result, 6, '掉级风险_绝对', 0.0,
            )
            if drop_risk < 0.2:
                risk_level = "低风险"
            elif drop_risk < 0.5:
                risk_level = "中风险"
            else:
                risk_level = "高风险"

            if "稳定性" in question or "稳不稳" in question:
                answer = (
                    f"您的地块耕地质量稳定性评价结果：稳定性得分 {stability_score:.2f}，"
                    f"稳定性等级：{'稳定' if stability_score > 0.8 else '较稳定'}。"
                )
                evidence = [
                    {"metric": "稳定性得分", "value": stability_score},
                    {"metric": "稳定性等级", "value": "稳定" if stability_score > 0.8 else "较稳定"},
                ]
                confidence = 0.88
            elif "退化风险" in question or "掉级" in question:
                answer = (
                    f"退化风险评价结果：掉级风险得分 {drop_risk:.2f}，风险等级：{risk_level}。"
                    f"九模块评价均已完成，包括等级边界安全度、指标支撑均衡度等。"
                )
                evidence = [
                    {"metric": "掉级风险", "value": drop_risk},
                    {"metric": "风险等级", "value": risk_level},
                ]
                confidence = 0.85
            else:
                answer = (
                    f"稳定性评价结果：稳定性得分 {stability_score:.2f}，"
                    f"风险等级：{risk_level}。"
                    f"九模块评价均已完成。"
                )
                evidence = [
                    {"metric": "稳定性得分", "value": stability_score},
                    {"metric": "风险等级", "value": risk_level},
                ]
                confidence = 0.85

            return {
                "answer": answer,
                "evidence": evidence,
                "confidence": confidence,
                "simulated": False,
                "stability_detail": real_result,
            }

        # 使用模拟数据回退
        result = self.execute(data=context.get("data"))["result"]
        stability_score = result["stability_score"]
        risk_level = result["risk_level"]

        if "稳定性" in question or "稳不稳" in question:
            answer = (
                f"您的地块耕地质量稳定性评价结果：稳定性得分 {stability_score}，"
                f"稳定性等级：{result['stability_level']}。"
            )
            evidence = [
                {"metric": "稳定性得分", "value": stability_score},
                {"metric": "稳定性等级", "value": result["stability_level"]},
            ]
            confidence = 0.85
        elif "退化风险" in question or "掉级" in question:
            answer = (
                f"退化风险评价结果：风险等级 {risk_level}，风险得分 {result['risk_score']}。"
                f"风险类型：{', '.join(result['risk_types'])}。"
            )
            evidence = [
                {"metric": "风险等级", "value": risk_level},
                {"metric": "风险得分", "value": result["risk_score"]},
            ]
            confidence = 0.82
        else:
            answer = (
                f"稳定性评价结果：稳定性得分 {stability_score}，"
                f"风险等级：{risk_level}。"
                f"九模块评价均已完成。"
            )
            evidence = [
                {"metric": "稳定性得分", "value": stability_score},
                {"metric": "风险等级", "value": risk_level},
            ]
            confidence = 0.85

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
        })
