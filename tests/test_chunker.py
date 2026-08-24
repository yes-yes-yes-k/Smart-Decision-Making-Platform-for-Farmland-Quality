"""测试配置驱动的滑动窗口分块。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.upload.chunker import split_text


def test_empty_or_whitespace_text_returns_empty():
    assert split_text("") == []
    assert split_text("   ") == []


def test_size_non_positive_returns_empty():
    assert split_text("abc", size=0, overlap=0) == []
    assert split_text("abc", size=-1, overlap=0) == []


def test_text_shorter_than_size_returns_single_chunk():
    assert split_text("abc", size=800, overlap=150) == ["abc"]


def test_overlap_covers_segment():
    # 长度 1000、size 800、overlap 150 -> step 650，切出 2 块，末块从 650 开始
    text = "啊" * 1000
    chunks = split_text(text, size=800, overlap=150)
    assert len(chunks) == 2
    assert chunks[0] == text[:800]
    assert chunks[1] == text[650:]


def test_overlap_ge_size_degrades_to_no_overlap():
    # overlap == size -> step 退化为 size，无重叠，不产生死循环
    text = "啊" * 900
    chunks = split_text(text, size=800, overlap=800)
    assert chunks == [text[:800], text[800:]]


def test_last_short_chunk_kept():
    text = "a" * 805
    chunks = split_text(text, size=800, overlap=150)
    assert len(chunks) == 2
    assert chunks[-1] == text[650:]


def test_defaults_read_config():
    # 不传 size/overlap 时使用 Config.CHUNK_SIZE=800 / CHUNK_OVERLAP=150
    text = "啊" * 1000
    chunks = split_text(text)
    assert chunks[0] == text[:800]
    assert chunks[1] == text[650:]