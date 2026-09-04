from types import SimpleNamespace

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from framework.agents.workflows.comprehensive.confirmation import ConfirmationPolicy, ParcelInputResolver
from framework.agents.workflows.comprehensive.contracts import InteractionResponse
from framework.agents.workflows.comprehensive.graph import ComprehensiveServices, build_comprehensive_graph, initial_state
from framework.agents.workflows.comprehensive.runtime import normalize_graph_output
from framework.domain.data.parcel_data_accessor import ParcelDataSnapshot
from tests.comprehensive_workflow.factories import parcel_context, valid_plan


class SnapshotAccessor:
    def __init__(self, *, land_type=None, fertilizer_type=None, target_ph=6.5):
        self.snapshot=ParcelDataSnapshot(
            parcel_id="P-MISSING", area_code="440281", parcel_code="LC-MISSING",
            land_type=land_type, fertilizer_type=fertilizer_type, target_ph=target_ph,
            indicators={"soil_ph":5.2, "organic_matter":18.0},
            source_version="parcel:test",
        )

    def get_parcel_snapshot(self, parcel_id):
        return self.snapshot if parcel_id==self.snapshot.parcel_id else None


def test_missing_land_type_and_fertilizer_default_are_exposed_safely():
    resolution=ParcelInputResolver(SnapshotAccessor()).resolve(
        valid_plan(), analysis_context=parcel_context("P-MISSING"),
    )
    assert resolution.missing_inputs==("land_type",)
    assert resolution.proposed_defaults=={"fertilizer_type":"compound"}
    assert resolution.task_arguments["acidification-remediation"]["fertilizer_type"]=="compound"
    assert resolution.resolved_values["fertilizer_type"].source=="confirmed_default"


def test_user_values_override_default_and_complete_resolution():
    resolution=ParcelInputResolver(SnapshotAccessor()).resolve(
        valid_plan(), analysis_context=parcel_context("P-MISSING"),
        user_values={"land_type":"paddy", "fertilizer_type":"urea"},
    )
    assert resolution.missing_inputs==()
    assert resolution.proposed_defaults=={}
    assert resolution.resolved_values["land_type"].source=="user"
    assert resolution.resolved_values["fertilizer_type"].source=="user"


def test_missing_safe_values_are_applied_only_after_confirmation():
    resolution=ParcelInputResolver(SnapshotAccessor(land_type="paddy",target_ph=None)).resolve(
        valid_plan(), analysis_context=parcel_context("P-MISSING"),
    )
    assert resolution.missing_inputs==()
    assert resolution.proposed_defaults=={
        "fertilizer_type":"compound", "target_ph":6.5,
    }
    assert resolution.task_arguments["acidification-remediation"]["target_ph"]==6.5
    assert resolution.resolved_values["target_ph"].source=="confirmed_default"


def test_chinese_choices_are_normalized_and_invalid_choice_is_requested_again():
    resolver=ParcelInputResolver(SnapshotAccessor())
    valid=resolver.resolve(
        valid_plan(), analysis_context=parcel_context("P-MISSING"),
        user_values={"land_type":"水田", "fertilizer_type":"尿素"},
    )
    assert valid.missing_inputs==()
    assert valid.task_arguments["acidification-remediation"]["land_type"]=="paddy"
    assert valid.task_arguments["acidification-remediation"]["fertilizer_type"]=="urea"

    invalid=resolver.resolve(
        valid_plan(), analysis_context=parcel_context("P-MISSING"),
        user_values={"land_type":"果园", "fertilizer_type":"磷肥"},
    )
    assert invalid.missing_inputs==("fertilizer_type","land_type")

    invalid_override=ParcelInputResolver(SnapshotAccessor(
        land_type="upland",fertilizer_type="compound",
    )).resolve(
        valid_plan(), analysis_context=parcel_context("P-MISSING"),
        user_values={"land_type":"果园", "fertilizer_type":"磷肥"},
    )
    assert invalid_override.missing_inputs==("fertilizer_type","land_type")


class PlanningFactsStub:
    def resolve(self, **_kwargs):
        return SimpleNamespace(
            history_available=False,
            user_requested_acidification=True,
            user_requested_organic_matter=True,
        )


class PlannerStub:
    def create_plan(self, **_kwargs):
        return valid_plan()


class MustNotRun:
    def __getattr__(self, name):
        raise AssertionError(f"unexpected downstream call: {name}")


def test_incomplete_supplement_prompts_again_before_execution():
    services=ComprehensiveServices(
        planning_facts_resolver=PlanningFactsStub(), planner=PlannerStub(),
        input_resolver=ParcelInputResolver(SnapshotAccessor()),
        confirmation_policy=ConfirmationPolicy(), scheduler=MustNotRun(),
        researcher=MustNotRun(), reporter=MustNotRun(), provenance_builder=MustNotRun(),
    )
    graph=build_comprehensive_graph(services,MemorySaver())
    config={"configurable":{"thread_id":"missing-input-test"}}
    request={
        "run_id":"run-missing", "trace_id":"trace-missing", "conversation_id":91,
        "user_id":7, "message":"请做综合诊断", "analysis_context":parcel_context("P-MISSING"),
        "capabilities":[],
    }
    first=normalize_graph_output(graph.invoke(initial_state(request),config=config))
    assert first.interaction_state=="needs_input"
    assert first.checkpoint_version==1
    assert first.missing_inputs==("land_type",)

    second=normalize_graph_output(graph.invoke(
        Command(resume=InteractionResponse(
            run_id="run-missing", expected_checkpoint_version=1,
            action="provide_input", values={},
        ).model_dump(mode="json")),config=config,
    ))
    assert second.interaction_state=="needs_input"
    assert second.checkpoint_version==2
    assert second.missing_inputs==("land_type",)

    third=normalize_graph_output(graph.invoke(
        Command(resume=InteractionResponse(
            run_id="run-missing", expected_checkpoint_version=2,
            action="provide_input", values={"land_type":"upland"},
        ).model_dump(mode="json")),config=config,
    ))
    assert third.interaction_state=="needs_confirmation"
    assert third.checkpoint_version==3
    assert third.missing_inputs==()
    assert third.proposed_defaults=={"fertilizer_type":"compound"}
