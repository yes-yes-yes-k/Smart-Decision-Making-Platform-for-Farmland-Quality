"""测试 document_parser 各路径接入 clean_text。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.upload import document_parser
from framework.upload.document_parser import parse_document, _parse_txt


def test_parse_txt_applies_clean(tmp_path):
    # 写入含全角字符与控制字符的 txt
    p = tmp_path / "sample.txt"
    p.write_text("ＡＢＣ\x00正文   空白", encoding="utf-8")
    result = _parse_txt(str(p))
    # clean_text 已接入：全角→半角、控制字符去除、空白合并
    assert "ABC" in result
    assert "\x00" not in result
    assert "正文  空白" in result


def test_parse_txt_empty_file(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("", encoding="utf-8")
    assert _parse_txt(str(p)) == ""


def test_parse_document_unknown_type_returns_none():
    assert parse_document("/tmp/x.xyz", "xyz") is None
