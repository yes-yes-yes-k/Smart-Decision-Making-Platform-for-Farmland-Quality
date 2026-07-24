from __future__ import annotations
from typing import Any, Dict

from ..base import BaseAgent
from ..mock_data import MockDataLoader

# 尝试导入实际模型3实现
try:
    from ai_culti_demo.farmland_diagnosis import query_acidification, evaluate_acidification
    ACIDIFICATION_MODEL_AVAILABLE = True
except ImportError:
    ACIDIFICATION_MODEL_AVAILABLE = False


# 模拟输入参数
MOCK_INPUTS = {
    "ph": 5.5,
    "organic_matter": 25.0,
    "cec": 8.5,
    "clay_content": 35.0,
    "exchangeable_al": 3.2,
}

# 酸化程度阈值规则
ACIDIFICATION_RULES = [
    (lambda v: v < 4.5, "强酸性"),
    (lambda v: 4.5 <= v < 5.5, "酸性"),
    (lambda v: 5.5 <= v < 6.5, "弱酸性"),
    (lambda v: v >= 6.5, "正常"),
]

# 石灰施用量规则（kg/亩）
LIME_DOSAGE_RULES = {
    "强酸性": 150.0,
    "酸性": 100.0,
    "弱酸性": 50.0,
    "正常": 0.0,
}


