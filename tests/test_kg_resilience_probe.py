from __future__ import annotations

from framework.knowledge_graph.resilience_probe import probe_vector_availability
from framework.rag.chain import RAGChain


class VectorStore:
    def __init__(self, results):
        self.results = results

    def hybrid_search(self, **_kwargs):
        return {"results": list(self.results), "count": len(self.results)}


def _rag(results):
    rag = RAGChain.__new__(RAGChain)
    rag.vector_store = VectorStore(results)
    rag.kg_retriever = object()
    return rag


def test_probe_actively_calls_failing_graph_and_preserves_vector_results():
    report = probe_vector_availability(
        _rag([{"content": "vector evidence", "metadata": {"visibility_scope": "public"}}]),
        ["土壤酸化如何改良", "有机质不足怎么办"],
    )

    assert report["available_during_graph_failures"] is True
    assert report["graph_failure_calls"] == 2
    assert all(case["graph_error"] == "graph_retrieval_unavailable" for case in report["cases"])
    assert all("土壤" not in str(case) for case in report["cases"])


def test_probe_fails_when_vector_store_has_no_retrievable_evidence():
    report = probe_vector_availability(_rag([]), ["no matching evidence"])

    assert report["available_during_graph_failures"] is False
    assert report["cases"][0]["returned_result_count"] == 0
