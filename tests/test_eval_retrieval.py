"""测试检索质量评估指标计算（stub vector_store，不依赖真实向量库）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from scripts import eval_retrieval
from scripts.eval_retrieval import load_queries, evaluate


def test_load_queries(tmp_path):
    p = tmp_path / "q.yaml"
    p.write_text("queries:\n  - query: 测试\n    expected_doc_ids: [\"a.pdf\"]\n", encoding="utf-8")
    qs = load_queries(str(p))
    assert len(qs) == 1
    assert qs[0]["query"] == "测试"
    assert qs[0]["expected_doc_ids"] == ["a.pdf"]


def test_evaluate_hit_rate_and_mrr(monkeypatch):
    queries = [
        {"query": "Q1", "expected_doc_ids": ["a.pdf"]},
        {"query": "Q2", "expected_doc_ids": ["b.pdf"]},
    ]

    def _fake_hybrid_search(self, query, category=None, n_results=5, **kw):
        if query == "Q1":
            return {"results": [
                {"metadata": {"source": "a.pdf"}},
                {"metadata": {"source": "c.pdf"}},
            ]}
        if query == "Q2":
            return {"results": [
                {"metadata": {"source": "c.pdf"}},
                {"metadata": {"source": "b.pdf"}},  # rank 2 命中
            ]}
        return {"results": []}

    # patch route_category 与 vector_store.hybrid_search
    monkeypatch.setattr(eval_retrieval, "route_category", lambda q: "other")

    class _FakeVS:
        hybrid_search = _fake_hybrid_search
    monkeypatch.setattr(eval_retrieval, "vector_store", _FakeVS())

    result = evaluate(queries, top_k=5)
    # Q1 rank1 命中（rr=1.0），Q2 rank2 命中（rr=0.5）→ mrr=0.75
    # hit_rate=2/2=1.0
    assert result["summary"]["n"] == 2
    assert result["summary"]["hit_rate"] == 1.0
    assert result["summary"]["mrr"] == pytest.approx(0.75)
    assert result["queries"][0]["hit"] is True
    assert result["queries"][0]["reciprocal_rank"] == 1.0
    assert result["queries"][1]["reciprocal_rank"] == 0.5


def test_evaluate_no_hit(monkeypatch):
    queries = [{"query": "QX", "expected_doc_ids": ["z.pdf"]}]

    monkeypatch.setattr(eval_retrieval, "route_category", lambda q: "other")

    class _FakeVS:
        def hybrid_search(self, query, category=None, n_results=5, **kw):
            return {"results": [{"metadata": {"source": "c.pdf"}}]}
    monkeypatch.setattr(eval_retrieval, "vector_store", _FakeVS())

    result = evaluate(queries, top_k=5)
    assert result["summary"]["hit_rate"] == 0.0
    assert result["summary"]["mrr"] == 0.0
    assert result["queries"][0]["hit"] is False
    assert result["queries"][0]["reciprocal_rank"] == 0.0


def test_evaluate_empty_expected(monkeypatch):
    queries = [{"query": "QE", "expected_doc_ids": []}]

    monkeypatch.setattr(eval_retrieval, "route_category", lambda q: "other")

    class _FakeVS:
        def hybrid_search(self, query, category=None, n_results=5, **kw):
            return {"results": [{"metadata": {"source": "a.pdf"}}]}
    monkeypatch.setattr(eval_retrieval, "vector_store", _FakeVS())

    result = evaluate(queries, top_k=5)
    # 空 expected → 无命中
    assert result["summary"]["hit_rate"] == 0.0
    assert result["queries"][0]["hit"] is False


def test_evaluate_uses_vector_store_n_results_parameter(monkeypatch):
    captured = {}
    monkeypatch.setattr(eval_retrieval, "route_category", lambda q: "acidification")

    class _FakeVS:
        def hybrid_search(self, query, *, category=None, n_results=20):
            captured.update({
                "query": query, "category": category, "n_results": n_results,
            })
            return {"results": []}

    monkeypatch.setattr(eval_retrieval, "vector_store", _FakeVS())
    evaluate([{"query": "酸化", "expected_doc_ids": []}], top_k=7)

    assert captured == {
        "query": "酸化", "category": "acidification", "n_results": 7,
    }
