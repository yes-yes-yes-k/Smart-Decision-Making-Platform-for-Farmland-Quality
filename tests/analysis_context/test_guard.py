from datetime import datetime, timezone

from framework.agents.capabilities import (
    PROFESSIONAL_CAPABILITIES,
    ProfessionalCapability,
)
from framework.analysis_context.contracts import (
    AnalysisContext,
    AnalysisObject,
    CalculationMode,
    ObjectType,
)
from framework.analysis_context.guard import AnalysisRequirementGuard


def _context(object_type=None):
    obj = None
    if object_type:
        obj = AnalysisObject(
            type=ObjectType(object_type), id="object-1", display_name="后端名称",
            area_code="440281", parent_path=(), source="registry",
            validated_at=datetime.now(timezone.utc),
        )
    return AnalysisContext(CalculationMode.SPATIAL, 0, obj)


def test_all_professional_capabilities_declare_spatial_requirements():
    for capability in PROFESSIONAL_CAPABILITIES:
        assert capability.supported_object_types
        assert isinstance(capability.supported_object_types, tuple)
        assert isinstance(capability.requires_spatial_object, bool)
        assert isinstance(capability.supports_scenario, bool)
        assert isinstance(capability.required_scenario_inputs, tuple)


def test_parcel_capability_without_object_needs_object():
    capability = PROFESSIONAL_CAPABILITIES[0]
    decision = AnalysisRequirementGuard().evaluate(capability, _context(), inputs={})
    assert decision.interaction_state == "needs_analysis_object"
    assert decision.required_object_types == ("parcel",)


def test_county_fixture_is_allowed_without_parcel_hardcoding():
    capability = ProfessionalCapability(
        agent_id="county-stats", model_id="county-stats", name="县域统计",
        description="统计", domain="statistics", question_type=99,
        supported_object_types=("county",), requires_spatial_object=True,
    )
    assert AnalysisRequirementGuard().evaluate(
        capability, _context("county"), inputs={}
    ).allowed is True
    assert AnalysisRequirementGuard().evaluate(
        capability, _context("parcel"), inputs={}
    ).allowed is False


def test_scenario_requires_complete_model4_inputs():
    model4 = next(cap for cap in PROFESSIONAL_CAPABILITIES if cap.agent_id == "model-4")
    context = AnalysisContext(CalculationMode.SCENARIO, None, None)
    decision = AnalysisRequirementGuard().evaluate(model4, context, inputs={"SJD": 5.2})
    assert decision.interaction_state == "needs_scenario_inputs"
    assert set(decision.missing_inputs) == {"JHX", "JLA", "land_type", "fertilizer_type"}
    complete = {name: "value" for name in model4.required_scenario_inputs}
    assert AnalysisRequirementGuard().evaluate(model4, context, inputs=complete).allowed is True


def test_only_model4_supports_scenario():
    assert [cap.agent_id for cap in PROFESSIONAL_CAPABILITIES if cap.supports_scenario] == ["model-4"]
    for capability in PROFESSIONAL_CAPABILITIES:
        if capability.agent_id != "model-4":
            decision = AnalysisRequirementGuard().evaluate(
                capability, AnalysisContext(CalculationMode.SCENARIO, None, None), inputs={}
            )
            assert decision.allowed is False
            assert decision.interaction_state == "needs_analysis_object"


def test_non_professional_route_needs_no_spatial_object():
    decision = AnalysisRequirementGuard().evaluate(None, _context(), inputs={})
    assert decision.allowed is True and decision.interaction_state == "completed"
