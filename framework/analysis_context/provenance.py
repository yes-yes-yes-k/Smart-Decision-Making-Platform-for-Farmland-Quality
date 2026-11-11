"""Deterministic, backend-owned professional result provenance."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from framework.agents.capabilities import ProfessionalCapability

from .contracts import AnalysisContext, CalculationMode


SAFE_INPUT_KEYS = frozenset({
    "parcel_id", "parcel_code", "area_code", "land_type", "fertilizer_type",
    "target_ph", "SJD", "JHX", "JLA", "pH", "SOCbe", "SOMbe", "TN", "TP",
    "TK", "AP", "AK", "Gap", "Dose", "YJZ", "TD", "TL", "TJ", "YXL",
    "SXJ", "YJZTSZ", "YJFLX",
})


def safe_actual_inputs(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        return {}
    return {key: values[key] for key in SAFE_INPUT_KEYS if key in values}


class ResultProvenanceBuilder:
    def build(
        self,
        *,
        trace_id: str,
        analysis_context: AnalysisContext,
        capability: ProfessionalCapability,
        agent_result: Mapping[str, Any],
        calculated_at: datetime,
    ) -> dict[str, Any]:
        scenario = analysis_context.mode is CalculationMode.SCENARIO
        spatial_object = None
        if not scenario and analysis_context.object is not None:
            spatial_object = analysis_context.object.to_dict()
        return {
            "trace_id": trace_id,
            "model_id": capability.model_id,
            "model_version": agent_result.get("model_version") or "unknown",
            "data_as_of": agent_result.get("data_as_of"),
            "data_version": agent_result.get("data_version"),
            "calculated_at": calculated_at.isoformat(),
            "key_inputs": safe_actual_inputs(agent_result.get("actual_inputs")),
            "scenario_result": scenario,
            "spatial_object": spatial_object,
            "object_title": (
                "情景试算，非具体空间对象结果"
                if scenario
                else f"分析对象：{analysis_context.object.display_name}"
            ),
        }


def prepend_object_title(answer: str | None, *, object_title: str) -> str:
    """在正文前拼接“分析对象”标题，并剥离正文开头重复的地块描述。

    字段直查前缀以「区域 地块 N：」开头（如“广东省韶关市仁化县 地块 131：
    耕地质量等级为 6等。”），标题已承载同一地块描述时，正文开头的重复
    描述与冒号会被剥离，保证「区域+地块编号」只出现一次。
    """
    body = str(answer or "").strip()
    if not object_title:
        return body
    descriptor = object_title.split("：", 1)[-1].strip()
    if descriptor and body.startswith(descriptor):
        tail = body[len(descriptor):]
        if tail.startswith("："):
            tail = tail[1:]
        body = tail.strip()
    if not body:
        return object_title
    return f"{object_title}\n\n{body}"
