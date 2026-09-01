"""Strict contracts for the comprehensive diagnostic workflow."""
from typing import Any, get_type_hints

import pytest
from pydantic import ValidationError

from framework.agents.capabilities import CAPABILITY_BY_AGENT_ID
from framework.agents.workflows.comprehensive.contracts import (
    DiagnosticPlan,
    InteractionIntent,
)
from framework.agents.workflows.comprehensive.state import ComprehensiveDiagnosticState
from tests.comprehensive_workflow.factories import (
    complete_resolution,
    make_valid_plan_payload,
    valid_evidence,
    valid_plan,
    validated_results,
)


def test_intent_rejects_unknown_kind_and_extra_fields():
    with pytest.raises(ValidationError):
        InteractionIntent.model_validate({
            "kind": "peer_chat",
            "confidence": 1,
            "reason_code": "UNKNOWN",
            "prompt_version": "coordinator-v1",
            "execute_now": True,
        })
    with pytest.raises(ValidationError):
        InteractionIntent.model_validate({
            "kind": "knowledge",
            "confidence": 1,
            "reason_code": "KNOWLEDGE_REQUEST",
            "prompt_version": "coordinator-v1",
            "execute_now": True,
        })


def test_plan_rejects_more_than_five_tasks():
    payload = make_valid_plan_payload()
    payload["tasks"] *= 3
    for index, task in enumerate(payload["tasks"]):
        task["task_id"] = f"task-{index}"
    with pytest.raises(ValidationError):
        DiagnosticPlan.model_validate(payload)


def test_state_is_a_json_only_child_graph_schema():
    hints = get_type_hints(ComprehensiveDiagnosticState)
    assert hints["analysis_context_snapshot"] == dict[str, Any]
    assert hints["task_results"] == dict[str, dict[str, Any]]
    assert hints["evidence_items"] == list[dict[str, Any]]
    assert hints["error"] == dict[str, Any] | None


def test_comprehensive_capability_metadata_is_complete():
    for agent_id in ("model-1", "model-2", "model-3", "model-4", "model-5"):
        cap = CAPABILITY_BY_AGENT_ID[agent_id]
        assert cap.tool_name
        assert cap.result_schema
        assert cap.timeout_seconds > 0
        assert cap.retry_limit == 2
    assert CAPABILITY_BY_AGENT_ID["model-6"].comprehensive_role == "disabled"


def test_shared_factories_return_deterministic_contract_objects():
    assert valid_plan() == valid_plan()
    assert complete_resolution().object_version == 4
    assert validated_results()["quality-evaluation"].status == "succeeded"
    assert valid_evidence().items[0].source_id == "doc-1:0:1"
