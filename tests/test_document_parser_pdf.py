"""测试 PDF 解析：图片型检测、表格 Markdown、page_aware 返回结构。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.upload import document_parser
from framework.upload.document_parser import (
    parse_document, _detect_avg_chars, _table_to_markdown,
)


def test_table_to_markdown_basic():
    rows = [["列A", "列B"], ["1", "2"], ["3", "4"]]
    md = _table_to_markdown(rows)
    assert "| 列A | 列B |" in md
    assert "| --- | --- |" in md
    assert "| 1 | 2 |" in md
    assert "| 3 | 4 |" in md


def test_table_to_markdown_empty():
    assert _table_to_markdown([]) == ""
    assert _table_to_markdown([[]]) == ""


def test_table_to_markdown_handles_none_cells():
    rows = [["a", None], [None, "b"]]
    md = _table_to_markdown(rows)
    assert "| a |  |" in md
    assert "|  | b |" in md


def test_detect_avg_chars_samples_first_five(monkeypatch):
    class _Page:
        def __init__(self, n): self._n = n
        def extract_text(self): return "x" * self._n
    class _Pdf:
        pages = [_Page(100), _Page(200), _Page(50), _Page(80), _Page(120), _Page(999)]
    avg = _detect_avg_chars(_Pdf())
    # 采样前 5 页：(100+200+50+80+120)/5 = 110
    assert avg == 110.0


def test_detect_avg_chars_empty_pdf():
    class _Pdf:
        pages = []
    assert _detect_avg_chars(_Pdf()) == 0.0


def test_parse_document_page_aware_non_pdf_returns_str(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("正文", encoding="utf-8")
    # 非 PDF 格式忽略 page_aware，仍返回 str
    result = parse_document(str(p), "txt", page_aware=True)
    assert isinstance(result, str)
