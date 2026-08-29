"""测试混合检索 RRF 融合与回退（离线，不依赖 embedding/Chroma 初始化）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.vector_store.chroma_store import ChromaVectorStore


def _doc(source, content):
    return {"content": content, "metadata": {"source": source}}


def test_rrf_fuse_dedup_and_rank():
    vector_docs = [
        _doc("a.pdf", "文本A"),
        _doc("b.pdf", "文本B"),
    ]
    bm25_docs = [
        _doc("b.pdf", "文本B"),  # 与向量路重叠
        _doc("c.pdf", "文本C"),
    ]
    fused = ChromaVectorStore._rrf_fuse(vector_docs, bm25_docs, k=60)
    contents = [d["content"] for d in fused]
    # 两路都命中 b.pdf，融合分最高，应排第一；且无重复项
    assert contents[0] == "文本B"
    assert len(contents) == 3
    assert set(contents) == {"文本A", "文本B", "文本C"}


def test_rrf_fuse_same_content_diff_source_kept_separate():
    vector_docs = [_doc("a.pdf", "相同文本")]
    bm25_docs = [_doc("b.pdf", "相同文本")]
    fused = ChromaVectorStore._rrf_fuse(vector_docs, bm25_docs, k=60)
    # 键含 source，不同 source 的同文本各自保留
    assert len(fused) == 2


def test_hybrid_search_disabled_falls_back_to_vector(monkeypatch):
    from framework.config import Config
    monkeypatch.setattr(Config, "HYBRID_SEARCH_ENABLED", False)

    store = ChromaVectorStore.__new__(ChromaVectorStore)
    calls = {}

    def fake_search(query, n_results, filters=None):
        calls["args"] = (query, n_results, filters)
        return {"results": [], "count": 0}

    store.search = fake_search
    result = store.hybrid_search("查询", n_results=20, filters=None)

    assert result == {"results": [], "count": 0}
    assert calls["args"] == ("查询", 20, None)