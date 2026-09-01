"""Strict data contracts for comprehensive diagnostic workflow steps."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Immutable workflow payload that rejects undeclared data."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class InteractionKind(str, Enum):
    KNOWLEDGE = "knowledge"
    SINGLE_ANALYSIS = "single_analysis"
    COMPREHENSIVE_ANALYSIS = "comprehensive_analysis"
    UNSUPPORTED = "unsupported"


class InteractionIntent(StrictModel):
    kind: InteractionKind
    confidence: float = Field(ge=0, le=1)
    reason_code: Literal[
        "KNOWLEDGE_REQUEST",
        "SINGLE_MODEL_REQUEST",
        "EXPLICIT_COMPREHENSIVE_REPORT",
        "UNSUPPORTED_REQUEST",
        "DETERMINISTIC_FALLBACK",
    ]
    prompt_version: str


class TriggerRule(StrictModel):
    type: Literal["always", "all", "any"]
    predicates: tuple[str, ...] = ()


class DiagnosticTask(StrictModel):
    task_id: str = Field(min_length=1)
    agent_id: str
    required: bool
    depends_on: tuple[str, ...] = ()
    trigger: TriggerRule


class DiagnosticPlan(StrictModel):
    plan_version: Literal[1]
    analysis_mode: Literal["single_parcel_comprehensive"]
    planner_prompt_version: str
    tasks: tuple[DiagnosticTask, ...] = Field(min_length=2, max_length=5)
    planner_reason: str = Field(min_length=1, max_length=500)


class ResolvedValue(StrictModel):
    value: Any
    unit: str | None = None
    source: Literal["parcel_db", "user", "confirmed_default"]
    source_version: str


class InputResolution(StrictModel):
    task_arguments: dict[str, dict[str, Any]]
    resolved_values: dict[str, ResolvedValue]
    missing_inputs: tuple[str, ...] = ()
    proposed_defaults: dict[str, Any] = Field(default_factory=dict)
    object_version: int


class TaskResult(StrictModel):
    task_id: str
    agent_id: str
    status: Literal["succeeded", "failed", "degraded", "skipped"]
    payload: dict[str, Any]
    key_inputs: dict[str, Any]
    model_version: str
    data_as_of: str | None
    data_version: str | None
    calculated_at: str
    trace_id: str
    error_code: str | None = None


class EvidenceItem(StrictModel):
    source_id: str
    doc_name: str
    chunk_index: int | None
    page: int | None
    claim_ids: tuple[str, ...]
    score: float | None


class EvidenceBundle(StrictModel):
    items: tuple[EvidenceItem, ...]
    unsupported_claims: tuple[str, ...] = ()


class ReportSection(StrictModel):
    section_id: str
    title: str
    prose_template: str
    fact_refs: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()


class ReportPayload(StrictModel):
    title: str
    sections: tuple[ReportSection, ...]
    degradations: tuple[str, ...]
    prompt_version: str


class InteractionResponse(StrictModel):
    run_id: str
    expected_checkpoint_version: int = Field(ge=1)
    action: Literal[
        "provide_input",
        "confirm_plan",
        "request_revision",
        "release_report",
        "cancel",
    ]
    values: dict[str, Any] = Field(default_factory=dict)
    comment: str = Field(default="", max_length=2000)


class WorkflowOutput(StrictModel):
    interaction_state: str
    run_id: str
    checkpoint_version: int = Field(ge=0)
    analysis_context: dict[str, Any]
    plan_summary: dict[str, Any] = Field(default_factory=dict)
    missing_inputs: tuple[str, ...] = ()
    proposed_defaults: dict[str, Any] = Field(default_factory=dict)
    report_draft: str | None = None
    answer: str | None = None
    degradations: tuple[str, ...] = ()
    provenance: dict[str, Any] = Field(default_factory=dict)
    trace_id: str
