from __future__ import annotations
from typing import Any, Dict

from ..base import BaseAgent
from ..mock_data import MockDataLoader
from ...domain.other_models.model_4 import model_4_execution

# 模拟输入默认值（向后兼容保留 exchangeable_al）
MOCK_INPUTS = {
    "SJD": 5.5,
    "JHX": 1.56,
    "JLA": 4.08,
    "exchangeable_al": 4.08,  # 向后兼容
}


class AcidificationRemediationAgent(BaseAgent):
    """模型4：耕地土壤酸化改良（过程模型）。"""

    def __init__(self):
        super().__init__(
            name="AcidificationRemediationAgent",
            description="基于过程模型计算酸化改良剂需求量（YTK/MBNT）",
            model_id="model-4",
            domain="acidification",
        )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = task or {}
        land_type = task.get("land_type")
        fertilizer_type = task.get("fertilizer_type")
        result = model_4_execution(task, land_type=land_type, fertilizer_type=fertilizer_type)
        return MockDataLoader.mark_simulated({
            "status": result["status"],
            "result": {
                "ytk": result.get("ytk"),
                "mbnt": result.get("mbnt"),
                "sub_model": result.get("sub_model"),
                "customized_params": result.get("customized_params", {}),
            },
            "metadata": {
                "model_version": result.get("model_version"),
                "warning": result.get("warning"),
                "reason": result.get("reason"),
            },
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 从 context 提取数据并透传 land_type/fertilizer_type/parcel_id
        task = context.get("data", {}) or context.get("task", {}) or {}
        enriched = dict(task)
        for key in ("land_type", "fertilizer_type", "parcel_id", "parcel_code", "db_path"):
            if key in context and key not in enriched:
                enriched[key] = context[key]
        # 兜底 mock 输入
        for k, v in MOCK_INPUTS.items():
            enriched.setdefault(k, v)

        exec_result = self.execute(enriched)
        res = exec_result["result"]
        status = exec_result["status"]

        if status == "rejected":
            reason = exec_result["metadata"].get("reason", "")
            answer = f"无法计算酸化改良剂需求：{reason}。请提供 SJD（pH）、JHX（交换性氢）、JLA（交换性铝）。"
            return {"answer": answer, "evidence": [], "confidence": 0.5,
                    "acidification_detail": exec_result, **{"simulated": True}}

        ytk = res.get("ytk")
        mbnt = res.get("mbnt")
        sub_model = res.get("sub_model", "")
        land_type = enriched.get("land_type", "upland")
        fertilizer_type = enriched.get("fertilizer_type", "compound")

        if "治理" in question or "调理剂" in question or "石灰" in question or "改良" in question or "用量" in question:
            answer = (f"基于过程模型（{sub_model}）计算，建议亿土康（YTK）施用量约 {ytk:.1f} kg/ha，"
                      f"木本泥炭（MBNT）约 {mbnt:.1f} kg/ha（土地利用类型：{land_type}，肥料类型：{fertilizer_type}）。")
        elif "酸化程度" in question or "酸化等级" in question or "酸化" in question:
            answer = (f"当前土壤 pH={enriched.get('SJD')}，过程模型（{sub_model}）计算的改良剂需求："
                      f"亿土康 {ytk:.1f} kg/ha，木本泥炭 {mbnt:.1f} kg/ha。")
        else:
            answer = (f"酸化改良建议：亿土康 {ytk:.1f} kg/ha，木本泥炭 {mbnt:.1f} kg/ha（{sub_model}）。")

        evidence = [
            {"metric": "ytk", "value": ytk, "unit": "kg/ha"},
            {"metric": "mbnt", "value": mbnt, "unit": "kg/ha"},
            {"metric": "sub_model", "value": sub_model},
            {"metric": "land_type", "value": land_type},
            {"metric": "fertilizer_type", "value": fertilizer_type},
        ]
        warning = exec_result["metadata"].get("warning")
        if warning:
            evidence.append({"warning": warning})

        return {
            "answer": answer,
            "evidence": evidence,
            "confidence": 0.88,
            "acidification_detail": exec_result,
            "simulated": False,
        }
