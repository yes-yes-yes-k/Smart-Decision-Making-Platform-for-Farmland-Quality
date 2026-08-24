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