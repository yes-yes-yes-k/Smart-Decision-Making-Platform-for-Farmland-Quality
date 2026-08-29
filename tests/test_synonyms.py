"""测试耕地领域同义词整词替换。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.rag.synonyms import normalize_query, load_synonyms


def test_load_synonyms_returns_dict():
    data = load_synonyms()
    assert isinstance(data, dict)
    assert "交换性氢" in data


def test_hit_replacement():
    # 命中：同义词 → 规范词
    assert normalize_query("可交换氢") == "交换性氢"


def test_hit_replacement_cjk_embedded():
    # 中文相邻（无空格）也视为整词命中
    assert normalize_query("土壤可交换氢含量偏高") == "土壤交换性氢含量偏高"


def test_unmatched_passthrough():
    # 规范词本身 / 未收录词 → 原样
    assert normalize_query("交换性氢") == "交换性氢"
    assert normalize_query("有机质含量") == "有机质含量"
    assert normalize_query("重金属污染") == "重金属污染"


def test_whole_word_ascii_boundary_no_misfire(monkeypatch):
    from framework.rag import synonyms as syn
    monkeypatch.setattr(syn, "load_synonyms", lambda: {"有效钾": ["速效钾"]})
    # 同义词两侧接英文/数字时视为更大词的一部分，跳过替换
    assert syn.normalize_query("abc速效钾") == "abc速效钾"
    assert syn.normalize_query("速效钾x") == "速效钾x"


def test_longest_first_avoid_substring_misfire(monkeypatch):
    from framework.rag import synonyms as syn
    # 长同义词"水解性氮"应先于短同义词"水解性"匹配
    monkeypatch.setattr(syn, "load_synonyms", lambda: {"碱解氮": ["水解性氮", "水解性"]})
    assert syn.normalize_query("水解性氮含量") == "碱解氮含量"


def test_empty_dict_passthrough(monkeypatch):
    from framework.rag import synonyms as syn
    monkeypatch.setattr(syn, "load_synonyms", lambda: {})
    assert syn.normalize_query("可交换氢") == "可交换氢"


def test_load_synonyms_missing_file_returns_empty(monkeypatch):
    from framework.rag import synonyms as syn
    monkeypatch.setattr(syn, "_cache", None)
    monkeypatch.setattr(syn, "_SYNONYM_PATH", "/nonexistent/path/soil_synonyms.json")
    assert syn.load_synonyms() == {}