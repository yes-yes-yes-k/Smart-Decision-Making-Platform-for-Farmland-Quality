"""Bounded graph query and permission-filtered evidence resolution."""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import GraphQuery


class SafeGraphQueryService:
    def __init__(self, graph_store, vector_store):
        self.graph_store = graph_store
        self.vector_store = vector_store

    def query(
        self, *, entity_ids, relation_types=(), direction="both", max_hops=1,
        top_k=20, timeout_ms=1000, max_result_bytes=262_144,
        filters: Mapping[str, Any] | None = None, category: str | None = None,
    ) -> dict[str, Any]:
        request = GraphQuery(
            entity_ids=tuple(str(value) for value in entity_ids),
            relation_types=tuple(str(value) for value in relation_types),
            direction=str(direction), max_hops=int(max_hops), top_k=int(top_k),
            timeout_ms=int(timeout_ms), max_result_bytes=int(max_result_bytes),
        )
        try:
            result = self.graph_store.neighbors(request)
        except Exception as exc:
            return {
                "status": "degraded", "failure_code": (
                    "graph_query_timeout" if isinstance(exc, TimeoutError)
                    else "graph_query_unavailable"
                ),
                "active_release": None, "entities": [], "relations": [],
                "evidence": [], "truncated": False,
            }
        fetch = getattr(self.vector_store, "get_by_references", None)
        chunks = []
        if callable(fetch) and result.evidence_references:
            chunks = fetch(
                [dict(item) for item in result.evidence_references],
                filters=dict(filters or {}), category=category,
                n_results=min(request.top_k, 100),
            )
        return {
            "status": "ok", "failure_code": None,
            "active_release": result.active_release,
            "entities": [dict(item) for item in result.entities],
            "relations": [dict(item) for item in result.relations],
            "evidence": list(chunks), "truncated": bool(result.truncated),
        }
