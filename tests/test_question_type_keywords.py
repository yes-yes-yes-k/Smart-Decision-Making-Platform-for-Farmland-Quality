"""测试问题类型关键词路由覆盖 xlsx 经典问题（D5）。"""
import sys
import os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def disable_llm_routing(monkeypatch):
    """禁用 LLM 路由，确保关键词匹配不被 LLM 初判覆盖。

    ROUTING_MODE 默认 "llm" 时，LLM 路由器会将有机质相关问题
    （如「全省耕地土壤有机质含量如何，空间分布情况？」）误判为 type 0，
    覆盖关键词匹配应返回的 type 5。本套件聚焦关键词路由行为，
    统一禁用 LLM 路由以保证确定性与既有 1..5 路由不回归。
    """
    from framework.config import Config
    monkeypatch.setattr(Config, "ROUTING_MODE", "keyword")


def _identify(question):
    from framework.agents.nodes import identify_question_type
    return identify_question_type(question)


MODEL_TO_QTYPE = {
    "model-1": 1, "model-2": 2, "model-3": 3,
    "model-4": 4, "model-5": 5, "model-6": 6,
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
# model-3（障碍诊断）：现状评价正例
MODEL3_STEMS = ["耕地质量现状评价", "土壤障碍现状如何", "耕地质量现状诊断",
                "作物生长障碍现状评价", "耕地退化现状如何", "土壤环境现状评价",
                "耕地质量现状如何", "土壤肥力现状诊断", "耕地酸碱现状评价",
                "耕地质量现状评估"]
# model-2（质量等级评价）：等级评价正例
MODEL2_STEMS = ["耕地质量等级评价结果", "耕地质量等级评价", "综合指数和障碍度排序",
                "耕地质量等级评定", "耕地质量等级是多少", "质量等级评价结果",
                "耕地质量等级综合评价", "地块质量等级评价"]
# model-4（酸化改良）：酸化调理剂正例
MODEL4_STEMS = ["酸化调理剂选择", "酸化调理剂用法", "石灰改良酸化土壤",
                "碱性材料作用", "木本泥炭作用", "酸性改良剂用法",
                "酸化治理调理剂选择"]
# model-5（有机质提升）：有机质投入量正例
MODEL5_STEMS = ["有机肥每亩施用量", "有机质投入量", "秸秆每亩施用量",
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


def test_type4_acidification_degree_question():
    """酸化程度判定 → TYPE_4（model-4）"""
    qt, _ = _identify("查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？")
    assert qt == 4


def test_type4_remediation_dosage_question():
    """农户端碱性调理剂施用量 → TYPE_4"""
    qt, _ = _identify("我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？")
    assert qt == 4


def test_type4_landuse_acidification_question():
    """不同土地利用类型酸化 → TYPE_4"""
    qt, _ = _identify("查询区域内不同土地利用类型的酸化程度")
    assert qt == 4


def test_type4_no_generic_words_collision():
    """TYPE_4 已移除通用词"施加""用量"，但含具体词"调理剂"仍命中 TYPE_4"""
    from framework.agents.nodes import QUESTION_TYPE_4_KEYWORDS
    assert "施加" not in QUESTION_TYPE_4_KEYWORDS
    assert "用量" not in QUESTION_TYPE_4_KEYWORDS
    assert "调理剂" in QUESTION_TYPE_4_KEYWORDS


def test_type3_farmer_plot_diagnosis():
    """农户地块诊断"毛病" → TYPE_3"""
    qt, _ = _identify("我这块地到底有啥毛病？")
    assert qt == 3


def test_type3_problem_identification():
    """主要问题/障碍因素 → TYPE_3"""
    qt, _ = _identify("全省耕地质量存在哪些问题？")
    assert qt == 3


def test_type5_organic_matter_content():
    """有机质含量 → TYPE_5（model-5）"""
    qt, _ = _identify("全省耕地土壤有机质含量如何，空间分布情况？")
    assert qt == 5


def test_type5_manure_dosage():
    """有机肥/秸秆施用量 → TYPE_5"""
    qt, _ = _identify("为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？")
    assert qt == 5


def test_type5_county_organic_average():
    """县域有机质平均含量 → TYPE_5"""
    qt, _ = _identify("本县耕地土壤有机质平均含量是多少？")
    assert qt == 5


def test_keyword_match_priority_over_vector():
    """D5：关键词匹配优先于向量匹配。

    即使向量返回不同的（更高分）类型，含具体关键词的问题仍应被关键词逻辑判定。
    手动 patch routing._identify_question_type_vector（兼容 __main__ 直接运行，无需 pytest fixture）。
    """
    from framework.agents import routing

    real_vector = routing._identify_question_type_vector
    try:
        # 向量返回 TYPE_4 高分，但关键词应判定为 TYPE_5（有机质）
        routing._identify_question_type_vector = lambda q: (4, 0.95)
        qt, _ = routing.identify_question_type("有机肥每亩施用量多少？")
        assert qt == 5, f"关键词优先应返回 TYPE_5，实际 {qt}"
        # 向量返回 TYPE_1 高分，但关键词应判定为 TYPE_4（酸化）
        routing._identify_question_type_vector = lambda q: (1, 0.95)
        qt, _ = routing.identify_question_type("我要施加多少碱性调理剂？")
        assert qt == 4, f"关键词优先应返回 TYPE_4，实际 {qt}"
    finally:
        routing._identify_question_type_vector = real_vector
    print("✓ 关键词匹配优先于向量匹配（D5）")


def test_type_order_no_cross_collision():
    """关键词不跨类型重叠：TYPE_3(障碍) 不含酸化词，TYPE_4(酸化) 不含稳定词，TYPE_5(有机质) 不跨入 TYPE_3/4/1"""
    from framework.agents.nodes import (
        QUESTION_TYPE_1_KEYWORDS, QUESTION_TYPE_3_KEYWORDS,
        QUESTION_TYPE_4_KEYWORDS, QUESTION_TYPE_5_KEYWORDS,
    )
    # "酸化"属 TYPE_4，不应出现在 TYPE_3
    assert not any("酸化" in kw for kw in QUESTION_TYPE_3_KEYWORDS)
    # "稳定"属 TYPE_1，不应出现在 TYPE_4
    assert not any("稳定" in kw for kw in QUESTION_TYPE_4_KEYWORDS)
    # "有机质"属 TYPE_5，不应出现在 TYPE_3/4/1
    assert not any("有机质" in kw for kw in QUESTION_TYPE_3_KEYWORDS)
    assert not any("有机质" in kw for kw in QUESTION_TYPE_4_KEYWORDS)
    assert not any("有机质" in kw for kw in QUESTION_TYPE_1_KEYWORDS)


def test_type5_straw_query():
    """秸秆还田 → TYPE_5"""
    qt, _ = _identify("秸秆还田每亩施用量多少？")
    assert qt == 5


def test_type4_farmer_severity():
    """农户酸化严重 → TYPE_4"""
    qt, _ = _identify("我的这块田酸化严重吗？")
    assert qt == 4


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
        ("我这块地到底有啥毛病？", 3),
        ("全省耕地质量存在哪些问题？", 3),
        ("县/乡镇里的耕地在哪些方面有问题", 3),
        ("查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？", 4),
        ("我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？", 4),
        ("查询区域内不同土地利用类型的酸化程度", 4),
        ("我的这块田酸化严重吗？", 4),
        ("全省耕地土壤有机质含量如何，空间分布情况？", 5),
        ("为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？", 5),
        ("本县耕地土壤有机质平均含量是多少？", 5),
        ("耕地有机质含量低的原因是什么？", 5),
        ("我这块地大概需要施多少有机肥？", 5),
        ("我的田耕地质量等级是多少？", 2),
        ("查询地块的综合指数和障碍度排序", 2),
    ]
    for q, expected in cases:
        qt, _ = _identify(q)
        assert qt == expected, f"问题「{q}」期望 TYPE_{expected}，实际 TYPE_{qt}"


def test_type2_grade_quality_question():
    """质量等级评价 → TYPE_2（model-2）"""
    qt, _ = _identify("我的田耕地质量等级是多少？")
    assert qt == 2, f"期望 TYPE_2，实际 {qt}"


def test_type2_comprehensive_index_question():
    """综合指数/障碍度排序 → TYPE_2"""
    qt, _ = _identify("查询地块的综合指数和障碍度排序")
    assert qt == 2, f"期望 TYPE_2，实际 {qt}"


def test_type2_grade_evaluation_question():
    """耕地质量等级评价结果 → TYPE_2"""
    qt, _ = _identify("这块地的耕地质量等级评价结果")
    assert qt == 2, f"期望 TYPE_2，实际 {qt}"


def test_type2_keyword_branch_after_type1():
    """type 2 分支在 type 1 之后：含'稳不稳'的等级问题仍返回 type 1，不误判 type 2"""
    qt, _ = _identify("我的这块田质量等级稳不稳？")
    assert qt == 1, f"期望 TYPE_1（稳定性），实际 TYPE_{qt}"


def test_type2_no_collision_with_type1():
    """type 2 问题不含稳定性词，不误命中 TYPE_1 的'等级稳定'"""
    from framework.agents.nodes import QUESTION_TYPE_1_KEYWORDS
    type2_questions = [
        "我的田耕地质量等级是多少",
        "查询地块的综合指数和障碍度排序",
        "这块地的耕地质量等级评价结果",
    ]
    for q in type2_questions:
        # 不应命中任何 TYPE_1 关键词
        assert not any(kw in q for kw in QUESTION_TYPE_1_KEYWORDS), (
            f"type 2 问题「{q}」误命中 TYPE_1 关键词"
        )
        qt, _ = _identify(q)
        assert qt == 2, f"问题「{q}」期望 TYPE_2，实际 TYPE_{qt}"


def test_type2_keyword_function_direct():
    """直接测试 _identify_question_type_keyword 返回 (2, relevance)"""
    from framework.agents.nodes import _identify_question_type_keyword
    qt, rel = _identify_question_type_keyword("我的田耕地质量等级是多少")
    assert qt == 2
    assert rel >= 0.3


def test_reference_questions_has_type2():
    """REFERENCE_QUESTIONS 应含 key 2（至少 3 个质量等级评价问题）"""
    from framework.agents.nodes import REFERENCE_QUESTIONS
    assert 2 in REFERENCE_QUESTIONS, "REFERENCE_QUESTIONS 缺少 key 2"
    assert len(REFERENCE_QUESTIONS[2]) >= 3, (
        f"REFERENCE_QUESTIONS[2] 应至少 3 个问题，实际 {len(REFERENCE_QUESTIONS.get(2, []))}"
    )
    print("✓ REFERENCE_QUESTIONS[2] 存在且含 >= 3 个问题")


def test_type2_questions_routed_to_type2():
    """REFERENCE_QUESTIONS[2] 的每个问题经 identify_question_type 返回 2"""
    from framework.agents.nodes import REFERENCE_QUESTIONS
    for q in REFERENCE_QUESTIONS[2]:
        qt, _ = _identify(q)
        assert qt == 2, f"type 2 问题「{q}」期望 TYPE_2，实际 TYPE_{qt}"


def test_capability_has_analysis_and_spatial_requirement_fields():
    """ProfessionalCapability 应声明展示维度及中央守卫所需字段。"""
    from framework.agents.capabilities import PROFESSIONAL_CAPABILITIES
    for cap in PROFESSIONAL_CAPABILITIES:
        assert hasattr(cap, "analysis_scale"), f"{cap.agent_id} 缺少 analysis_scale"
        assert hasattr(cap, "data_type"), f"{cap.agent_id} 缺少 data_type"
        assert cap.analysis_scale, f"{cap.agent_id} 的 analysis_scale 为空"
        assert cap.data_type, f"{cap.agent_id} 的 data_type 为空"
        assert cap.supported_object_types, f"{cap.agent_id} 未声明支持的空间对象"
        assert isinstance(cap.requires_spatial_object, bool)
        assert isinstance(cap.supports_scenario, bool)
        assert isinstance(cap.required_scenario_inputs, tuple)
    assert len(PROFESSIONAL_CAPABILITIES) == 6


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


def test_pair_model3_vs_model2_positive():
    """model-3/2：现状评价正例(→model-3) 与 质量等级评价正例(→model-2) 各 ≥20"""
    _assert_rule_batch(_expand(MODEL3_STEMS, PREFIXES, SUFFIXES), 2, "model-3")
    _assert_rule_batch(_expand(MODEL2_STEMS, PREFIXES, SUFFIXES), 3, "model-2")


def test_pair_model3_vs_model2_negative():
    """model-3/2：反例（不误路由到对方）各 ≥20"""
    _assert_not_routed_to(_expand(MODEL3_STEMS, PREFIXES, SUFFIXES), 2, "model-2")
    _assert_not_routed_to(_expand(MODEL2_STEMS, PREFIXES, SUFFIXES), 3, "model-3")


def test_pair_model4_vs_model5_positive():
    """model-4/5：酸化调理剂正例(→model-4) 与 有机质正例(→model-5) 各 ≥20"""
    # 酸化调理剂：base 为 model-5(有机质) 时，排他规则修正到 model-4
    _assert_rule_batch(_expand(MODEL4_STEMS, PREFIXES, SUFFIXES), 5, "model-4")
    # 有机质：与酸化关键词不重叠，排他规则不触发，保持 model-5
    _assert_rule_batch(_expand(MODEL5_STEMS, PREFIXES, SUFFIXES), 5, "model-5")


def test_pair_model4_vs_model5_negative():
    """model-4/5：反例各 ≥20"""
    _assert_not_routed_to(_expand(MODEL4_STEMS, PREFIXES, SUFFIXES), 5, "model-5")
    _assert_not_routed_to(_expand(MODEL5_STEMS, PREFIXES, SUFFIXES), 5, "model-4")


def test_five_dim_does_not_break_existing_1to1_routing():
    """context 提供时，未命中排他规则的正常问题保持既有 question_type"""
    from framework.agents import routing
    real_flag = routing.EMBEDDING_AVAILABLE
    try:
        routing.EMBEDDING_AVAILABLE = False  # 纯关键词，确定性
        cases = [
            ("查询区域内哪些高等级耕地存在退化风险？", 1),
            ("我这块地到底有啥毛病？", 3),
            ("查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？", 4),
            ("我的田耕地质量等级是多少？", 2),
            ("全省耕地土壤有机质含量如何，空间分布情况？", 5),
        ]
        for q, expected in cases:
            qt, _ = routing.identify_question_type(q, {"scale": "县"})
            assert qt == expected, f"「{q}」期望 TYPE_{expected}，实际 TYPE_{qt}"
    finally:
        routing.EMBEDDING_AVAILABLE = real_flag


def test_normal_questions_not_degraded():
    """未命中排他规则的正常问题，routing_status 保持 normal"""
    from framework.agents.exclusive_rules import apply_exclusive_rules as _apply
    final_type, status = _apply("我的田稳不稳", 1, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 1


def test_all_confusing_pair_batches_size_ge_20():
    """两组易混淆对正例/反例批量规模均 ≥20"""
    assert len(_expand(MODEL3_STEMS, PREFIXES, SUFFIXES)) >= 20
    assert len(_expand(MODEL2_STEMS, PREFIXES, SUFFIXES)) >= 20
    assert len(_expand(MODEL4_STEMS, PREFIXES, SUFFIXES)) >= 20
    assert len(_expand(MODEL5_STEMS, PREFIXES, SUFFIXES)) >= 20


def test_confusing_pair_positive_and_negative_batches_ge_20():
    """两组易混淆对的正例与反例批量均 ≥20（反例与正例同源句干联动）。"""
    for name, stems in (("model-3", MODEL3_STEMS), ("model-2", MODEL2_STEMS),
                        ("model-4", MODEL4_STEMS), ("model-5", MODEL5_STEMS)):
        batch = _expand(stems, PREFIXES, SUFFIXES)
        assert len(batch) >= 20, f"{name} 正例/反例批量应 ≥20，实际 {len(batch)}"


def test_extract_business_task_keywords():
    """_extract_five_dim_context 应从问题文本提取 business_task 标签"""
    from framework.agents.nodes import _extract_five_dim_context, BUSINESS_TASK_KEYWORDS
    # 关键词表完整性与 Design Doc 决策 A 一致
    assert set(BUSINESS_TASK_KEYWORDS.keys()) == {
        "障碍诊断", "酸化改良", "有机质培肥", "稳定性评价", "质量等级评价",
    }
    assert BUSINESS_TASK_KEYWORDS["障碍诊断"] == ("诊断", "毛病", "障碍")
    assert BUSINESS_TASK_KEYWORDS["酸化改良"] == ("酸化", "调理剂", "石灰", "治酸", "pH提升", "碱性")
    assert BUSINESS_TASK_KEYWORDS["有机质培肥"] == ("有机质", "有机肥", "秸秆", "培肥")
    assert BUSINESS_TASK_KEYWORDS["稳定性评价"] == ("稳定性", "退化", "掉级", "稳定")
    assert BUSINESS_TASK_KEYWORDS["质量等级评价"] == ("质量等级", "等级评价", "综合指数", "等级评定")

    cases = [
        ("我这块地到底有啥毛病", "障碍诊断"),
        ("土壤酸化了怎么治酸", "酸化改良"),
        ("有机肥每亩施用量多少", "有机质培肥"),
        ("这块地稳定性退化风险", "稳定性评价"),  # "稳定性"/"退化" 命中稳定性评价
        ("耕地质量等级评价结果", "质量等级评价"),
    ]
    for question, expected_task in cases:
        state = {"request": {"question": question}}
        ctx = _extract_five_dim_context(state)
        assert ctx["business_task"] == expected_task, (
            f"「{question}」business_task 应为 {expected_task}，实际 {ctx.get('business_task')}"
        )


def test_extract_expected_output_keywords():
    """_extract_five_dim_context 应从问题文本提取 expected_output 标签"""
    from framework.agents.nodes import _extract_five_dim_context, EXPECTED_OUTPUT_KEYWORDS
    assert set(EXPECTED_OUTPUT_KEYWORDS.keys()) == {"评价结果", "处方用量", "诊断报告"}
    assert EXPECTED_OUTPUT_KEYWORDS["评价结果"] == ("等级", "指数", "评价结果", "评定")
    assert EXPECTED_OUTPUT_KEYWORDS["处方用量"] == ("施多少", "每亩", "用量", "投入量")
    assert EXPECTED_OUTPUT_KEYWORDS["诊断报告"] == ("诊断", "问题", "毛病", "障碍")

    cases = [
        ("耕地质量等级评价结果", "评价结果"),
        ("有机肥每亩施用量多少", "处方用量"),
        ("我这块地到底有啥毛病", "诊断报告"),
    ]
    for question, expected_out in cases:
        state = {"request": {"question": question}}
        ctx = _extract_five_dim_context(state)
        assert ctx["expected_output"] == expected_out, (
            f"「{question}」expected_output 应为 {expected_out}，实际 {ctx.get('expected_output')}"
        )


def test_extract_five_dim_context_returns_four_fields():
    """_extract_five_dim_context 返回的 context 必含 scale/data_type/business_task/expected_output 四字段"""
    from framework.agents.nodes import _extract_five_dim_context
    ctx = _extract_five_dim_context({"request": {"question": "我的田耕地质量等级是多少"}})
    assert set(ctx.keys()) >= {"scale", "data_type", "business_task", "expected_output"}
    assert ctx["scale"] == "地块"  # "我的田" 命中地块
    assert ctx["data_type"] is not None


def test_v1_compat_context_none_identical_to_v1():
    """context=None 时 identify_question_type 行为与 v1 完全一致（不应用排他规则）"""
    from framework.agents import routing
    real_flag = routing.EMBEDDING_AVAILABLE
    try:
        routing.EMBEDDING_AVAILABLE = False  # 纯关键词，确定性
        cases = [
            ("我这块地到底有啥毛病？", 3),    # TYPE_3 关键词
            ("酸化调理剂每亩施用量", 4),      # TYPE_4 关键词
            ("有机肥每亩施用量多少", 5),      # TYPE_5 关键词
            ("这块地稳定性退化风险", 1),      # TYPE_1 关键词
            ("耕地质量等级评价结果", 2),      # TYPE_2 关键词
        ]
        for q, expected in cases:
            qt_no_ctx, _ = routing.identify_question_type(q)              # 无 context
            qt_with_none, _ = routing.identify_question_type(q, None)     # context=None
            assert qt_no_ctx == expected, f"无 context「{q}」期望 TYPE_{expected}，实际 TYPE_{qt_no_ctx}"
            assert qt_with_none == qt_no_ctx, f"context=None 应与无 context 一致"
    finally:
        routing.EMBEDDING_AVAILABLE = real_flag


def test_v1_compat_context_scale_only_does_not_trigger_dim_rules():
    """context 仅含 scale（v1 测试基础设施场景）不应触发 v1.1 维度规则"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # v1 测试中 _assert_rule_batch 传入 {"scale": "地块"}，
    # 维度规则要求 data_type+business_task 同时匹配，scale-only context 不应触发
    cases = [
        ("耕地质量现状评价如何", 2, 3),   # v1 规则：现状评价 → model-3
        ("酸化调理剂每亩施用量", 5, 4),   # v1 规则：酸化调理剂 → model-4
        ("这块地稳定性退化风险", 5, 1),   # v1 规则：稳定性风险 → model-1
        ("耕地质量等级评价结果", 5, 2),   # v1 规则：质量等级评价 → model-2
    ]
    for q, base, expected in cases:
        final_type, status = apply_exclusive_rules(q, base, {"scale": "地块"})
        assert (final_type, status) == (expected, "normal"), (
            f"scale-only context「{q}」应保持 v1 行为 (→{expected})，实际 ({final_type}, {status})"
        )


if __name__ == "__main__":
    from framework.config import Config
    Config.ROUTING_MODE = "keyword"
    test_type1_stability_province_question()
    test_type1_stability_county_question()
    test_type1_stability_farmer_question()
    test_type1_attention_list_question()
    test_type4_acidification_degree_question()
    test_type4_remediation_dosage_question()
    test_type4_landuse_acidification_question()
    test_type4_no_generic_words_collision()
    test_type3_farmer_plot_diagnosis()
    test_type3_problem_identification()
    test_type5_organic_matter_content()
    test_type5_manure_dosage()
    test_type5_county_organic_average()
    test_keyword_match_priority_over_vector()
    test_type_order_no_cross_collision()
    test_type5_straw_query()
    test_type4_farmer_severity()
    test_unrelated_question_returns_zero()
    test_all_xlsx_classic_questions_routed()
    test_type2_grade_quality_question()
    test_type2_comprehensive_index_question()
    test_type2_grade_evaluation_question()
    test_type2_keyword_branch_after_type1()
    test_type2_no_collision_with_type1()
    test_type2_keyword_function_direct()
    test_reference_questions_has_type2()
    test_type2_questions_routed_to_type2()
    test_capability_has_five_dim_fields()
    test_routing_module_migrated()
    test_pair_model3_vs_model2_positive()
    test_pair_model3_vs_model2_negative()
    test_pair_model4_vs_model5_positive()
    test_pair_model4_vs_model5_negative()
    test_five_dim_does_not_break_existing_1to1_routing()
    test_normal_questions_not_degraded()
    test_all_confusing_pair_batches_size_ge_20()
    test_confusing_pair_positive_and_negative_batches_ge_20()
    print("\n全部问题类型关键词测试通过！")
