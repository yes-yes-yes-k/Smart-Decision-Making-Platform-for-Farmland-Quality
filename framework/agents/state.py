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