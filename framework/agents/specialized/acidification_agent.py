from __future__ import annotations
from typing import Any, Dict
import logging

from ..base import BaseAgent, ProfessionalInputRejected
from ..mock_data import MockDataLoader
from ...domain.data.parcel_data_accessor import ParcelDataAccessor
from ...domain.other_models.model_4 import model_4_execution
from ...domain.provenance import (
    IMPUTED_INPUT,
    MODEL4_INPUT_SOURCES,
    SOURCE_DEFAULT,
    imputed_fields,
    provenance_map,
)

logger = logging.getLogger(__name__)

# 模拟输入默认值（向后兼容保留 exchangeable_al）
MOCK_INPUTS = {
    "SJD": 5.5,
    "JHX": 1.56,
    "JLA": 4.08,
    "exchangeable_al": 4.08,  # 向后兼容
}

#: 输入不可信时置空的定量结论字段（酸缓冲量与两项用量）。
QUANTITATIVE_RESULT_FIELDS = ("Aback", "YTK", "MBNT")


def _imputed_model4_inputs(parcel, mapped) -> list[str]:
    """列出 Model-4 输入中被区域平均回填或使用默认值的字段。

    返回 ``soil_indicators`` 字段名（如 ``exchangeable_aluminum``）；目标 pH 与
    肥料类型缺失或标记为默认来源时补充 ``target_ph``、``fertilizer_type``。
    """
    indicators = getattr(parcel, "soil_indicators", None) if parcel is not None else None
    imputed = imputed_fields(indicators, tuple(MODEL4_INPUT_SOURCES.values()))
    marked = provenance_map(indicators)
    for field in ("target_ph", "fertilizer_type"):
        if field in imputed:
            continue
        if marked.get(field) == SOURCE_DEFAULT:
            imputed.append(field)
        elif parcel is None or getattr(parcel, field, None) in (None, ""):
            imputed.append(field)
    return imputed


class AcidificationRemediationAgent(BaseAgent):
    """模型4：耕地土壤酸化改良（过程模型）。"""

    def __init__(self):
        super().__init__(
            name="AcidificationRemediationAgent",
            description="基于过程模型计算酸化改良剂需求量（YTK/MBNT）",
            model_id="acidification-remediation",
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
                # 用户/调用方显式提供的参数优先，其次 DB 地块字段，最后默认值。
                user_target_ph = task.get("target_ph")
                user_fertilizer_type = task.get("fertilizer_type")
                fertilizer_type = user_fertilizer_type or (parcel.fertilizer_type if parcel else None) or "compound"
                pHtarget = user_target_ph if user_target_ph is not None else (parcel.target_ph if parcel else None)
                imputed_inputs = _imputed_model4_inputs(parcel, mapped)
                # 用户显式提供的上下文参数不算“回填/默认”，从判定结果中剔除，
                # 避免因 DB 地块字段为空而把已提供的 target_ph/fertilizer_type 误判为缺失。
                if user_target_ph is not None:
                    imputed_inputs = [f for f in imputed_inputs if f != "target_ph"]
                if user_fertilizer_type:
                    imputed_inputs = [f for f in imputed_inputs if f != "fertilizer_type"]
                result = calculate_acidification(
                    SJD=mapped["SJD"] or 0.0, Hex=mapped["Hex"] or 0.0, Alex=mapped["Alex"] or 0.0,
                    land_type=land_type, fertilizer_type=fertilizer_type, pHtarget=pHtarget)
                if imputed_inputs:
                    # 用量与酸缓冲量由回填/默认输入推出，不作为结论输出（与统一输出契约的
                    # Model-4 安全规则一致）；落库同步置空，避免报告读库时又取到这些数字。
                    result = {
                        key: (None if key in QUANTITATIVE_RESULT_FIELDS else value)
                        for key, value in result.items()
                    }
                outputs = {
                    "parcel_id": inputs.get("parcel_id"),
                    **result,
                    "soil_ph": mapped["SJD"],
                    # land_type 已由 DB 地块档案/默认值解析，透传给输出契约，供 LLM 知晓无需追问
                    "land_type": land_type,
                    "imputed_inputs": imputed_inputs,
                    # 统一输出契约从嵌套 result 读取问题码，故与 Model-5 保持同一形状。
                    "reason": IMPUTED_INPUT if imputed_inputs else None,
                }
                # 输入含回填或默认取值时降级，避免把回填参数的计算结果当作实测结论。
                status = "degraded" if imputed_inputs else "ok"
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
                status = result["status"]
                data_source = "legacy_process"

            persisted = self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id") or inputs.get("parcel_id"),
                inputs={**inputs, "data_source": data_source},
                outputs=outputs,
                status=status,
                execution_context=task.get("execution_context"),
            )

            if data_source == "db":
                imputed_inputs = outputs.get("imputed_inputs") or []
                envelope: Dict[str, Any] = {
                    "status": status,
                    # 模型真实执行，但部分输入来自回填或默认值，因此不标记为模拟。
                    "simulated": False,
                    "result": outputs,
                    "metadata": {
                        "reason": IMPUTED_INPUT if imputed_inputs else None,
                        "imputed_inputs": imputed_inputs,
                    },
                    "data_source": data_source,
                    "persisted": persisted,
                }
                if imputed_inputs:
                    envelope["issues"] = [{
                        "code": IMPUTED_INPUT,
                        "severity": "warning",
                        "message": (
                            "酸化计算输入包含区域平均回填或默认取值，已降级标注："
                            + "、".join(imputed_inputs)
                        ),
                    }]
                return envelope
            return {
                "status": result["status"],
                # legacy 路径使用默认输入或文件数据，公共契约将其标记为降级。
                "simulated": True,
                "result": outputs["result"],
                "metadata": outputs["metadata"],
                "data_source": data_source,
                "persisted": persisted,
            }
        except Exception as e:
            self._persist_result(
                agent_id=self.agent_id,
                parcel_id=task.get("parcel_id"),
                inputs={**inputs, "data_source": data_source},
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
