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


def test_type3_potential_question():
    """潜力评估 → TYPE_3（model-2/3）"""
    qt, _ = _identify("辖区耕地质量提升的总体潜力有多大？可增产多少粮食？")
    assert qt == 3


def test_type3_county_potential_distribution():
    """县域优先改良片区 → TYPE_3"""
    qt, _ = _identify("我们县划定的优先改良片区具体在哪几个村？每块潜力多大？")
    assert qt == 3


def test_type3_farmer_plot_diagnosis():
    """农户地块诊断"毛病" → TYPE_3"""
    qt, _ = _identify("我这块地到底有啥毛病？")
    assert qt == 3


def test_type3_problem_identification():
    """主要问题/障碍因素 → TYPE_3"""
    qt, _ = _identify("全省耕地质量存在哪些问题？")
    assert qt == 3


def test_type4_organic_matter_content():
    """有机质含量 → TYPE_4（model-5/6）"""
    qt, _ = _identify("全省耕地土壤有机质含量如何，空间分布情况？")
    assert qt == 4


def test_type4_manure_dosage():
    """有机肥/秸秆施用量 → TYPE_4"""
    qt, _ = _identify("为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？")
    assert qt == 4


def test_type4_fertility_ml():
    """农户肥力/SOC → TYPE_4"""
    qt, _ = _identify("我的田肥力怎么样？")
    assert qt == 4


def test_type4_county_organic_average():
    """县域有机质平均含量 → TYPE_4"""
    qt, _ = _identify("本县耕地土壤有机质平均含量是多少？")
    assert qt == 4


def test_keyword_match_priority_over_vector():
    """D5：关键词匹配优先于向量匹配。

    即使向量返回不同的（更高分）类型，含具体关键词的问题仍应被关键词逻辑判定。
    手动 patch _identify_question_type_vector（兼容 __main__ 直接运行，无需 pytest fixture）。
    """
    from framework.agents import nodes

    real_vector = nodes._identify_question_type_vector
    try:
        # 向量返回 TYPE_2 高分，但关键词应判定为 TYPE_4
        nodes._identify_question_type_vector = lambda q: (2, 0.95)
        qt, _ = nodes.identify_question_type("有机肥每亩施用量多少？")
        assert qt == 4, f"关键词优先应返回 TYPE_4，实际 {qt}"
        # 向量返回 TYPE_4 高分，但关键词应判定为 TYPE_2
        nodes._identify_question_type_vector = lambda q: (4, 0.95)
        qt, _ = nodes.identify_question_type("我要施加多少碱性调理剂？")
        assert qt == 2, f"关键词优先应返回 TYPE_2，实际 {qt}"
    finally:
        nodes._identify_question_type_vector = real_vector
    print("✓ 关键词匹配优先于向量匹配（D5）")


def test_type_order_no_cross_collision():
    """关键词不跨类型重叠：TYPE_1 不含酸化词，TYPE_2 不含稳定词"""
    from framework.agents.nodes import (
        QUESTION_TYPE_1_KEYWORDS, QUESTION_TYPE_2_KEYWORDS,
        QUESTION_TYPE_3_KEYWORDS, QUESTION_TYPE_4_KEYWORDS,
    )
    # "酸化"属 TYPE_2，不应出现在 TYPE_1
    assert not any("酸化" in kw for kw in QUESTION_TYPE_1_KEYWORDS)
    # "稳定"属 TYPE_1，不应出现在 TYPE_2
    assert not any("稳定" in kw for kw in QUESTION_TYPE_2_KEYWORDS)
    # "潜力"属 TYPE_3，不应出现在其他
    assert not any("潜力" in kw for kw in QUESTION_TYPE_1_KEYWORDS)
    assert not any("潜力" in kw for kw in QUESTION_TYPE_2_KEYWORDS)
    # "有机质"属 TYPE_4，不应出现在 TYPE_1/2/3
    assert not any("有机质" in kw for kw in QUESTION_TYPE_1_KEYWORDS)
    assert not any("有机质" in kw for kw in QUESTION_TYPE_3_KEYWORDS)


