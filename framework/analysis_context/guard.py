"""Pure central guard for professional capability requirements."""
from __future__ import annotations

from typing import Any, Mapping

from framework.agents.capabilities import ProfessionalCapability

from .contracts import AnalysisContext, CalculationMode, GuardDecision


class AnalysisRequirementGuard:
    def evaluate(
        self,
        capability: ProfessionalCapability | None,
        context: AnalysisContext,
        *,
        inputs: Mapping[str, Any],
    ) -> GuardDecision:
        if capability is None:
            return GuardDecision(True, "completed")
        if context.mode is CalculationMode.SCENARIO:
            if not capability.supports_scenario:
                return GuardDecision(
                    False,
                    "needs_analysis_object",
                    tuple(capability.supported_object_types),
                    message="该能力不支持无空间对象情景试算",
                )
            missing = tuple(
                name for name in capability.required_scenario_inputs
                if inputs.get(name) is None
            )
            return GuardDecision(
                not missing,
                "completed" if not missing else "needs_scenario_inputs",
                missing_inputs=missing,
                message="" if not missing else "请补充完整情景试算输入",
            )
        object_type = context.object.type.value if context.object else None
        if capability.requires_spatial_object and object_type not in capability.supported_object_types:
            return GuardDecision(
                False,
                "needs_analysis_object",
                tuple(capability.supported_object_types),
                message="请选择满足该能力尺度要求的分析对象",
            )
        return GuardDecision(True, "completed")
