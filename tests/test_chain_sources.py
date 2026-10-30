"""测试 chain.py sources 含 chunk_index/page，且流式与非流式一致。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.rag import chain as chain_module
from framework.rag.chain import RAGChain


def _make_hit(source, chunk_index, page, content="chunk内容"):
    return {
        "content": content,
        "metadata": {
            "source": source,
            "chunk_index": chunk_index,
            "page": page,
            "category": "acidification",
        },
    }


def test_chat_sources_include_chunk_index_and_page(monkeypatch):
    rag = RAGChain.__new__(RAGChain)
    # mock _retrieve_documents 返回 2 个命中
    rag._retrieve_documents = lambda q, v, user_id=None: {
        "results": [
            _make_hit("doc_a.pdf", 0, 1),
            _make_hit("doc_a.pdf", 1, 5),
            _make_hit("doc_b.pdf", 2, 3),
        ],
        "count": 3,
    }
    rag._query_doc_names = lambda names: {"doc_a.pdf": "文档A.pdf", "doc_b.pdf": "文档B.pdf"}
    rag._build_context = lambda results: "ctx"
    rag._build_prompt = lambda q, ctx: "prompt"
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    sources = result["sources"]
    # 每个 chunk 一条 source（不再按文档去重）
    assert len(sources) == 3
    assert {"doc_name": "文档A.pdf", "chunk_index": 0, "page": 1} in sources
    assert {"doc_name": "文档A.pdf", "chunk_index": 1, "page": 5} in sources
    assert {"doc_name": "文档B.pdf", "chunk_index": 2, "page": 3} in sources


def test_chat_sources_metadata_missing_degrades_to_none(monkeypatch):
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v, user_id=None: {
        "results": [
            {"content": "c", "metadata": {"source": "old.pdf"}},  # 旧数据无 chunk_index/page
        ],
        "count": 1,
    }
    rag._query_doc_names = lambda names: {}
    rag._build_context = lambda r: "ctx"
    rag._build_prompt = lambda q, ctx: "p"
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    assert result["sources"] == [{"doc_name": "old.pdf", "chunk_index": None, "page": None}]


def test_chat_stream_sources_same_structure_as_chat(monkeypatch):
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v, user_id=None: {
        "results": [_make_hit("x.pdf", 4, 9)],
        "count": 1,
    }
    rag._query_doc_names = lambda names: {"x.pdf": "X.pdf"}
    rag._build_context = lambda r: "ctx"
    rag._build_prompt = lambda q, ctx: "p"
    rag.llm_service = type("_L", (), {
        "generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"},
        "generate_stream": lambda self, p, h=None: iter(["a", "n", "s"]),
    })()

    # chat
    chat_sources = rag.chat("问题")["sources"]
    # chat_stream：收集 meta 事件
    stream_meta = None
    for ev in rag.chat_stream("问题"):
        if ev.get("type") == "meta":
            stream_meta = ev
            break
    assert stream_meta is not None
    assert stream_meta["sources"] == chat_sources
    assert stream_meta["sources"][0] == {"doc_name": "X.pdf", "chunk_index": 4, "page": 9}


def test_chat_no_retrieval_returns_empty_sources(monkeypatch):
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v, user_id=None: {"results": [], "count": 0}
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    assert result["sources"] == []


def test_multiple_chunks_same_doc_different_pages(monkeypatch):
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v, user_id=None: {
        "results": [
            _make_hit("same.pdf", 0, 1),
            _make_hit("same.pdf", 1, 1),
            _make_hit("same.pdf", 2, 2),
        ],
        "count": 3,
    }
    rag._query_doc_names = lambda names: {"same.pdf": "同文档.pdf"}
    rag._build_context = lambda r: "ctx"
    rag._build_prompt = lambda q, ctx: "p"
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    # 同文档多 chunk 不合并，每条 source 独立
    assert len(result["sources"]) == 3
    pages = [s["page"] for s in result["sources"]]
    assert pages == [1, 1, 2]


def test_source_field_missing(monkeypatch):
    # metadata 完全缺失 source 字段
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v, user_id=None: {
        "results": [{"content": "c", "metadata": {}}],
        "count": 1,
    }
    rag._query_doc_names = lambda names: {}
    rag._build_context = lambda r: "ctx"
    rag._build_prompt = lambda q, ctx: "p"
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    assert result["sources"] == [{"doc_name": "unknown", "chunk_index": None, "page": None}]


def test_metadata_none_entirely(monkeypatch):
    # result.metadata 为 None
    rag = RAGChain.__new__(RAGChain)
    rag._retrieve_documents = lambda q, v, user_id=None: {
        "results": [{"content": "c", "metadata": None}],
        "count": 1,
    }
    rag._query_doc_names = lambda names: {}
    rag._build_context = lambda r: "ctx"
    rag._build_prompt = lambda q, ctx: "p"
    rag.llm_service = type("_L", (), {"generate": lambda self, p, h=None: {"success": True, "content": "ans", "model": "m"}})()

    result = rag.chat("问题")
    assert result["sources"] == [{"doc_name": "unknown", "chunk_index": None, "page": None}]
    # 不抛异常、不丢弃 source


def test_academic_context_and_answer_use_numbered_citations():
    rag = RAGChain.__new__(RAGChain)
    results = [{
        "content": "长期施用有机肥有助于缓解土壤酸化。",
        "metadata": {
            "source": "paper.pdf",
            "document_kind": "academic_paper",
            "title": "有机肥与土壤酸化",
            "authors": ["张三", "李四"],
            "journal": "土壤学报",
            "publication_date": "2024-06-01",
            "doi": "10.1000/example",
            "page": 8,
        },
    }]

    context = rag._build_context(results)
    assert "文档1" not in context
    assert "[1] 参考文献：张三, 李四. 有机肥与土壤酸化[J]. 土壤学报, 2024." in context
    assert "证据位置：第 8 页" in context

    answer = rag._finalize_answer("根据文档1，该措施有效。", results)
    assert "文档1" not in answer
    assert "根据参考文献[1]" in answer
    assert "\n\n参考文献\n[1] 张三, 李四. 有机肥与土壤酸化[J]." in answer
    assert "DOI: 10.1000/example." in answer


def test_multiple_chunks_share_one_bibliography_number():
    rag = RAGChain.__new__(RAGChain)
    metadata = {
        "source": "paper.pdf",
        "document_kind": "academic_paper",
        "title": "耕地质量研究",
        "authors": "Wang Wu; Zhao Liu",
        "journal": "Journal of Soil Science",
        "publication_date": "2023",
    }
    results = [
        {"content": "A", "metadata": {**metadata, "chunk_index": 0, "page": 1}},
        {"content": "B", "metadata": {**metadata, "chunk_index": 1, "page": 2}},
    ]

    sources = rag._build_sources(results, {})
    assert [source["citation_number"] for source in sources] == [1, 1]
    assert sources[0]["citation"] == (
        "Wang Wu, Zhao Liu. 耕地质量研究[J]. Journal of Soil Science, 2023."
    )
    assert rag._reference_suffix(results).count("[1] ") == 1