def test_type4_soc_query():
    """model-6 SOC 查询 → TYPE_4"""
    qt, _ = _identify("我的田土壤有机碳含量大概多少？")
    assert qt == 4


def test_type4_dose_query():
    """model-6 Dose 查询 → TYPE_4"""
    qt, _ = _identify("我这块地大概需要施多少有机肥？")
    assert qt == 4


def test_type4_straw_query():
    """秸秆还田 → TYPE_4"""
    qt, _ = _identify("秸秆还田每亩施用量多少？")
    assert qt == 4


def test_type2_farmer_severity():
    """农户酸化严重 → TYPE_2"""
    qt, _ = _identify("我的这块田酸化严重吗？")
    assert qt == 2


def test_unrelated_question_returns_zero():
    """无关问题 → TYPE_0（强制 embedding 不可用，纯关键词路径确定返回 0，避免向量阈值边界 flaky）"""
    from framework.agents import nodes

    real_flag = nodes.EMBEDDING_AVAILABLE
    try:
        nodes.EMBEDDING_AVAILABLE = False
        qt, _ = _identify("今天天气怎么样？")
        assert qt == 0, f"无关问题期望 TYPE_0，实际 {qt}"
    finally:
        nodes.EMBEDDING_AVAILABLE = real_flag
    print("✓ 无关问题返回 TYPE_0")


def test_all_xlsx_classic_questions_routed():
    """xlsx 全部经典问题均能路由到非 0 类型（覆盖性断言）"""
    cases = [
        ("查询区域内耕地质量等级整体稳定吗？", 1),
        ("查询区域内哪些高等级耕地存在退化风险？", 1),
        ("本县哪些乡镇或地块等级稳定性较弱，需要现场复核？", 1),
        ("我的这块田质量等级稳不稳？", 1),
        ("查询区域内哪些对象需要纳入重点关注清单？", 1),
        ("辖区耕地质量提升的总体潜力有多大？可增产多少粮食？", 3),
        ("我们县划定的优先改良片区具体在哪几个村？每块潜力多大？", 3),
        ("我这块地到底有啥毛病？", 3),
        ("全省耕地质量存在哪些问题？", 3),
        ("县/乡镇里的耕地在哪些方面有问题", 3),
        ("查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？", 2),
        ("我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？", 2),
        ("查询区域内不同土地利用类型的酸化程度", 2),
        ("我的这块田酸化严重吗？", 2),
        ("全省耕地土壤有机质含量如何，空间分布情况？", 4),
        ("为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？", 4),
        ("本县耕地土壤有机质平均含量是多少？", 4),
        ("耕地有机质含量低的原因是什么？", 4),
        ("我的田肥力怎么样？", 4),
        ("我的田土壤有机碳含量大概多少？", 4),
        ("我这块地大概需要施多少有机肥？", 4),
    ]
    for q, expected in cases:
        qt, _ = _identify(q)
        assert qt == expected, f"问题「{q}」期望 TYPE_{expected}，实际 TYPE_{qt}"


def test_type5_grade_quality_question():
    """质量等级评价 → TYPE_5（model-7）"""
    qt, _ = _identify("我的田耕地质量等级是多少？")
    assert qt == 5, f"期望 TYPE_5，实际 {qt}"


def test_type5_comprehensive_index_question():
    """综合指数/障碍度排序 → TYPE_5"""
    qt, _ = _identify("查询地块的综合指数和障碍度排序")
    assert qt == 5, f"期望 TYPE_5，实际 {qt}"


def test_type5_grade_evaluation_question():
    """耕地质量等级评价结果 → TYPE_5"""
    qt, _ = _identify("这块地的耕地质量等级评价结果")
    assert qt == 5, f"期望 TYPE_5，实际 {qt}"


def test_type5_keyword_branch_after_type4():
    """type 5 分支在 type 4 之后：'肥力'问题仍返回 type 4，不误判 type 5"""
    qt, _ = _identify("我的田肥力怎么样？")
    assert qt == 4, f"期望 TYPE_4（肥力），实际 TYPE_{qt}"


