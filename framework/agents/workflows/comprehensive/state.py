"""JSON-serializable state shared by the comprehensive workflow graph."""
from typing import Any, TypedDict


class ComprehensiveDiagnosticState(TypedDict, total=False):
    run_id: str
    trace_id: str
    conversation_id: int
    user_id: int
    checkpoint_version: int
    interaction_state: str
    normalized_request: dict[str, Any]
    interaction_intent: dict[str, Any]
    planning_facts: dict[str, Any]
    request_facts: dict[str, Any]
    analysis_context_snapshot: dict[str, Any]
    object_version: int
    diagnostic_plan: dict[str, Any]
    plan_hash: str
    resolved_inputs: dict[str, Any]
    missing_inputs: list[str]
    proposed_defaults: dict[str, Any]
    confirmation: dict[str, Any]
    task_results: dict[str, dict[str, Any]]
    task_attempts: dict[str, int]
    validation_issues: list[dict[str, Any]]
    degradations: list[str]
    evidence_items: list[dict[str, Any]]
    canonical_claims: list[dict[str, Any]]
    unsupported_claims: list[str]
    report_payload: dict[str, Any]
    report_draft: str
    report_revision_count: int
    report_validation_attempts: int
    revision_comment: str
    release_confirmation: dict[str, Any]
    provenance: dict[str, Any]
    error: dict[str, Any] | None
