"""测试问题类型关键词路由覆盖 xlsx 经典问题（D5）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _identify(question):
    from framework.agents.nodes import identify_question_type
    return identify_question_type(question)


def test_type1_stability_province_question():
    """省市端稳定性问题 → TYPE_1"""
    qt, _ = _identify("查询区域内耕地质量等级整体稳定吗？")
    assert qt == 1, f"期望 TYPE_1，实际 {qt}"


def test_type1_stability_county_question():
    """县域端稳定性薄弱片区 → TYPE_1"""
    qt, _ = _identify("本县哪些乡镇或地块等级稳定性较弱，需要现场复核？")
    assert qt == 1


def test_type1_stability_farmer_question():
    """农户端稳不稳 → TYPE_1"""
    qt, _ = _identify("我的这块田质量等级稳不稳？")
    assert qt == 1


def test_type1_attention_list_question():
    """关注清单 → TYPE_1"""
    qt, _ = _identify("查询区域内哪些对象需要纳入重点关注清单？")
    assert qt == 1


def test_type2_acidification_degree_question():
    """酸化程度判定 → TYPE_2（model-4）"""
    qt, _ = _identify("查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？")
    assert qt == 2


def test_type2_remediation_dosage_question():
    """农户端碱性调理剂施用量 → TYPE_2"""
    qt, _ = _identify("我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？")
    assert qt == 2


def test_type2_landuse_acidification_question():
    """不同土地利用类型酸化 → TYPE_2"""
    qt, _ = _identify("查询区域内不同土地利用类型的酸化程度")
    assert qt == 2


def test_type2_no_generic_words_collision():
    """TYPE_2 已移除通用词"施加""用量"，但含具体词"调理剂"仍命中 TYPE_2"""
    from framework.agents.nodes import QUESTION_TYPE_2_KEYWORDS
    assert "施加" not in QUESTION_TYPE_2_KEYWORDS
    assert "用量" not in QUESTION_TYPE_2_KEYWORDS
    assert "调理剂" in QUESTION_TYPE_2_KEYWORDS


if __name__ == "__main__":
    test_type1_stability_province_question()
    test_type1_stability_county_question()
    test_type1_stability_farmer_question()
    test_type1_attention_list_question()
    test_type2_acidification_degree_question()
    test_type2_remediation_dosage_question()
    test_type2_landuse_acidification_question()
    test_type2_no_generic_words_collision()
    print("\nTYPE_1/TYPE_2 关键词测试通过！")
