from __future__ import annotations
from typing import Any, Dict

from ..base import BaseAgent
from ..mock_data import MockDataLoader


# 模拟输入参数
MOCK_INPUTS = {
    "organic_matter": 22.0,      # g/kg
    "total_nitrogen": 1.2,        # g/kg
    "cn_ratio": 11.5,             # 碳氮比
    "clay_content": 35.0,         # %
}

# 有机质分级规则
ORGANIC_RULES = [
    (lambda v: v < 10.0, "极低"),
    (lambda v: 10.0 <= v < 20.0, "低"),
    (lambda v: 20.0 <= v < 30.0, "中"),
    (lambda v: 30.0 <= v < 40.0, "高"),
    (lambda v: v >= 40.0, "极高"),
]

# 有机肥施用量规则（kg/亩）
MANURE_DOSAGE_RULES = {
    "极低": 2000.0,
    "低": 1500.0,
    "中": 1000.0,
    "高": 500.0,
    "极高": 0.0,
}


class OrganicMatterAgent(BaseAgent):
    """模型5：耕地土壤有机质培肥提升模型。"""

    def __init__(self):
        super().__init__(
            name="OrganicMatterAgent",
            description="有机质提升评估与有机肥施用量计算",
            model_id="model-5",
            domain="organic_matter",
        )

    def _compute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        data = MockDataLoader.merge_defaults(inputs, MOCK_INPUTS)
        om = float(data["organic_matter"])
        level = MockDataLoader.apply_threshold(om, ORGANIC_RULES)
        manure_dosage = MANURE_DOSAGE_RULES.get(level, 0.0)
        # 简化预测：每施 1000 kg/亩 有机肥，有机质提升 1.5 g/kg
        potential_increase = round(manure_dosage / 1000.0 * 1.5, 2)
        return {
            "organic_matter": om,
            "level": level,
            "manure_dosage": manure_dosage,
            "potential_increase": potential_increase,
            "total_nitrogen": data["total_nitrogen"],
            "cn_ratio": data["cn_ratio"],
            "clay_content": data["clay_content"],
        }

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        computed = self._compute(task)
        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": computed,
            "metadata": {"simulated": True},
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        inputs = {}
        if isinstance(context.get("data"), dict):
            inputs.update(context["data"])
        inputs.update({k: v for k, v in context.items() if k in MOCK_INPUTS})
        computed = self._compute(inputs)

        # 县域端：本县有机质平均含量与低值区域
        if "本县" in question or "平均含量" in question:
            answer = (
                f"本县耕地土壤有机质平均含量 {computed['organic_matter']} g/kg，"
                f"等级为{computed['level']}。"
                f"低值区域为等级“极低”“低”的片区，建议作为培肥重点。"
            )
            evidence = [
                {"metric": "organic_matter", "value": computed["organic_matter"], "unit": "g/kg"},
                {"metric": "level", "value": computed["level"]},
                {"recommendation": "识别有机质低值区域并给出明确数值"},
            ]
            confidence = 0.83
        # 有机质低值原因
        elif "原因" in question and ("有机质" in question or "低" in question):
            answer = (
                f"耕地有机质含量低的原因：受土壤类型、气候、地形、耕作制度、"
                f"秸秆还田与施肥管理影响。当前有机质 {computed['organic_matter']} g/kg"
                f"（{computed['level']}），低有机质区域应作为后续培肥重点。"
            )
            evidence = [
                {"metric": "organic_matter", "value": computed["organic_matter"], "unit": "g/kg"},
                {"metric": "level", "value": computed["level"]},
                {"factors": "土壤类型/气候/地形/耕作制度/秸秆还田/施肥管理"},
            ]
            confidence = 0.80
        # 有机质含量评估（省市端）
        elif "含量" in question or "分布" in question or "现状" in question:
            answer = (
                f"全省耕地有机质含量平均 {computed['organic_matter']} g/kg，"
                f"等级为{computed['level']}。"
                f"全氮 {computed['total_nitrogen']} g/kg，碳氮比 {computed['cn_ratio']}。"
                f"空间分布建议按高/中/低等级占比与地形梯度分析。"
            )
            evidence = [
                {"metric": "organic_matter", "value": computed["organic_matter"], "unit": "g/kg"},
                {"metric": "level", "value": computed["level"]},
                {"metric": "total_nitrogen", "value": computed["total_nitrogen"], "unit": "g/kg"},
                {"metric": "cn_ratio", "value": computed["cn_ratio"]},
            ]
            confidence = 0.84
        # 有机肥/秸秆施用量
        elif "施用量" in question or "有机肥" in question or "秸秆" in question:
            answer = (
                f"有机质等级为{computed['level']}，"
                f"建议有机肥施用量 {computed['manure_dosage']} kg/亩，"
                f"秸秆还田参考同等养分替代量，"
                f"预期有机质提升 {computed['potential_increase']} g/kg。"
            )
            evidence = [
                {"metric": "organic_matter", "value": computed["organic_matter"], "unit": "g/kg"},
                {"metric": "manure_dosage", "value": computed["manure_dosage"], "unit": "kg/亩"},
                {"metric": "potential_increase", "value": computed["potential_increase"], "unit": "g/kg"},
                {"recommendation": "优先选用腐熟农家肥或商品有机肥，分季施用"},
            ]
            confidence = 0.82
        else:
            answer = (
                f"有机质 {computed['organic_matter']} g/kg（{computed['level']}），"
                f"建议施有机肥 {computed['manure_dosage']} kg/亩。"
            )
            evidence = [
                {"metric": "level", "value": computed["level"]},
                {"metric": "manure_dosage", "value": computed["manure_dosage"]},
            ]
            confidence = 0.78

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
        })
