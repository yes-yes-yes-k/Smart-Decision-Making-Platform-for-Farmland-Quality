from __future__ import annotations
from typing import TypedDict, Any, Optional

class MultiAgentState(TypedDict):
    request: dict[str, Any]
    data: dict[str, Any]
    model_results: dict[str, Any]
    llm_response: dict[str, Any]
    rag_response: dict[str, Any]
    conversation_history: list[dict]
    status: str
    error: Optional[str]
    question_type: Optional[int]
    relevance: Optional[float]
    routing_status: Optional[str]
    trace_id: Optional[str]
    analysis_context: dict[str, Any]
    calculation_mode: str
    guard_decision: dict[str, Any]
    validated_identifiers: dict[str, str]
    scenario_inputs: dict[str, Any]
    user_id: int | None
    conversation_id: int | None
