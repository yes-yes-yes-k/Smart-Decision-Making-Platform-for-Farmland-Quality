from __future__ import annotations
from typing import Any, Dict, List
import logging

from ..base import BaseAgent
from ..mock_data import MockDataLoader
from ...domain.data.parcel_data_accessor import ParcelDataAccessor

logger = logging.getLogger(__name__)


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

    def _collect_inputs(self, context: dict) -> dict:
        """DB 优先获取地块指标，未命中时降级到 MOCK_COUNTIES。"""
        parcel_id = context.get("parcel_id")

        if parcel_id:
            accessor = ParcelDataAccessor()
            indicators = accessor.get_parcel_indicators(str(parcel_id))
            if indicators is not None:
                inputs = self._map_indicators_to_inputs(indicators)
                inputs["parcel_id"] = str(parcel_id)
                inputs["data_source"] = "db"
                return inputs

        logger.warning("Parcel %s not in DB, falling back to MOCK_COUNTIES", parcel_id)
        inputs = self._collect_inputs_from_legacy(context)
        inputs["data_source"] = "fallback"
        return inputs

    def _collect_inputs_from_legacy(self, context: dict) -> dict:
        """原有数据源：MOCK_COUNTIES 硬编码。"""
        return {"counties": [dict(c) for c in MOCK_COUNTIES]}

    def _map_indicators_to_inputs(self, indicators: dict) -> dict:
        """将 soil_indicators JSON 映射为模型输入字段。"""
        return {
            "soil_ph": indicators.get("soil_ph"),
            "organic_matter": indicators.get("organic_matter"),
            "stability_score": indicators.get("stability_score"),
            "quality_grade": indicators.get("quality_grade"),
            "risk_index": indicators.get("risk_index"),
            "area_mu": indicators.get("area_mu"),
        }

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建 StabilityRiskResult ORM 实例。legacy 县区聚合路径无 parcel_id 时返回 None。"""
        from ...models.thematic_model import StabilityRiskResult

        parcel_id = outputs.get("parcel_id")
        if not parcel_id:
            return None
        return StabilityRiskResult(
            execution_id=execution_id,
            parcel_id=parcel_id,
            input_snapshot=outputs,
            simulated=True,
        )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        inputs = self._collect_inputs(task)
        data_source = inputs.pop("data_source", "unknown")

        try:
            if "counties" in inputs:
                # Legacy 路径：县区聚合
                counties = inputs["counties"]
                for c in counties:
                    c["stability"] = MockDataLoader.apply_threshold(
                        c["stability_score"], STABILITY_RULES
                    )
                outputs = {
                    "counties": counties,
                    "total_area_mu": sum(c["area_mu"] for c in counties),
                }
                status = "degraded"
            else:
                # DB 路径：单地块
                score = inputs.get("stability_score") or 70.0
                stability = MockDataLoader.apply_threshold(score, STABILITY_RULES)
                outputs = {
                    "parcel_id": inputs.get("parcel_id"),
                    "stability_score": score,
                    "stability": stability,
                    "soil_ph": inputs.get("soil_ph"),
                }
                status = "ok"

            persisted = self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id"),
                inputs=inputs,
                outputs=outputs,
                status=status,
            )

            return MockDataLoader.mark_simulated({
                "status": "ok",
                "result": outputs,
                "metadata": {"simulated": True, "data_source": data_source},
                "data_source": data_source,
                "persisted": persisted,
            })
        except Exception as e:
            self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id"),
                inputs=inputs,
                outputs={"error": str(e)},
                status="error",
            )
            raise

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        counties = [dict(c) for c in MOCK_COUNTIES]
        for c in counties:
            c["stability"] = MockDataLoader.apply_threshold(c["stability_score"], STABILITY_RULES)

        total_area = sum(c["area_mu"] for c in counties)
        stable_area = sum(c["area_mu"] for c in counties if c["stability"] == "稳定")
        general_area = sum(c["area_mu"] for c in counties if c["stability"] == "一般")
        weak_area = sum(c["area_mu"] for c in counties if c["stability"] == "较弱")

        # 农户端：通俗语言说明稳不稳
        if "稳不稳" in question or ("我的" in question and "田" in question and "稳定" not in question and "风险" not in question):
            plain = "比较稳" if stable_area >= general_area and stable_area >= weak_area else (
                "一般稳" if general_area >= weak_area else "不太稳")
            answer = (
                f"您的地块耕地质量等级稳定性为「{plain}」。"
                f"参考全县稳定性分布：稳定占比 {stable_area/total_area*100:.1f}%，"
                f"一般占比 {general_area/total_area*100:.1f}%，较弱占比 {weak_area/total_area*100:.1f}%。"
            )
            evidence = [
                {"metric": "稳定性类型", "value": plain},
                {"metric": "稳定面积占比", "value": f"{stable_area/total_area*100:.1f}%"},
            ]
            confidence = 0.80
        # 县域端：稳定性较弱片区清单
        elif "稳定性较弱" in question or "现场复核" in question or ("乡镇" in question and "地块" in question):
            weak_counties = sorted(
                [c for c in counties if c["stability"] == "较弱"],
                key=lambda c: c["stability_score"],
            )
            names = "、".join(c["name"] for c in weak_counties[:5]) or "无明显薄弱片区"
            answer = (
                f"本县稳定性较弱的乡镇/地块清单：{names}。"
                f"建议对上述区域现场复核当前等级、稳定性类型与是否接近等级边界。"
            )
            evidence = [
                {"county": c["name"], "stability": c["stability"],
                 "stability_score": c["stability_score"], "area_mu": c["area_mu"]}
                for c in weak_counties[:5]
            ]
            confidence = 0.82
        # 重点关注清单
        elif "关注清单" in question or "重点关注" in question:
            focus = sorted(
                [c for c in counties if c["risk_index"] >= 0.40 or c["stability"] == "较弱"],
                key=lambda c: c["risk_index"], reverse=True,
            )
            names = "、".join(c["name"] for c in focus[:5])
            answer = (
                f"建议纳入重点关注清单：{names}。"
                f"关注其等级稳定性、退化风险等级、风险类型与主要风险来源，"
                f"后续可调用模型2/3进行潜力与障碍诊断。"
            )
            evidence = [
                {"county": c["name"], "risk_index": c["risk_index"],
                 "stability": c["stability"], "risk_type": "退化风险" if c["risk_index"] >= 0.5 else "临界风险"}
                for c in focus[:5]
            ]
            confidence = 0.83
        # 省市端：稳定性总体评价
        elif "整体" in question or "稳定" in question:
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
        # 退化风险
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
