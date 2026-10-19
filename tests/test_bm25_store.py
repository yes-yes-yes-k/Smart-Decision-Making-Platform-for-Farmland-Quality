"""测试应用层 BM25 关键词索引。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.vector_store.bm25_store import BM25Store


def _make_store():
    store = BM25Store()
    store.add_documents(
        ["土壤交换性氢含量影响土壤酸度", "有效钾是作物重要养分指标"],
        [{"source": "soil.pdf"}, {"source": "fertilizer.pdf"}],
    )
    return store


def test_add_and_search_returns_scored_docs():
    store = _make_store()
    results = store.search("交换性氢", n_results=5)
    assert len(results) >= 1
    assert results[0]["metadata"]["source"] == "soil.pdf"
    assert "content" in results[0] and "score" in results[0]


def test_search_hits_terminology():
    store = _make_store()
    results = store.search("有效钾", n_results=5)
    assert any(r["metadata"]["source"] == "fertilizer.pdf" for r in results)


def test_source_filter_includes_only_allowed():
    store = _make_store()
    results = store.search("有效钾", n_results=5, filters={"source": {"$in": ["fertilizer.pdf"]}})
    assert len(results) == 1
    assert results[0]["metadata"]["source"] == "fertilizer.pdf"


def test_owner_filter_prevents_cross_user_results():
    store = BM25Store()
    store.add_documents(
        ["酸化治理资料", "酸化治理资料"],
        [{"source": "a.pdf", "owner_id": 1}, {"source": "b.pdf", "owner_id": 2}],
    )
    results = store.search("酸化", filters={"owner_id": 1})
    assert [item["metadata"]["source"] for item in results] == ["a.pdf"]


def test_delete_by_source():
    store = _make_store()
    assert store.delete_by_source("soil.pdf") == 1
    assert store.search("交换性氢", n_results=5) == []


def test_clear():
    store = _make_store()
    assert store.clear() == 2
    assert store.search("交换性氢", n_results=5) == []
