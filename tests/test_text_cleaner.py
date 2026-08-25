"""测试文本清洗纯函数。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.upload.text_cleaner import clean_text


def test_empty_returns_empty():
    assert clean_text("") == ""
    assert clean_text(None) == ""


def test_nfkc_fullwidth_to_halfwidth():
    # 全角字母数字 → 半角
    assert clean_text("ＡＢＣ１２３") == "ABC123"


def test_control_chars_removed():
    # 保留 \t \n \r，去除其他控制字符
    text = "abc\x00def\x07ghi\n\t\r"
    assert clean_text(text) == "abcdefghi\n\t\r"


def test_multi_whitespace_collapsed():
    # 3+ 空白压成 2 个
    assert clean_text("a   b") == "a  b"
    # 3+ 换行压成 2 个
    assert clean_text("a\n\n\n\nb") == "a\n\nb"


def test_repeated_header_footer_removed():
    # 跨页重复 ≥ 3 次的行去除
    header = "第 X 页 共 Y 页"
    text = "\n".join([header, "正文内容一", header, "正文内容二", header, "正文内容三", header])
    result = clean_text(text)
    assert header not in result.split("\n")
    assert "正文内容一" in result
    assert "正文内容二" in result


def test_short_text_passthrough():
    # 行数 < 6 不做页眉页脚处理
    text = "重复行\n重复行\n重复行"
    # 行数 3 < 6，不去重
    assert "重复行" in clean_text(text)


def test_strip_leading_trailing_whitespace():
    assert clean_text("  hello  ") == "hello"
