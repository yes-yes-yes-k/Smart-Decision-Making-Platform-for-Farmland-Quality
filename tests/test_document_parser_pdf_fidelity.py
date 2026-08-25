"""扫描件与含表格 PDF 信息保真集成测试（mock pdfplumber/pdf2image）。"""
import sys
import os
import types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.upload import document_parser
from framework.upload.document_parser import _parse_pdf, _parse_pdf_ocr, parse_document


def _make_fake_pdfplumber(pdf_obj):
    """构造 fake pdfplumber 模块：open 返回上下文管理器，yield pdf_obj。"""
    mod = types.ModuleType("pdfplumber")

    def _open(path):
        class _Handler:
            def __enter__(self): return pdf_obj
            def __exit__(self, *a): return False
        return _Handler()
    mod.open = _open
    return mod


def test_image_type_pdf_triggers_ocr_primary(monkeypatch):
    # avg_chars < 阈值 → 走 OCR 主路径
    class _Page:
        def extract_text(self): return "ab"  # 每页 2 字符
        def extract_tables(self): return []
    class _Pdf:
        pages = [_Page() for _ in range(3)]
    monkeypatch.setitem(sys.modules, "pdfplumber", _make_fake_pdfplumber(_Pdf()))

    ocr_called = {"yes": False}
    def _fake_ocr(fp, page_aware=False):
        ocr_called["yes"] = True
        if page_aware:
            return [(1, "OCR第一页"), (2, "OCR第二页"), (3, "OCR第三页")]
        return "OCR全文"
    monkeypatch.setattr(document_parser, "_parse_pdf_ocr", _fake_ocr)

    result = _parse_pdf("/tmp/scan.pdf", page_aware=True)
    assert ocr_called["yes"] is True
    assert isinstance(result, list)
    assert result[0] == (1, "OCR第一页")


def test_text_pdf_with_table_preserves_structure(monkeypatch):
    # 文本层正常 + 含表格 → 提取文本 + 表格 Markdown
    class _Page:
        def extract_text(self): return "页面正文"
        def extract_tables(self):
            return [[["产品", "数量"], ["A", "10"], ["B", "20"]]]
    class _Pdf:
        pages = [_Page()]
    monkeypatch.setitem(sys.modules, "pdfplumber", _make_fake_pdfplumber(_Pdf()))
    # 文本层正常，强制高于阈值走文本提取路径
    monkeypatch.setattr(document_parser, "_detect_avg_chars", lambda pdf: 100.0)

    result = _parse_pdf("/tmp/with_table.pdf", page_aware=True)
    assert isinstance(result, list)
    page_text = result[0][1]
    assert "页面正文" in page_text
    assert "| 产品 | 数量 |" in page_text
    assert "| A | 10 |" in page_text


def test_page_aware_returns_pages_from_one(monkeypatch):
    class _Page:
        def __init__(self, n): self._n = n
        def extract_text(self): return f"第{self._n}页内容"
        def extract_tables(self): return []
    class _Pdf:
        pages = [_Page(i) for i in range(1, 4)]
    monkeypatch.setitem(sys.modules, "pdfplumber", _make_fake_pdfplumber(_Pdf()))
    # 文本层正常，强制高于阈值走文本提取路径
    monkeypatch.setattr(document_parser, "_detect_avg_chars", lambda pdf: 100.0)

    result = _parse_pdf("/tmp/multi.pdf", page_aware=True)
    page_nums = [p for p, _ in result]
    assert page_nums == [1, 2, 3]


def test_empty_page_ocr_fallback(monkeypatch):
    # 文本层提取为空 → 该页 OCR 兜底
    class _Page:
        def extract_text(self): return ""
        def extract_tables(self): return []
    class _Pdf:
        pages = [_Page()]
    monkeypatch.setitem(sys.modules, "pdfplumber", _make_fake_pdfplumber(_Pdf()))
    # avg_chars 强制高于阈值，走文本提取路径
    monkeypatch.setattr(document_parser, "_detect_avg_chars", lambda pdf: 100.0)

    # mock pdf2image + pytesseract（局部 from import 走 sys.modules）
    class _Img: pass
    fake_pdf2image = types.ModuleType("pdf2image")
    fake_pdf2image.convert_from_path = lambda fp, first_page=None, last_page=None: [_Img()]
    monkeypatch.setitem(sys.modules, "pdf2image", fake_pdf2image)
    fake_pytesseract = types.ModuleType("pytesseract")
    fake_pytesseract.image_to_string = lambda img, lang=None: "OCR兜底文本"
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    result = _parse_pdf("/tmp/empty_page.pdf", page_aware=True)
    assert result[0][1] == "OCR兜底文本"
