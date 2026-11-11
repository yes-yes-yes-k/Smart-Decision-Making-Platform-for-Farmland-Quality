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
