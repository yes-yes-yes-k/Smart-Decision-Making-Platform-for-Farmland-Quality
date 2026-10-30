"""CAJ 上传与转换解析测试。"""
from pathlib import Path
import subprocess

import pytest

from framework.upload import document_parser


def test_parse_caj_converts_then_reuses_pdf_parser(monkeypatch, tmp_path):
    source = tmp_path / "论文.caj"
    source.write_bytes(b"CAJViewer File")
    converter = tmp_path / "caj2pdf.exe"
    converter.write_bytes(b"placeholder")

    from framework.config import Config
    monkeypatch.setattr(Config, "CAJ_CONVERTER_PATH", str(converter))
    monkeypatch.setattr(Config, "CAJ_CONVERTER_TIMEOUT", 12)

    calls = {}

    def fake_run(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        output = Path(command[command.index("-o") + 1])
        output.write_bytes(b"%PDF-1.7\nconverted")
        return subprocess.CompletedProcess(command, 0, "", "")

    def fake_parse_pdf(path, page_aware=False):
        calls["pdf_path"] = path
        calls["page_aware"] = page_aware
        assert Path(path).read_bytes().startswith(b"%PDF-")
        return [(1, "正文")]

    monkeypatch.setattr(document_parser.subprocess, "run", fake_run)
    monkeypatch.setattr(document_parser, "_parse_pdf", fake_parse_pdf)

    result = document_parser.parse_document(str(source), "caj", page_aware=True)

    assert result == [(1, "正文")]
    assert calls["command"][:2] == [str(converter), "convert"]
    assert calls["kwargs"]["timeout"] == 12
    assert calls["page_aware"] is True
    assert not Path(calls["pdf_path"]).exists(), "临时 PDF 应在解析结束后删除"


def test_parse_caj_pdf_payload_skips_converter(monkeypatch, tmp_path):
    source = tmp_path / "实际为PDF.caj"
    source.write_bytes(b"%PDF-1.7\ncontent")
    monkeypatch.setattr(
        document_parser,
        "_parse_pdf",
        lambda path, page_aware=False: [(1, "内容")] if page_aware else "内容",
    )
    monkeypatch.setattr(
        document_parser.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("PDF payload 不应调用转换器"),
    )

    assert document_parser.parse_document(str(source), "caj", page_aware=True) == [(1, "内容")]


def test_parse_caj_reports_missing_converter(monkeypatch, tmp_path):
    source = tmp_path / "论文.caj"
    source.write_bytes(b"CAJViewer File")
    from framework.config import Config
    monkeypatch.setattr(Config, "CAJ_CONVERTER_PATH", "")
    monkeypatch.setattr(document_parser.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="未找到 CAJ 转换器"):
        document_parser.parse_document(str(source), "caj")


def test_parse_caj_rejects_non_pdf_converter_output(monkeypatch, tmp_path):
    source = tmp_path / "论文.caj"
    source.write_bytes(b"CAJViewer File")
    converter = tmp_path / "caj2pdf.py"
    converter.write_text("# placeholder", encoding="utf-8")
    from framework.config import Config
    monkeypatch.setattr(Config, "CAJ_CONVERTER_PATH", str(converter))

    def fake_run(command, **kwargs):
        Path(command[command.index("-o") + 1]).write_bytes(b"not a pdf")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(document_parser.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="不是有效 PDF"):
        document_parser.parse_document(str(source), "caj")


def test_parse_caj_can_retain_managed_derived_pdf(monkeypatch, tmp_path):
    source = tmp_path / "保留派生.caj"
    source.write_bytes(b"CAJViewer File")
    converter = tmp_path / "caj2pdf.exe"
    converter.write_bytes(b"placeholder")
    upload_dir = tmp_path / "uploads"
    from framework.config import Config
    monkeypatch.setattr(Config, "CAJ_CONVERTER_PATH", str(converter))
    monkeypatch.setattr(Config, "LITERATURE_RETAIN_DERIVED_PDF", True)
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_dir))

    def fake_run(command, **kwargs):
        Path(command[command.index("-o") + 1]).write_bytes(b"%PDF-1.7\nmanaged")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(document_parser.subprocess, "run", fake_run)
    monkeypatch.setattr(
        document_parser, "_parse_pdf",
        lambda *args, **kwargs: document_parser.ParsedPages([(1, "正文")]),
    )
    result = document_parser.parse_document(str(source), "caj", page_aware=True)
    assert result == [(1, "正文")]
    assert result.parse_metadata["derived_pdf_retained"] is True
    assert len(result.parse_metadata["derived_pdf_hash"]) == 64
    derived = list((upload_dir / "derived").glob("*.pdf"))
    assert len(derived) == 1
    assert derived[0].read_bytes().startswith(b"%PDF-")
