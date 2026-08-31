from __future__ import annotations
from typing import Any, Dict
import logging

from ..base import BaseAgent, ProfessionalInputRejected
from ..mock_data import MockDataLoader
from ...domain.data.parcel_data_accessor import ParcelDataAccessor
from ...domain.other_models.model_4 import model_4_execution

logger = logging.getLogger(__name__)

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

    def _collect_inputs(self, context: dict) -> dict:
        """DB 优先获取地块指标，未命中时降级到 MOCK_INPUTS。"""
        parcel_id = context.get("parcel_id")

        if parcel_id:
            accessor = ParcelDataAccessor()
            indicators = accessor.get_parcel_indicators(str(parcel_id))
            if indicators is not None:
                inputs = dict(indicators)
                inputs["parcel_id"] = str(parcel_id)
                inputs["data_source"] = "db"
                return inputs

        logger.warning("Parcel %s not in DB, falling back to MOCK_INPUTS", parcel_id)
        inputs = self._collect_inputs_from_legacy(context)
        inputs["data_source"] = "fallback"
        return inputs

    def _collect_inputs_from_legacy(self, context: dict) -> dict:
        """原有数据源：MOCK_INPUTS 硬编码 + context 透传。"""
        enriched = dict(context)
        for k, v in MOCK_INPUTS.items():
            enriched.setdefault(k, v)
        return enriched

    def _build_result_record(self, execution_id: int, outputs: dict):
        """构建 AcidificationRemediationResult ORM 实例。legacy 路径无 parcel_id 时返回 None。"""
        from ...models.thematic_model import AcidificationRemediationResult

        parcel_id = outputs.get("parcel_id")
        if not parcel_id:
            return None
        result_data = outputs.get("result", outputs)
        return AcidificationRemediationResult(
            execution_id=execution_id,
            parcel_id=parcel_id,
            soil_ph=float(outputs.get("soil_ph", 0.0) or 0.0),
            soil_conditioner_dosage=float(result_data.get("ytk", 0.0) or 0.0),
            woody_peat_dosage=float(result_data.get("mbnt", 0.0) or 0.0),
            model_version=result_data.get("model_version", "unknown"),
            status=result_data.get("sub_model", "ok"),
            simulated=True,
        )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task = task or {}
        chat = task.get("execution_channel") == "chat"
        mode = task.get("calculation_mode") or (task.get("execution_context") or {}).get("analysis_context", {}).get("mode", "spatial")
        if chat and not task.get("guard_passed"):
            raise ProfessionalInputRejected("analysis_guard_required", "专业聊天执行必须先通过中央守卫")
        if chat and mode == "spatial" and not task.get("parcel_id"):
            raise ProfessionalInputRejected("verified_parcel_required", "空间计算需要已验证地块")
        if chat and mode == "scenario":
            required = ("SJD", "JHX", "JLA", "land_type", "fertilizer_type")
            missing = [name for name in required if task.get(name) is None]
            if missing:
                raise ProfessionalInputRejected("scenario_inputs_required", f"情景试算缺少输入: {', '.join(missing)}")
        inputs = self._collect_inputs(task)
        data_source = inputs.pop("data_source", "unknown")
        land_type = task.get("land_type") or inputs.get("land_type")
        fertilizer_type = task.get("fertilizer_type") or inputs.get("fertilizer_type")

        try:
            if chat and mode == "spatial" and data_source != "db":
                raise ProfessionalInputRejected("verified_parcel_required", "已验证地块未命中权威数据")
            if data_source == "db":
                # DB 路径：调用 calculate_acidification
                from framework.domain.calculations.acidification_calculation import calculate_acidification
                accessor = ParcelDataAccessor()
                mapped = accessor._map_indicators_to_inputs(inputs, "model-4")
                # 从 ParcelInfo 读取 land_type, fertilizer_type, target_ph
                try:
                    from framework.models.thematic_model import ParcelInfo
                    parcel = ParcelInfo.query.filter_by(parcel_id=str(inputs.get("parcel_id"))).first()
                except Exception:
                    parcel = None
                land_type = (parcel.land_type if parcel else None) or land_type or "upland"
                fertilizer_type = (parcel.fertilizer_type if parcel else None) or fertilizer_type or "compound"
                pHtarget = parcel.target_ph if parcel else None
                result = calculate_acidification(
                    SJD=mapped["SJD"] or 0.0, Hex=mapped["Hex"] or 0.0, Alex=mapped["Alex"] or 0.0,
                    land_type=land_type, fertilizer_type=fertilizer_type, pHtarget=pHtarget)
                outputs = {"parcel_id": inputs.get("parcel_id"), **result}
                status = "ok"
            else:
                # Legacy 路径：model_4_execution
                enriched = dict(inputs)
                if not (chat and mode == "scenario"):
                    for k, v in MOCK_INPUTS.items():
                        enriched.setdefault(k, v)

                result = model_4_execution(enriched, land_type=land_type, fertilizer_type=fertilizer_type)
                outputs = {
                    "parcel_id": inputs.get("parcel_id"),
                    "soil_ph": enriched.get("SJD"),
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
                }
                status = "degraded"

            persisted = self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id") or inputs.get("parcel_id"),
                inputs=inputs,
                outputs=outputs,
                status=status,
                execution_context=task.get("execution_context"),
            )

            if data_source == "db":
                return {
                    "status": "ok",
                    "simulated": False,
                    "result": outputs,
                    "metadata": {},
                    "data_source": data_source,
                    "persisted": persisted,
                }
            return {
                "status": result["status"],
                "simulated": False,
                "result": outputs["result"],
                "metadata": outputs["metadata"],
                "data_source": data_source,
                "persisted": persisted,
            }
        except Exception as e:
            self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id"),
                inputs=inputs,
                outputs={"error": str(e)},
                status="error",
                execution_context=task.get("execution_context"),
            )
            raise

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
                    "acidification_detail": exec_result, "simulated": True}

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