class AcidificationRemediationAgent(BaseAgent):
    """模型4：耕地土壤酸化改良模型。"""

    def __init__(self):
        super().__init__(
            name="AcidificationRemediationAgent",
            description="判定酸化程度并计算调理剂施用量",
            model_id="model-4",
            domain="acidification",
        )

    def _compute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        data = MockDataLoader.merge_defaults(inputs, MOCK_INPUTS)
        ph = float(data["ph"])
        degree = MockDataLoader.apply_threshold(ph, ACIDIFICATION_RULES)
        lime_dosage = LIME_DOSAGE_RULES.get(degree, 0.0)
        ph_after = round(min(7.5, ph + 0.1 * (lime_dosage / 50.0) * 1.0), 2)
        return {
            "ph": ph,
            "degree": degree,
            "lime_dosage": lime_dosage,
            "ph_after_remediation": ph_after,
            "exchangeable_al": data["exchangeable_al"],
            "cec": data["cec"],
            "organic_matter": data["organic_matter"],
            "clay_content": data["clay_content"],
        }

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        computed = self._compute(task)
        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": computed,
            "metadata": {"simulated": True},
        })

    def _get_real_acidification(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """尝试获取实际酸化改良结果"""
        if not ACIDIFICATION_MODEL_AVAILABLE:
            return {}

        parcel_id = context.get("parcel_id") or context.get("data", {}).get("parcel_id")
        db_path = context.get("db_path") or context.get("data", {}).get("db_path")

        if not parcel_id:
            return {}

        try:
            result = query_acidification(parcel_id, db_path)
            if result.get("status") == "ok":
                return result.get("acidification", {})
        except Exception:
            pass

        return {}

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 检测实际模型可用但缺少地块 ID 的情况（用于附加提示）
        need_parcel_hint = False
        if ACIDIFICATION_MODEL_AVAILABLE:
            parcel_id = context.get("parcel_id") or context.get("data", {}).get("parcel_id")
            if not parcel_id:
                need_parcel_hint = True

        # 尝试使用实际酸化改良模型
        real_result = self._get_real_acidification(context)

        if real_result:
            acid_level = real_result.get("acidification_level", "未知")
            pH = real_result.get("pH", 5.5)
            lime_demand = real_result.get("lime_demand", 0)
            amendment_type = real_result.get("amendment_type", "有机肥")
            amendment_rate = real_result.get("amendment_rate", 0)
            need_amendment = real_result.get("need_amendment", False)

            if "酸化严重" in question or ("这块田" in question and "酸化" in question):
                answer = (
                    f"您的地块土壤 pH={pH}，酸化等级为{acid_level}。"
                    f"{'需要进行酸化改良。' if need_amendment else '无需酸化改良。'}"
                    f"（依据 GB/T 42817-2023：酸性 5.5≤pH<6.5、强酸性 4.5≤pH<5.5、极强酸性 pH<4.5）"
                )
                evidence = [
                    {"metric": "ph", "value": pH},
                    {"metric": "acidification_level", "value": acid_level},
                    {"standard": "GB/T 42817-2023"},
                ]
                confidence = 0.88
            elif "治理" in question or "调理剂" in question or "石灰" in question or "碱性材料" in question:
                answer = (
                    f"土壤酸化程度为{acid_level}，"
                    f"建议施{amendment_type} {amendment_rate} kg/亩，"
                    f"石灰需求量约 {lime_demand} kg/亩。"
                    f"（依据 GB/T 42817-2023 酸化等级判定与 NY/T 443-2019 调理剂施用量计算，"
                    f"分两次施用，结合翻耕作业）"
                )
                evidence = [
                    {"metric": "ph", "value": pH},
                    {"metric": "lime_demand", "value": lime_demand, "unit": "kg/亩"},
                    {"metric": "amendment_type", "value": amendment_type},
                    {"metric": "amendment_rate", "value": amendment_rate, "unit": "kg/亩"},
                    {"standard": "GB/T 42817-2023"},
                    {"standard": "NY/T 443-2019"},
                    {"recommendation": "分两次施用，结合翻耕作业"},
                ]
                confidence = 0.88
            elif "酸化程度" in question or "酸化等级" in question or "酸化现状" in question or "酸化" in question:
                answer = (
                    f"当前土壤 pH={pH}，酸化程度为{acid_level}。"
                    f"{'需要进行酸化改良。' if need_amendment else '无需酸化改良。'}"
                    f"（依据 GB/T 42817-2023 分级）"
                )
                evidence = [
                    {"metric": "ph", "value": pH},
                    {"metric": "acidification_level", "value": acid_level},
                    {"standard": "GB/T 42817-2023"},
                ]
                confidence = 0.88
            elif "酸化改良" in question or "改良方案" in question:
                answer = (
                    f"酸化改良方案：当前土壤 pH={pH}，酸化程度为{acid_level}。"
                    f"建议施{amendment_type} {amendment_rate} kg/亩，"
                    f"石灰需求量约 {lime_demand} kg/亩。"
                    f"预计治理后 pH 可提升至{real_result.get('target_pH', 6.5)}。"
                )
                evidence = [
                    {"metric": "ph", "value": pH},
                    {"metric": "acidification_level", "value": acid_level},
                    {"metric": "amendment_type", "value": amendment_type},
                    {"metric": "amendment_rate", "value": amendment_rate, "unit": "kg/亩"},
                    {"metric": "lime_demand", "value": lime_demand, "unit": "kg/亩"},
                    {"recommendation": real_result.get("reason", "")},
                ]
                confidence = 0.88
            else:
                answer = (
                    f"土壤 pH={pH}（{acid_level}），"
                    f"建议{amendment_type}施用量 {amendment_rate} kg/亩。"
                )
                evidence = [
                    {"metric": "ph", "value": pH},
                    {"metric": "acidification_level", "value": acid_level},
                    {"metric": "amendment_rate", "value": amendment_rate, "unit": "kg/亩"},
                ]
                confidence = 0.85

            return {
                "answer": answer,
                "evidence": evidence,
                "confidence": confidence,
                "simulated": False,
                "acidification_detail": real_result,
            }

        # 使用模拟数据回退
        inputs = {}
        if isinstance(context.get("data"), dict):
            inputs.update(context["data"])
        inputs.update({k: v for k, v in context.items() if k in MOCK_INPUTS})
        computed = self._compute(inputs)

        # 农户端：酸化严重吗（地块酸化等级）
        if "酸化严重" in question or ("这块田" in question and "酸化" in question):
            answer = (
                f"您的地块土壤 pH={computed['ph']}，酸化等级为{computed['degree']}。"
                f"（依据 GB/T 42817-2023：酸性 5.5≤pH<6.5、强酸性 4.5≤pH<5.5、极强酸性 pH<4.5）"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "degree", "value": computed["degree"]},
                {"standard": "GB/T 42817-2023"},
            ]
            confidence = 0.86
        # 不同土地利用类型酸化
        elif "土地利用类型" in question or "旱地" in question or "水田" in question or "园地" in question:
            answer = (
                f"不同土地利用类型酸化程度：当前样本 pH={computed['ph']}（{computed['degree']}）。"
                f"建议按旱地、水田、园地、林地分别统计酸化等级及比例"
                f"（依据 GB/T 42817-2023 分级）。"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "degree", "value": computed["degree"]},
                {"standard": "GB/T 42817-2023"},
            ]
            confidence = 0.84
        # 农户端：调理剂施用量（引用 GB/T 42817-2023 与 NY/T 443-2019）
        elif "治理" in question or "调理剂" in question or "石灰" in question or "碱性材料" in question:
            answer = (
                f"土壤酸化程度为{computed['degree']}，"
                f"建议施石灰 {computed['lime_dosage']} kg/亩，"
                f"预计治理后 pH 提升至 {computed['ph_after_remediation']}。"
                f"（依据 GB/T 42817-2023 酸化等级判定与 NY/T 443-2019 调理剂施用量计算，"
                f"分两次施用，结合翻耕作业）"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "exchangeable_al", "value": computed["exchangeable_al"], "unit": "cmol/kg"},
                {"metric": "lime_dosage", "value": computed["lime_dosage"], "unit": "kg/亩"},
                {"metric": "ph_after_remediation", "value": computed["ph_after_remediation"]},
                {"standard": "GB/T 42817-2023"},
                {"standard": "NY/T 443-2019"},
                {"recommendation": "分两次施用，结合翻耕作业"},
            ]
            confidence = 0.85
        # 酸化程度判定
        elif "酸化程度" in question or "酸化等级" in question or "酸化现状" in question or "酸化" in question:
            answer = (
                f"当前土壤 pH={computed['ph']}，酸化程度为{computed['degree']}。"
                f"交换性铝={computed['exchangeable_al']} cmol/kg。"
                f"（依据 GB/T 42817-2023 分级）"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "degree", "value": computed["degree"]},
                {"metric": "exchangeable_al", "value": computed["exchangeable_al"]},
                {"standard": "GB/T 42817-2023"},
            ]
            confidence = 0.88
        else:
            answer = (
                f"土壤 pH={computed['ph']}（{computed['degree']}），"
                f"建议石灰施用量 {computed['lime_dosage']} kg/亩。"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "lime_dosage", "value": computed["lime_dosage"]},
            ]
            confidence = 0.80

        response = {
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
        }
        # 实际模型可用但缺少地块 ID 时，附加提示（不阻断模拟回退）
        if need_parcel_hint:
            response["need_input"] = "parcel_id"
            response["hint"] = (
                "当前为模拟数据。提供地块 ID（parcel_id）后可获取真实酸化改良结果，"
                "例如：'地块 110105001 的酸化改良方案'。"
            )

        return MockDataLoader.mark_simulated(response)
