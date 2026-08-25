"""测试 page-aware 切分：跨页不拼接、空页跳过、参数缺省。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.upload.chunker import split_text_with_pages, split_text


def test_single_page_multiple_chunks(monkeypatch):
    monkeypatch.setattr("framework.upload.chunker.Config.CHUNK_SIZE", 10)
    monkeypatch.setattr("framework.upload.chunker.Config.CHUNK_OVERLAP", 2)
    pages = [(1, "a" * 25)]
    result = split_text_with_pages(pages)
    assert all(isinstance(c, tuple) for c in result)
    assert all(p == 1 for _, p in result)
    assert len(result) >= 2  # 25 字符 / 10 size 至少 3 块


def test_empty_page_skipped():
    pages = [(1, ""), (2, "正文内容")]
    result = split_text_with_pages(pages)
    assert len(result) == 1
    assert result[0] == ("正文内容", 2)


def test_cross_page_not_concatenated():
    # 跨页不拼接：每页独立切分
    pages = [(1, "页一内容"), (2, "页二内容")]
    result = split_text_with_pages(pages)
    chunks = [c for c, _ in result]
    pages_meta = [p for _, p in result]
    # 不应出现跨页拼接的 chunk
    assert "页一内容页二内容" not in chunks
    assert pages_meta == [1, 2]


def test_explicit_size_overlap():
    pages = [(1, "abcdefghij"), (2, "klmnopqrst")]
    result = split_text_with_pages(pages, size=5, overlap=0)
    # 每页 2 块（5+5），共 4 块
    assert len(result) == 4


def test_empty_pages_returns_empty():
    assert split_text_with_pages([]) == []
    assert split_text_with_pages([(1, None)]) == []
