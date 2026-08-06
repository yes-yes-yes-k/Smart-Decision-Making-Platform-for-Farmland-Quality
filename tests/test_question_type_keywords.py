"""测试问题类型关键词路由覆盖 xlsx 经典问题（D5）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _identify(question):
    from framework.agents.nodes import identify_question_type
    return identify_question_type(question)


MODEL_TO_QTYPE = {
    "model-1": 1, "model-2": 6, "model-3": 3,
    "model-4": 2, "model-5": 7, "model-6": 4, "model-7": 5,
}


def _expand(stems, prefixes, suffixes):
    """由基础句干 × 前缀 × 后缀展开为 ≥20 条问题，去重保序。"""
    out, seen = [], set()
    for s in stems:
        for p in prefixes:
            for suf in suffixes:
                c = p + s + suf
                if c not in seen:
                    seen.add(c)
                    out.append(c)
    return out


def _assert_rule_batch(questions, base_qtype, expected_model):
    from framework.agents.exclusive_rules import apply_exclusive_rules
    assert len(questions) >= 20, f"{expected_model} 正例应 ≥20，实际 {len(questions)}"
    for q in questions:
        final_type, status = apply_exclusive_rules(q, base_qtype, {"scale": "地块"})
        exp = MODEL_TO_QTYPE[expected_model]
        assert final_type == exp, f"「{q}」应路由到 {expected_model}(type {exp})，实际 type {final_type}"
        assert status == "normal", f"「{q}」状态应为 normal，实际 {status}"


def _assert_not_routed_to(questions, base_qtype, forbidden_model):
    from framework.agents.exclusive_rules import apply_exclusive_rules
    forb = MODEL_TO_QTYPE[forbidden_model]
    for q in questions:
        final_type, _ = apply_exclusive_rules(q, base_qtype, {"scale": "地块"})
        assert final_type != forb, f"「{q}」不应路由到 {forbidden_model}"


PREFIXES = ["", "全省", "全县", "我们县", "本县", "辖区"]
SUFFIXES = ["", "？"]
MODEL3_STEMS = ["耕地质量现状评价", "土壤障碍现状如何", "耕地质量现状诊断",
                "作物生长障碍现状评价", "耕地退化现状如何", "土壤环境现状评价",
                "耕地质量现状如何", "土壤肥力现状诊断", "耕地酸碱现状评价",
                "耕地质量现状评估"]
MODEL7_STEMS = ["耕地质量等级评价结果", "耕地质量等级评价", "综合指数和障碍度排序",
                "耕地质量等级评定", "耕地质量等级是多少", "质量等级评价结果",
                "耕地质量等级综合评价", "地块质量等级评价"]
MODEL2_STEMS = ["耕地质量提升潜力", "耕地质量潜力评估", "增产潜力多大",
                "改良片区提升潜力", "耕地提升空间", "目标等级提升潜力",
                "潜力分布范围", "提升潜力评估"]
MODEL4_STEMS = ["酸化调理剂选择", "酸化调理剂用法", "石灰改良酸化土壤",
                "碱性材料作用", "木本泥炭作用", "酸性改良剂用法",
                "酸化治理调理剂选择"]
MODEL6_STEMS = ["有机肥每亩施用量", "有机质投入量", "秸秆每亩施用量",
                "有机肥施用量多少", "有机质投入量多少", "有机肥投入量"]


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
    """潜力评估 → TYPE_6（model-2）"""
    qt, _ = _identify("辖区耕地质量提升的总体潜力有多大？可增产多少粮食？")
    assert qt == 6


def test_type3_county_potential_distribution():
    """县域优先改良片区 → TYPE_6"""
    qt, _ = _identify("我们县划定的优先改良片区具体在哪几个村？每块潜力多大？")
    assert qt == 6


def test_type3_farmer_plot_diagnosis():
    """农户地块诊断"毛病" → TYPE_3"""
    qt, _ = _identify("我这块地到底有啥毛病？")
    assert qt == 3


def test_type3_problem_identification():
    """主要问题/障碍因素 → TYPE_3"""
    qt, _ = _identify("全省耕地质量存在哪些问题？")
    assert qt == 3


def test_type4_organic_matter_content():
    """有机质含量 → TYPE_7（model-5）"""
    qt, _ = _identify("全省耕地土壤有机质含量如何，空间分布情况？")
    assert qt == 7


def test_type4_manure_dosage():
    """有机肥/秸秆施用量 → TYPE_7"""
    qt, _ = _identify("为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？")
    assert qt == 7


def test_type4_fertility_ml():
    """农户肥力/SOC → TYPE_4"""
    qt, _ = _identify("我的田肥力怎么样？")
    assert qt == 4


def test_type4_county_organic_average():
    """县域有机质平均含量 → TYPE_7"""
    qt, _ = _identify("本县耕地土壤有机质平均含量是多少？")
    assert qt == 7


def test_keyword_match_priority_over_vector():
    """D5：关键词匹配优先于向量匹配。

    即使向量返回不同的（更高分）类型，含具体关键词的问题仍应被关键词逻辑判定。
    手动 patch routing._identify_question_type_vector（兼容 __main__ 直接运行，无需 pytest fixture）。
    """
    from framework.agents import routing

    real_vector = routing._identify_question_type_vector
    try:
        # 向量返回 TYPE_2 高分，但关键词应判定为 TYPE_7
        routing._identify_question_type_vector = lambda q: (2, 0.95)
        qt, _ = routing.identify_question_type("有机肥每亩施用量多少？")
        assert qt == 7, f"关键词优先应返回 TYPE_7，实际 {qt}"
        # 向量返回 TYPE_4 高分，但关键词应判定为 TYPE_2
        routing._identify_question_type_vector = lambda q: (4, 0.95)
        qt, _ = routing.identify_question_type("我要施加多少碱性调理剂？")
        assert qt == 2, f"关键词优先应返回 TYPE_2，实际 {qt}"
    finally:
        routing._identify_question_type_vector = real_vector
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
    qt, _ = _identify("我这块地预测需要施多少肥？")
    assert qt == 4


def test_type4_nitrogen_fertilizer_dose_query():
    """氮肥施用量查询 → TYPE_4（model-6）"""
    qt, _ = _identify("我的田施氮肥施多少？")
    assert qt == 4


def test_type4_straw_query():
    """秸秆还田 → TYPE_7"""
    qt, _ = _identify("秸秆还田每亩施用量多少？")
    assert qt == 7


def test_type2_farmer_severity():
    """农户酸化严重 → TYPE_2"""
    qt, _ = _identify("我的这块田酸化严重吗？")
    assert qt == 2


def test_unrelated_question_returns_zero():
    """无关问题 → TYPE_0（强制 embedding 不可用，纯关键词路径确定返回 0，避免向量阈值边界 flaky）"""
    from framework.agents import routing

    real_flag = routing.EMBEDDING_AVAILABLE
    try:
        routing.EMBEDDING_AVAILABLE = False
        qt, _ = _identify("今天天气怎么样？")
        assert qt == 0, f"无关问题期望 TYPE_0，实际 {qt}"
    finally:
        routing.EMBEDDING_AVAILABLE = real_flag
    print("✓ 无关问题返回 TYPE_0")


def test_all_xlsx_classic_questions_routed():
    """xlsx 全部经典问题均能路由到非 0 类型（覆盖性断言）"""
    cases = [
        ("查询区域内耕地质量等级整体稳定吗？", 1),
        ("查询区域内哪些高等级耕地存在退化风险？", 1),
        ("本县哪些乡镇或地块等级稳定性较弱，需要现场复核？", 1),
        ("我的这块田质量等级稳不稳？", 1),
        ("查询区域内哪些对象需要纳入重点关注清单？", 1),
        ("辖区耕地质量提升的总体潜力有多大？可增产多少粮食？", 6),
        ("我们县划定的优先改良片区具体在哪几个村？每块潜力多大？", 6),
        ("我这块地到底有啥毛病？", 3),
        ("全省耕地质量存在哪些问题？", 3),
        ("县/乡镇里的耕地在哪些方面有问题", 3),
        ("查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？", 2),
        ("我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？", 2),
        ("查询区域内不同土地利用类型的酸化程度", 2),
        ("我的这块田酸化严重吗？", 2),
        ("全省耕地土壤有机质含量如何，空间分布情况？", 7),
        ("为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？", 7),
        ("本县耕地土壤有机质平均含量是多少？", 7),
        ("耕地有机质含量低的原因是什么？", 7),
        ("我的田肥力怎么样？", 4),
        ("我的田土壤有机碳含量大概多少？", 4),
        ("我这块地大概需要施多少有机肥？", 7),
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


def test_capability_has_five_dim_fields():
    """ProfessionalCapability 应含 analysis_scale/data_type 字段且 7 个能力均已填充"""
    from framework.agents.capabilities import PROFESSIONAL_CAPABILITIES
    for cap in PROFESSIONAL_CAPABILITIES:
        assert hasattr(cap, "analysis_scale"), f"{cap.agent_id} 缺少 analysis_scale"
        assert hasattr(cap, "data_type"), f"{cap.agent_id} 缺少 data_type"
        assert cap.analysis_scale, f"{cap.agent_id} 的 analysis_scale 为空"
        assert cap.data_type, f"{cap.agent_id} 的 data_type 为空"
    assert len(PROFESSIONAL_CAPABILITIES) == 7


def test_routing_module_migrated():
    """路由判定函数应从 routing 模块导出且签名向后兼容"""
    from framework.agents import routing
    for name in ("identify_question_type", "_identify_question_type_keyword",
                 "_identify_question_type_vector", "check_relevance"):
        assert hasattr(routing, name), f"routing 缺少 {name}"
    # identify_question_type 支持可选 context 参数
    qt, rel = routing.identify_question_type("我的这块田稳不稳")
    assert qt == 1
    qt2, rel2 = routing.identify_question_type("我的这块田稳不稳", {"scale": "地块"})
    assert qt2 == qt  # context 追加不改变无规则命中的既有行为


def test_pair_model3_vs_model7_positive():
    """model-3/7：现状评价正例(→model-3) 与 质量等级评价正例(→model-7) 各 ≥20"""
    _assert_rule_batch(_expand(MODEL3_STEMS, PREFIXES, SUFFIXES), 5, "model-3")
    _assert_rule_batch(_expand(MODEL7_STEMS, PREFIXES, SUFFIXES), 3, "model-7")


def test_pair_model3_vs_model7_negative():
    """model-3/7：反例（不误路由到对方）各 ≥20"""
    _assert_not_routed_to(_expand(MODEL3_STEMS, PREFIXES, SUFFIXES), 5, "model-7")
    _assert_not_routed_to(_expand(MODEL7_STEMS, PREFIXES, SUFFIXES), 3, "model-3")


def test_pair_model2_vs_model7_positive():
    """model-2/7：潜力正例(→model-2) 与 质量等级评价正例(→model-7) 各 ≥20"""
    _assert_rule_batch(_expand(MODEL2_STEMS, PREFIXES, SUFFIXES), 5, "model-2")
    _assert_rule_batch(_expand(MODEL7_STEMS, PREFIXES, SUFFIXES), 6, "model-7")


def test_pair_model2_vs_model7_negative():
    """model-2/7：反例各 ≥20"""
    _assert_not_routed_to(_expand(MODEL2_STEMS, PREFIXES, SUFFIXES), 5, "model-7")
    _assert_not_routed_to(_expand(MODEL7_STEMS, PREFIXES, SUFFIXES), 6, "model-2")


def test_pair_model4_vs_model6_positive():
    """model-4/6：酸化调理剂正例(→model-4) 与 有机质投入量正例(→model-6) 各 ≥20"""
    _assert_rule_batch(_expand(MODEL4_STEMS, PREFIXES, SUFFIXES), 4, "model-4")
    _assert_rule_batch(_expand(MODEL6_STEMS, PREFIXES, SUFFIXES), 2, "model-6")


def test_pair_model4_vs_model6_negative():
    """model-4/6：反例各 ≥20"""
    _assert_not_routed_to(_expand(MODEL4_STEMS, PREFIXES, SUFFIXES), 4, "model-6")
    _assert_not_routed_to(_expand(MODEL6_STEMS, PREFIXES, SUFFIXES), 2, "model-4")


def test_five_dim_does_not_break_existing_1to1_routing():
    """context 提供时，未命中排他规则的正常问题保持既有 question_type"""
    from framework.agents import routing
    real_flag = routing.EMBEDDING_AVAILABLE
    try:
        routing.EMBEDDING_AVAILABLE = False  # 纯关键词，确定性
        cases = [
            ("查询区域内哪些高等级耕地存在退化风险？", 1),
            ("辖区耕地质量提升的总体潜力有多大？可增产多少粮食？", 6),
            ("我这块地到底有啥毛病？", 3),
            ("查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？", 2),
            ("我的田土壤有机碳含量大概多少？", 4),
            ("我的田耕地质量等级是多少？", 5),
            ("全省耕地土壤有机质含量如何，空间分布情况？", 7),
        ]
        for q, expected in cases:
            qt, _ = routing.identify_question_type(q, {"scale": "县"})
            assert qt == expected, f"「{q}」期望 TYPE_{expected}，实际 TYPE_{qt}"
    finally:
        routing.EMBEDDING_AVAILABLE = real_flag


def test_normal_questions_not_degraded():
    """未命中排他规则的正常问题，routing_status 保持 normal"""
    from framework.agents.exclusive_rules import apply_exclusive_rules as _apply
    final_type, status = _apply("我的田肥力怎么样", 4, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 4


def test_all_confusing_pair_batches_size_ge_20():
    """三组易混淆对正例/反例批量规模均 ≥20"""
    assert len(_expand(MODEL3_STEMS, PREFIXES, SUFFIXES)) >= 20
    assert len(_expand(MODEL7_STEMS, PREFIXES, SUFFIXES)) >= 20
    assert len(_expand(MODEL2_STEMS, PREFIXES, SUFFIXES)) >= 20
    assert len(_expand(MODEL4_STEMS, PREFIXES, SUFFIXES)) >= 20
    assert len(_expand(MODEL6_STEMS, PREFIXES, SUFFIXES)) >= 20


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
    test_capability_has_five_dim_fields()
    test_routing_module_migrated()
    test_pair_model3_vs_model7_positive()
    test_pair_model3_vs_model7_negative()
    test_pair_model2_vs_model7_positive()
    test_pair_model2_vs_model7_negative()
    test_pair_model4_vs_model6_positive()
    test_pair_model4_vs_model6_negative()
    test_five_dim_does_not_break_existing_1to1_routing()
    test_normal_questions_not_degraded()
    test_all_confusing_pair_batches_size_ge_20()
    print("\n全部问题类型关键词测试通过！")