def test_type5_no_collision_with_type1():
    """type 5 问题不含'稳定'，不误命中 TYPE_1 的'等级稳定'"""
    from framework.agents.nodes import QUESTION_TYPE_1_KEYWORDS
    type5_questions = [
        "我的田耕地质量等级是多少",
        "查询地块的综合指数和障碍度排序",
        "这块地的耕地质量等级评价结果",
    ]
    for q in type5_questions:
        # 不应命中任何 TYPE_1 关键词
        assert not any(kw in q for kw in QUESTION_TYPE_1_KEYWORDS), (
            f"type 5 问题「{q}」误命中 TYPE_1 关键词"
        )
        qt, _ = _identify(q)
        assert qt == 5, f"问题「{q}」期望 TYPE_5，实际 TYPE_{qt}"


def test_type5_keyword_function_direct():
    """直接测试 _identify_question_type_keyword 返回 (5, relevance)"""
    from framework.agents.nodes import _identify_question_type_keyword
    qt, rel = _identify_question_type_keyword("我的田耕地质量等级是多少")
    assert qt == 5
    assert rel >= 0.3


def test_reference_questions_has_type5():
    """REFERENCE_QUESTIONS 应含 key 5（至少 3 个质量等级评价问题）"""
    from framework.agents.nodes import REFERENCE_QUESTIONS
    assert 5 in REFERENCE_QUESTIONS, "REFERENCE_QUESTIONS 缺少 key 5"
    assert len(REFERENCE_QUESTIONS[5]) >= 3, (
        f"REFERENCE_QUESTIONS[5] 应至少 3 个问题，实际 {len(REFERENCE_QUESTIONS.get(5, []))}"
    )
    print("✓ REFERENCE_QUESTIONS[5] 存在且含 >= 3 个问题")


def test_type5_questions_routed_to_type5():
    """REFERENCE_QUESTIONS[5] 的每个问题经 identify_question_type 返回 5"""
    from framework.agents.nodes import REFERENCE_QUESTIONS
    for q in REFERENCE_QUESTIONS[5]:
        qt, _ = _identify(q)
        assert qt == 5, f"type 5 问题「{q}」期望 TYPE_5，实际 TYPE_{qt}"


def test_type5_questions_route_to_farmer():
    """REFERENCE_QUESTIONS[5] 的每个问题经 RoleRouter 识别为 farmer"""
    from framework.agents.nodes import REFERENCE_QUESTIONS
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    for q in REFERENCE_QUESTIONS[5]:
        role = router.identify_role(q)
        assert role == "farmer", f"type 5 问题「{q}」期望 farmer 角色，实际 {role}"


if __name__ == "__main__":
    test_type1_stability_province_question()
    test_type1_stability_county_question()
    test_type1_stability_farmer_question()
    test_type1_attention_list_question()
    test_type2_acidification_degree_question()
    test_type2_remediation_dosage_question()
    test_type2_landuse_acidification_question()
    test_type2_no_generic_words_collision()
    test_type3_potential_question()
    test_type3_county_potential_distribution()
    test_type3_farmer_plot_diagnosis()
    test_type3_problem_identification()
    test_type4_organic_matter_content()
    test_type4_manure_dosage()
    test_type4_fertility_ml()
    test_type4_county_organic_average()
    test_keyword_match_priority_over_vector()
    test_type_order_no_cross_collision()
    test_type4_soc_query()
    test_type4_dose_query()
    test_type4_straw_query()
    test_type2_farmer_severity()
    test_unrelated_question_returns_zero()
    test_all_xlsx_classic_questions_routed()
    test_type5_grade_quality_question()
    test_type5_comprehensive_index_question()
    test_type5_grade_evaluation_question()
    test_type5_keyword_branch_after_type4()
    test_type5_no_collision_with_type1()
    test_type5_keyword_function_direct()
    test_reference_questions_has_type5()
    test_type5_questions_routed_to_type5()
    test_type5_questions_route_to_farmer()
    print("\n全部问题类型关键词测试通过！")
