"""Active probe proving vector retrieval survives an injected graph failure."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import TYPE_CHECKING, Any, Sequence

from framework.config import Config

if TYPE_CHECKING:
    from framework.rag.chain import RAGChain


class _InjectedGraphFailure:
    def __init__(self):
        self.calls = 0

    def retrieve(self, *_args, **_kwargs):
        self.calls += 1
        raise RuntimeError("injected_graph_failure")

    @staticmethod
    def health():
        return {"ready": False, "errors": ["injected_graph_failure"]}

    @staticmethod
    def merge(graph, vector, *, top_k):
        return [*graph, *vector][:top_k]


def probe_vector_availability(
    rag: "RAGChain", queries: Sequence[str],
) -> dict[str, Any]:
    clean_queries = [str(query).strip() for query in queries if str(query).strip()]
    if not clean_queries:
        raise ValueError("at least one non-empty probe query is required")
    original_graph = getattr(rag, "kg_retriever", None)
    original_values = {
        "KG_RETRIEVAL_ENABLED": Config.KG_RETRIEVAL_ENABLED,
        "KG_ROLLOUT_MODE": Config.KG_ROLLOUT_MODE,
        "RERANK_ENABLED": Config.RERANK_ENABLED,
    }
    injected = _InjectedGraphFailure()
    cases = []
    try:
        rag.kg_retriever = injected
        Config.KG_RETRIEVAL_ENABLED = True
        Config.KG_ROLLOUT_MODE = "enabled"
        Config.RERANK_ENABLED = False
        for query in clean_queries:
            result = rag._retrieve_documents(query, None, user_id=None)
            diagnostics = dict(result.get("diagnostics") or {})
            count = int(result.get("count") or 0)
            cases.append({
                "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "vector_result_count": int(diagnostics.get("vector_result_count") or 0),
                "returned_result_count": count,
                "graph_error": diagnostics.get("graph_error"),
                "passed": (
                    count > 0
                    and int(diagnostics.get("vector_result_count") or 0) > 0
                    and diagnostics.get("graph_error") == "graph_retrieval_unavailable"
                ),
            })
    finally:
        rag.kg_retriever = original_graph
        for name, value in original_values.items():
            setattr(Config, name, value)
    passed = injected.calls == len(clean_queries) and all(case["passed"] for case in cases)
    return {
        "schema": "knowledge-platform-vector-availability-v1",
        "status": "completed",
        "generated_at": datetime.now(UTC).isoformat(),
        "graph_failure_injected": True,
        "graph_failure_calls": injected.calls,
        "query_count": len(clean_queries),
        "available_during_graph_failures": passed,
        "cases": cases,
    }
