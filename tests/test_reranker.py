"""测试 Rerank 精排调用与降级路径。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.rag.reranker import RerankService
from framework.config import Config

CANDIDATES = [
    {"content": "文本一", "metadata": {"source": "a.pdf"}},
    {"content": "文本二", "metadata": {"source": "b.pdf"}},
    {"content": "文本三", "metadata": {"source": "c.pdf"}},
]


def test_rerank_disabled_returns_original(monkeypatch):
    monkeypatch.setattr(Config, "RERANK_ENABLED", False)
    svc = RerankService()
    assert svc.is_available() is False
    assert svc.rerank("q", CANDIDATES) == CANDIDATES


def test_rerank_empty_candidates_returns_empty(monkeypatch):
    monkeypatch.setattr(Config, "RERANK_ENABLED", True)
    monkeypatch.setattr(Config, "SILICONFLOW_API_KEY", "sk-test")
    svc = RerankService()
    assert svc.rerank("q", []) == []


def test_rerank_reranks_by_relevance(monkeypatch):
    monkeypatch.setattr(Config, "RERANK_ENABLED", True)
    monkeypatch.setattr(Config, "SILICONFLOW_API_KEY", "sk-test")

    import requests

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [
                {"index": 2, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.7},
            ]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert json["model"] == Config.RERANK_MODEL
        assert json["query"] == "q"
        assert json["documents"] == ["文本一", "文本二", "文本三"]
        assert json["top_n"] == 3  # min(len(candidates)=3, RETRIEVAL_TOP_K=5)
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    svc = RerankService()
    ranked = svc.rerank("q", CANDIDATES)
    # index 2 分数高排第一，index 0 次之
    assert [d["content"] for d in ranked] == ["文本三", "文本一"]


def test_rerank_api_exception_falls_back(monkeypatch):
    monkeypatch.setattr(Config, "RERANK_ENABLED", True)
    monkeypatch.setattr(Config, "SILICONFLOW_API_KEY", "sk-test")

    import requests

    def fake_post(url, headers=None, json=None, timeout=None):
        raise requests.exceptions.Timeout("mock timeout")

    monkeypatch.setattr(requests, "post", fake_post)
    svc = RerankService()
    assert svc.rerank("q", CANDIDATES) == CANDIDATES


def test_rag_chain_retrieve_triggers_rerank(monkeypatch):
    from framework.rag.chain import rag_chain
    from framework.rag import reranker as reranker_mod

    monkeypatch.setattr(Config, "RECALL_TOP_K", 20)
    monkeypatch.setattr(Config, "RETRIEVAL_TOP_K", 5)
    monkeypatch.setattr(Config, "RERANK_ENABLED", True)

    recalled = {
        "results": [{"content": f"c{i}", "metadata": {"source": "s"}} for i in range(20)],
        "count": 20,
    }

    class FakeVS:
        def hybrid_search(self, query, n_results=None, filters=None, category=None):
            return recalled

    monkeypatch.setattr(rag_chain, "vector_store", FakeVS())

    seen = {}

    def fake_rerank(query, candidates):
        seen["n"] = len(candidates)
        return list(reversed(candidates))[:5]

    monkeypatch.setattr(reranker_mod.rerank_service, "rerank", fake_rerank)

    result = rag_chain._retrieve_documents("查询农耕", {"s"})
    assert seen["n"] == 20
    assert result["count"] == 5
    assert len(result["results"]) == 5


def test_rag_chain_normalizes_query_before_recall(monkeypatch):
    from framework.rag.chain import rag_chain
    from framework.rag import chain as chain_mod

    monkeypatch.setattr(Config, "RECALL_TOP_K", 20)
    monkeypatch.setattr(Config, "RETRIEVAL_TOP_K", 5)
    monkeypatch.setattr(Config, "RERANK_ENABLED", False)

    recalled = {"results": [], "count": 0}
    seen = {}

    def fake_normalize(query):
        return query.replace("速效钾", "有效钾")

    monkeypatch.setattr(chain_mod, "normalize_query", fake_normalize)

    class FakeVS:
        def hybrid_search(self, query, n_results=None, filters=None, category=None):
            seen["query"] = query
            return recalled

    monkeypatch.setattr(rag_chain, "vector_store", FakeVS())

    rag_chain._retrieve_documents("速效钾含量", None)
    assert seen["query"] == "有效钾含量"


def test_rag_chain_preserves_original_query_for_graph_matching(monkeypatch):
    from framework.rag.chain import rag_chain
    from framework.rag import chain as chain_mod

    monkeypatch.setattr(Config, "RERANK_ENABLED", False)
    monkeypatch.setattr(chain_mod, "normalize_query", lambda q: q.replace("耕层厚度", "土层厚度"))
    seen = {}

    class FakeVS:
        def hybrid_search(self, query, n_results=None, filters=None, category=None):
            seen["vector_query"] = query
            return {"results": [], "count": 0}

    class FakeKG:
        def retrieve(self, query, **kwargs):
            seen["graph_query"] = query
            return {"results": [], "claim_assessment": None, "matched": False}

        @staticmethod
        def merge(graph_results, vector_results, *, top_k):
            return list(vector_results)[:top_k]

    monkeypatch.setattr(rag_chain, "vector_store", FakeVS())
    monkeypatch.setattr(rag_chain, "kg_retriever", FakeKG())

    rag_chain._retrieve_documents("耕层厚度是否属于补充指标？", None)

    assert seen["vector_query"] == "土层厚度是否属于补充指标？"
    assert seen["graph_query"] == "耕层厚度是否属于补充指标？"


def test_rag_context_uses_human_readable_role_label():
    from framework.rag.chain import RAGChain

    rag = RAGChain.__new__(RAGChain)
    context = rag._build_context([{
        "content": "规范原文证据。",
        "metadata": {
            "retrieval_source": "knowledge_graph_v0.4",
            "source_entity": "广东省补充耕地质量鉴定技术规范 试行",
            "target_entity": "土壤有机质",
            "relation_type": "assigns_by_laboratory_test",
            "relation_label": "依据土壤样品检测结果赋值",
        },
    }])

    assert "依据土壤样品检测结果赋值" in context
    assert "assigns_by_laboratory_test" not in context


def test_rag_chain_routes_category_and_passes_to_search(monkeypatch):
    from framework.rag.chain import rag_chain
    from framework.rag import chain as chain_mod

    monkeypatch.setattr(Config, "RECALL_TOP_K", 20)
    monkeypatch.setattr(Config, "RETRIEVAL_TOP_K", 5)
    monkeypatch.setattr(Config, "RERANK_ENABLED", False)

    seen = {}
    monkeypatch.setattr(chain_mod, "normalize_query", lambda q: q)
    monkeypatch.setattr(chain_mod, "route_category", lambda q: "acidification")

    class FakeVS:
        def hybrid_search(self, query, n_results=None, filters=None, category=None):
            seen["category"] = category
            return {"results": [], "count": 0}

    monkeypatch.setattr(rag_chain, "vector_store", FakeVS())

    rag_chain._retrieve_documents("土壤酸化严重吗", None)
    assert seen["category"] == "acidification"
