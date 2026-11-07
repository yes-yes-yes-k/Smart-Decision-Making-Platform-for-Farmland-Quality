import pytest
from langchain_core.tools import Tool
from pydantic import BaseModel
from framework.agents.workflows.comprehensive.confirmation import ConfirmationPolicy
from framework.agents.workflows.comprehensive.contracts import DiagnosticTask
from framework.agents.workflows.comprehensive.execution import ModelToolExecutor, TriggerEvaluator
from framework.agents.workflows.comprehensive.contracts import TaskResult
from framework.agents.workflows.comprehensive.planner import DiagnosticPlanner, PlanValidationError, PlanValidator, PlanningFacts
from framework.agents.workflows.comprehensive.reporting import ReportPolicyError, ReportPolicyValidator, Reporter, user_facing_text
from framework.agents.workflows.comprehensive.structured_roles import StructuredRoleError
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


class ToolArgs(BaseModel):
    parcel_id: str
    area_code: str | None = None


def test_model_tool_executor_calls_multi_argument_tool_with_filtered_inputs():
    captured = {}

    def calculate(parcel_id, area_code=None, execution_context=None):
        captured.update({
            "parcel_id": parcel_id,
            "area_code": area_code,
            "execution_context": execution_context,
        })
        return {"status":"ok", "result":{"parcel_id":parcel_id}}

    tool = Tool(
        name="quality", func=calculate, description="test", args_schema=ToolArgs,
    )
    task = DiagnosticTask.model_validate({
        "task_id":"quality-evaluation", "agent_id":"model-2",
        "required":True, "depends_on":(),
        "trigger":{"type":"always", "predicates":()},
    })
    context = {
        "verified":True,
        "analysis_context":{"object":{"type":"parcel", "id":"4190"}},
        "trace_id":"trace-tool",
    }
    raw = ModelToolExecutor({"model-2":tool}).invoke(
        task,
        arguments={"parcel_id":"4190", "area_code":"440233", "soil_ph":5.2},
        execution_context=context,
    )
    assert raw["status"] == "ok"
    assert captured == {
        "parcel_id":"4190", "area_code":"440233", "execution_context":context,
    }


def test_report_rejects_unbound_number():
    payload=report_payload(prose_template="建议施用 999 kg/ha",fact_refs=())
    with pytest.raises(ReportPolicyError,match="raw_number_forbidden"):
        ReportPolicyValidator().validate_and_render(payload,task_results={"quality":successful_model2_result()},evidence=valid_evidence())


def test_report_renders_exact_fact():
    payload=report_payload(prose_template="综合指数为 [[fact:model-2.composite_index]]。",fact_refs=("model-2.composite_index",))
    text=ReportPolicyValidator().validate_and_render(payload,task_results={"quality":successful_model2_result()},evidence=valid_evidence())
    assert "0.73" in text


def test_report_rounds_customer_facing_values_without_changing_payload():
    payload=report_payload(
        prose_template="综合指数为 [[fact:model-2.composite_index]]。",
        fact_refs=("model-2.composite_index",),
    )
    result=successful_model2_result(composite_index=0.8339658156201359)
    text=ReportPolicyValidator().validate_and_render(
        payload,task_results={"quality":result},evidence=valid_evidence(),
    )
    assert "综合指数为 0.83" in text
    assert result.payload["composite_index"] == 0.8339658156201359


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


class UnavailableStructuredRunner:
    def generate(self, *, role, **_kwargs):
        raise StructuredRoleError(role, ["llm_unavailable"])


def test_planner_uses_valid_deterministic_plan_when_llm_is_unavailable():
    plan = DiagnosticPlanner(
        UnavailableStructuredRunner(), PlanValidator(),
    ).create_plan(
        request={"question": "生成综合诊断"},
        facts=PlanningFacts(
            history_available=True,
            user_requested_acidification=True,
            user_requested_organic_matter=True,
        ),
        capabilities=[],
    )
    assert [task.agent_id for task in plan.tasks] == [
        "model-1", "model-2", "model-3", "model-4", "model-5",
    ]
    assert plan.planner_prompt_version == "planner-deterministic-v1"


def _task_result(agent_id, task_id, payload):
    return TaskResult(
        task_id=task_id, agent_id=agent_id, status="succeeded",
        payload=payload, key_inputs={"parcel_id":"4190"},
        model_version="test", data_as_of=None, data_version="parcel:test",
        calculated_at="2026-09-04T00:00:00+00:00", trace_id="trace-test",
    )


def test_reporter_uses_user_facing_deterministic_report_when_llm_is_unavailable():
    results = {
        "quality-evaluation": _task_result(
            "model-2", "quality-evaluation",
            {"parcel_id":"4190", "quality_grade":"3", "composite_index":0.83},
        ),
        "problem-diagnosis": _task_result(
            "model-3", "problem-diagnosis",
            {"parcel_id":"4190", "obstacle_type":"多障碍",
             "primary_factors":["YJZ"], "secondary_factors":["YXL", "SXJ"]},
        ),
        "acidification-remediation": _task_result(
            "model-4", "acidification-remediation",
            {"parcel_id":"4190", "ytk":120.5, "mbnt":240.0},
        ),
        "organic-matter-improvement": _task_result(
            "model-5", "organic-matter-improvement",
            {"parcel_id":"4190", "dose":8.2},
        ),
    }
    payload, text = Reporter(
        UnavailableStructuredRunner(), ReportPolicyValidator(),
    ).compose(
        task_results=results, evidence=valid_evidence(),
        degradations=("local_evidence_unavailable",),
    )
    assert payload.prompt_version == "reporter-deterministic-v1"
    assert "有机质" in text
    assert "有效磷" in text
    assert "速效钾" in text
    assert "土壤调理剂（亿土康）建议施用量为 120.50 公斤/公顷" in text
    assert "木本泥炭建议施用量为 240.00 公斤/公顷" in text
    assert "有机质培肥建议施用量为 8.20 吨/公顷" in text
    assert "YTK" not in text
    assert "MBNT" not in text
    assert "model-" not in text
