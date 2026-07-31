from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader
from ...domain.other_models.model_6 import model_6_execution


# 肥力相关关键词（与 AgentManager.FERTILITY_KEYWORDS 保持一致）
FERTILITY_KEYWORDS = [
    "有机碳", "SOC", "soc",
    "施用量", "施肥量", "施肥", "Dose", "dose", "剂量", "施多少肥",
    "肥力", "综合肥力",
    "秸秆", "有机肥", "培肥",
]

# Dose 关键词（优先级 1）
DOSE_KEYWORDS = ["施用量", "施肥量", "Dose", "剂量", "施多少肥", "施肥"]

# SOC 关键词（优先级 2）
SOC_KEYWORDS = ["有机碳", "SOC"]


class FertilityMLAgent(BaseAgent):
    """模型6：基于 ML 的耕地肥力 SOC/Dose 预测。"""

    def __init__(self):
        super().__init__(
            name="FertilityMLAgent",
            description="基于 ML 的耕地肥力 SOC/Dose 预测",
            model_id="model-6",
            domain="fertility_ml",
        )
        self.dependencies = []  # 独立 ML 模型，不依赖 model-4/5

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """调用 model_6_execution 执行 ML 预测，包装为三层结构。

        从 task 提取 land_type（默认 upland）透传给 model_6_execution。
        area_code 已在 task 字典中自然流转，无需额外传递。
        """
        land_type = (task or {}).get("land_type", "upland")
        result = model_6_execution(task or {}, land_type=land_type)
        return MockDataLoader.mark_simulated({
            "status": result["status"],
            "result": {
                "soc_prediction": result["soc_prediction"],
                "soc_confidence": result["soc_confidence"],
                "dose_prediction": result["dose_prediction"],
                "dose_confidence": result["dose_confidence"],
                "dose_warning": result["dose_warning"],
                "imputed_features": result["imputed_features"],
                "imputation_applied": result["imputation_applied"],
            },
            "metadata": {
                "model_version": result["model_version"],
                "fallback_reason": result.get("fallback_reason"),
                "reason": result.get("reason"),
                "out_of_range_features": result.get("out_of_range_features"),
            },
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """按关键词优先级处理问答：Dose > SOC > 综合/默认。

        从 context 顶层提取 area_code/land_type 注入 task（task 内已有值则不覆盖），
        确保 model_6_execution 能收到区域与土地类型信息。
        """
        task = context.get("data", {}) or context.get("task", {}) or {}
        enriched = dict(task)
        # 透传 context 顶层的 area_code/land_type（task 内已有值优先）
        if "area_code" in context and "area_code" not in enriched:
            enriched["area_code"] = context["area_code"]
        if "land_type" in context and "land_type" not in enriched:
            enriched["land_type"] = context["land_type"]

        exec_result = self.execute(enriched)
        pred = exec_result["result"]

        q_lower = question.lower()

        # 优先级 1：明确问 Dose / 施用量
        if any(kw.lower() in q_lower for kw in DOSE_KEYWORDS):
            return self._format_dose_only(pred, exec_result)

        # 优先级 2：明确问 SOC / 有机碳
        if any(kw.lower() in q_lower for kw in SOC_KEYWORDS):
            return self._format_soc_only(pred, exec_result)

        # 优先级 3：肥力 / 综合 / 其他
        return self._format_both(pred, exec_result)

    def _format_rejected(self, exec_result: Dict[str, Any]) -> Dict[str, Any]:
        """越界拒绝的统一格式化"""
        oor = exec_result["metadata"].get("out_of_range_features", [])
        oor_text = "; ".join([
            f"{f['feature']}={f['value']}（合法范围 {f['valid_range'][0]}-{f['valid_range'][1]}）"
            for f in oor
        ])
        return MockDataLoader.mark_simulated({
            "answer": f"输入值异常，无法预测。越界特征：{oor_text}。请检查输入后重试。",
            "evidence": [],
            "sources": [],
        })

    def _format_soc_only(self, pred: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
        if exec_result["status"] == "rejected":
            return self._format_rejected(exec_result)

        if exec_result["status"] == "fallback":
            confidence_text = "（模型不可用，返回训练集均值估算）"
        else:
            confidence_text = f"（置信度 {pred['soc_confidence']:.0%}）"

        return MockDataLoader.mark_simulated({
            "answer": f"基于 ML 预测，您的土壤有机碳（SOC）预测值约 {pred['soc_prediction']:.2f} g/kg{confidence_text}",
            "evidence": [
                {"metric": "soc_prediction", "value": pred["soc_prediction"], "unit": "g/kg"},
                {"metric": "soc_confidence", "value": pred["soc_confidence"]},
            ],
            "sources": [],
        })

    def _format_dose_only(self, pred: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
        if exec_result["status"] == "rejected":
            return self._format_rejected(exec_result)

        if exec_result["status"] == "fallback":
            confidence_text = "（模型不可用，返回训练集均值估算）"
        else:
            confidence_text = f"（置信度 {pred['dose_confidence']:.0%}，{pred['dose_warning']}）"

        return MockDataLoader.mark_simulated({
            "answer": f"基于 ML 预测，建议施肥量约 {pred['dose_prediction']:.2f} t/ha{confidence_text}",
            "evidence": [
                {"metric": "dose_prediction", "value": pred["dose_prediction"], "unit": "t/ha"},
                {"metric": "dose_confidence", "value": pred["dose_confidence"]},
            ],
            "sources": [],
        })

    def _format_both(self, pred: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
        if exec_result["status"] == "rejected":
            return self._format_rejected(exec_result)

        imputation_note = (
            "\n（注：部分特征用训练集均值填充，已标注于 imputed_features）"
            if pred["imputation_applied"] else ""
        )
        fallback_note = (
            "\n（模型不可用，以上为训练集均值估算）"
            if exec_result["status"] == "fallback" else ""
        )

        return MockDataLoader.mark_simulated({
            "answer": (
                f"耕地综合地力改良提升综合诊断（基于 ML 预测）：\n"
                f"- SOC（土壤有机碳）：{pred['soc_prediction']:.2f} g/kg（置信度 {pred['soc_confidence']:.0%}）\n"
                f"- Dose（施肥量）：{pred['dose_prediction']:.2f} t/ha（置信度 {pred['dose_confidence']:.0%}，{pred['dose_warning']}）"
                f"{imputation_note}{fallback_note}"
            ),
            "evidence": [
                {"metric": "soc_prediction", "value": pred["soc_prediction"], "unit": "g/kg"},
                {"metric": "soc_confidence", "value": pred["soc_confidence"]},
                {"metric": "dose_prediction", "value": pred["dose_prediction"], "unit": "t/ha"},
                {"metric": "dose_confidence", "value": pred["dose_confidence"]},
            ],
            "sources": [],
        })
