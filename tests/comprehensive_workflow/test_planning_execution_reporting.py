import pytest
from framework.agents.workflows.comprehensive.confirmation import ConfirmationPolicy
from framework.agents.workflows.comprehensive.execution import TriggerEvaluator
from framework.agents.workflows.comprehensive.planner import PlanValidationError, PlanValidator, PlanningFacts
from framework.agents.workflows.comprehensive.reporting import ReportPolicyError, ReportPolicyValidator, user_facing_text
from tests.comprehensive_workflow.factories import complete_resolution, make_model4_always, report_payload, successful_model2_result, valid_evidence, valid_plan


def test_plan_rejects_unconditional_second_wave():
    with pytest.raises(PlanValidationError,match="invalid_trigger"):
        PlanValidator().validate(make_model4_always(valid_plan()),PlanningFacts(False))


def test_confirmation_is_required_for_unconfirmed_plan():
    decision=ConfirmationPolicy().decide(plan=valid_plan(),resolution=complete_resolution())
    assert decision.interaction_state=="needs_confirmation"


@pytest.mark.parametrize("name,expected",[("acidification_evidence",True),("unknown",False)])
def test_trigger_predicates_are_closed(name,expected):
    assert TriggerEvaluator().predicate(name,{"acidification_evidence":True}) is expected


def test_report_rejects_unbound_number():
    payload=report_payload(prose_template="建议施用 999 kg/ha",fact_refs=())
    with pytest.raises(ReportPolicyError,match="raw_number_forbidden"):
        ReportPolicyValidator().validate_and_render(payload,task_results={"quality":successful_model2_result()},evidence=valid_evidence())


def test_report_renders_exact_fact():
    payload=report_payload(prose_template="综合指数为 [[fact:model-2.composite_index]]。",fact_refs=("model-2.composite_index",))
    text=ReportPolicyValidator().validate_and_render(payload,task_results={"quality":successful_model2_result()},evidence=valid_evidence())
    assert "0.734" in text


def test_report_hides_workflow_internals_and_translates_codes():
    text=user_facing_text(
        "节点状态：Coordinator[done] → Reporter[drafted]\n"
        "model-4（ok）建议 YTK 100 kg/ha、MBNT 200 kg/ha；关注 YXL 和 SXJ。"
    )
    assert "节点状态" not in text
    assert "Coordinator" not in text
    assert "model-4" not in text
    assert "YTK" not in text
    assert "MBNT" not in text
    assert "酸化改良测算建议 土壤调理剂（亿土康）" in text
    assert "木本泥炭" in text
    assert "有效磷" in text
    assert "速效钾" in text
