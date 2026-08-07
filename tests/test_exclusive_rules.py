"""排他规则与「模型边界待确认」降级测试。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _apply(q, base_type, ctx=None):
    from framework.agents.exclusive_rules import apply_exclusive_rules
    return apply_exclusive_rules(q, base_type, ctx)


def test_rule_status_refers_to_model1():
    """现状评价 → model-1：候选为 model-5 时修正到 model-1(5→1)"""
    final_type, status = _apply("耕地质量现状评价如何", 5, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 1, f"现状评价应路由到 model-1(type 1)，实际 type {final_type}"


def test_rule_acidification_refers_to_model2():
    """酸化调理剂 → model-2(2)"""
    final_type, status = _apply("我要施加多少酸化调理剂", 3, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 2, f"酸化调理剂应路由到 model-2(type 2)，实际 type {final_type}"


def test_rule_stability_refers_to_model4():
    """稳定性风险 → model-4(4)"""
    final_type, status = _apply("这块地稳定性退化风险如何", 3, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 4, f"稳定性风险应路由到 model-4(type 4)，实际 type {final_type}"


def test_rule_grade_refers_to_model5():
    """质量等级评价 → model-5(5)"""
    final_type, status = _apply("耕地质量等级评价结果", 3, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 5, f"质量等级评价应路由到 model-5(type 5)，实际 type {final_type}"


def test_conflicting_rules_return_boundary_pending():
    """同一易混淆对内两条规则同时命中 → 边界待确认"""
    final_type, status = _apply("耕地质量等级现状评价", 1, {"scale": "地块"})
    assert status == "boundary_pending", f"冲突应降级 boundary_pending，实际 {status}"


def test_type0_untouched():
    """TYPE_0(RAG) 不应用排他规则"""
    final_type, status = _apply("什么是土壤酸化", 0, {"scale": "地块"})
    assert (final_type, status) == (0, "normal")


def test_model_id_to_question_type_mapping():
    from framework.agents.exclusive_rules import model_id_to_question_type
    assert model_id_to_question_type("model-1") == 1
    assert model_id_to_question_type("model-2") == 2
    assert model_id_to_question_type("model-3") == 3
    assert model_id_to_question_type("model-4") == 4
    assert model_id_to_question_type("model-5") == 5
    assert model_id_to_question_type("model-6") is None
    assert model_id_to_question_type("model-7") is None


def test_route_models_boundary_pending():
    """route_models 对 boundary_pending 返回降级分支，且缺省时保持旧行为"""
    from framework.agents.nodes import route_models
    assert route_models({"question_type": 2, "routing_status": "boundary_pending"}) == "boundary_pending"
    assert route_models({"question_type": 1}) == "execute_models"
    assert route_models({"question_type": 0}) == "rag_chat"


def test_aggregate_results_passthrough_boundary_pending():
    """aggregate_results 透传 routing_status 与降级提示"""
    from framework.agents.nodes import aggregate_results
    state = {
        "request": {"question": "耕地质量等级现状评价"},
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": 1,
        "relevance": 0.8,
        "routing_status": "boundary_pending",
    }
    result = aggregate_results(state)
    assert result["status"] == "completed"
    assert result["model_results"]["routing_status"] == "boundary_pending"
    assert result["model_results"]["degradation"]
    assert "模型边界待确认" in result["model_results"]["answer"]


def test_identify_question_node_writes_routing_status():
    """identify_question_node 写入 routing_status（缺省 normal）"""
    from framework.agents.nodes import identify_question_node
    state = {"request": {"question": "耕地质量现状评价如何", "scale": "地块"}}
    result = identify_question_node(state)
    assert result["routing_status"] == "normal"


def test_exclusive_rule_supports_dimension_conditions():
    """ExclusiveRule 支持 dimension_conditions 字段，且默认空 dict"""
    from framework.agents.exclusive_rules import ExclusiveRule

    # 默认构造：condition=None、dimension_conditions={}
    rule_default = ExclusiveRule(
        pair=frozenset({"model-1", "model-5"}),
        discriminator="测试",
    )
    assert rule_default.condition is None
    assert rule_default.dimension_conditions == {}
    assert rule_default.target == ""

    # 完整构造
    rule_full = ExclusiveRule(
        pair=frozenset({"model-1", "model-5"}),
        discriminator="分析尺度+数据类型+业务任务",
        condition=None,
        target="model-5",
        dimension_conditions={"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价"},
    )
    assert rule_full.target == "model-5"
    assert rule_full.dimension_conditions == {"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价"}

    # 现有 v1 规则：condition 保持字符串值，dimension_conditions 默认空
    rule_v1 = ExclusiveRule(
        pair=frozenset({"model-1", "model-5"}),
        discriminator="业务任务",
        condition="现状评价",
        target="model-1",
    )
    assert rule_v1.condition == "现状评价"
    assert rule_v1.dimension_conditions == {}


def test_existing_exclusive_rules_backward_compatible():
    """现有 4 条 v1 规则字段保持向后兼容：condition 为字符串、dimension_conditions 为空"""
    from framework.agents.exclusive_rules import EXCLUSIVE_RULES
    # v1 规则 = dimension_conditions 为空的规则（v1.1 维度规则有非空 dimension_conditions）
    v1_rules = [r for r in EXCLUSIVE_RULES if not r.dimension_conditions]
    # v1 规则应至少 4 条
    assert len(v1_rules) >= 4, f"v1 纯关键词规则应至少 4 条，实际 {len(v1_rules)}"
    for rule in v1_rules:
        # v1 规则 condition 必为字符串（非 None）
        assert isinstance(rule.condition, str), f"{rule} 的 condition 应为字符串"
        # v1 规则 dimension_conditions 必为空 dict
        assert rule.dimension_conditions == {}, f"{rule} 的 dimension_conditions 应为空"


def test_dimension_conditions_match_all_match():
    """context 四维全部满足 dimension_conditions → True"""
    from framework.agents.exclusive_rules import _dimension_conditions_match
    dim_conds = {"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价"}
    ctx = {"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价", "expected_output": "评价结果"}
    assert _dimension_conditions_match(dim_conds, ctx) is True


def test_dimension_conditions_match_partial_mismatch():
    """任一维度不匹配 → False"""
    from framework.agents.exclusive_rules import _dimension_conditions_match
    dim_conds = {"scale": "地块", "data_type": "评价结果"}
    assert _dimension_conditions_match(dim_conds, {"scale": "县", "data_type": "评价结果"}) is False
    assert _dimension_conditions_match(dim_conds, {"scale": "地块", "data_type": "指标数据"}) is False


def test_dimension_conditions_match_missing_field_in_context():
    """context 缺少声明维度 → 该维度视为不匹配 → False"""
    from framework.agents.exclusive_rules import _dimension_conditions_match
    dim_conds = {"scale": "地块", "business_task": "障碍诊断"}
    # context 缺 business_task 键
    assert _dimension_conditions_match(dim_conds, {"scale": "地块", "data_type": "指标数据"}) is False
    # context 中 business_task 为 None
    assert _dimension_conditions_match(dim_conds, {"scale": "地块", "business_task": None}) is False


def test_dimension_conditions_match_empty_conditions():
    """dimension_conditions 为空 → 跳过维度检查 → True"""
    from framework.agents.exclusive_rules import _dimension_conditions_match
    assert _dimension_conditions_match({}, {"scale": "地块"}) is True
    assert _dimension_conditions_match({}, None) is True


def test_dimension_conditions_match_none_context():
    """context 为 None 且 dimension_conditions 非空 → False"""
    from framework.agents.exclusive_rules import _dimension_conditions_match
    assert _dimension_conditions_match({"scale": "地块"}, None) is False


def test_apply_exclusive_rules_and_logic_condition_only():
    """AND 逻辑：v1 纯关键词规则（dimension_conditions 为空）行为不变"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # 现状评价 → model-1（无 dimension_conditions，仅关键词）
    final_type, status = apply_exclusive_rules("耕地质量现状评价如何", 5, {"scale": "地块"})
    assert (final_type, status) == (1, "normal")


def test_apply_exclusive_rules_and_logic_dimension_only_no_match():
    """AND 逻辑：condition=None 的规则（仅维度条件）暂未新增时，无关键词命中的问题应回退原 type"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # 此时还未新增维度规则（Task 4 才加），无任何规则命中 → 回退 base_type
    final_type, status = apply_exclusive_rules("普通问题没有关键词", 2, {"scale": "地块", "data_type": "处方用量"})
    assert (final_type, status) == (2, "normal")


def test_apply_exclusive_rules_no_context_backward_compat():
    """context=None 时行为与 v1 完全一致：仅关键词规则生效"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    # context=None：v1 关键词规则仍触发
    final_type, status = apply_exclusive_rules("耕地质量现状评价如何", 5, None)
    assert (final_type, status) == (1, "normal")
    # context=None：无关键词命中 → 回退
    final_type, status = apply_exclusive_rules("普通问题", 2, None)
    assert (final_type, status) == (2, "normal")


def test_dim_rule_model5_plot_grade_eval():
    """维度规则：地块级质量等级评价 → model-5"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    ctx = {"scale": "地块", "data_type": "评价结果", "business_task": "质量等级评价", "expected_output": "评价结果"}
    final_type, status = apply_exclusive_rules("我的田耕地质量等级评价结果", 1, ctx)
    assert (final_type, status) == (5, "normal"), f"地块级质量等级评价应路由 model-5，实际 ({final_type}, {status})"


def test_dim_rule_model1_plot_diagnosis():
    """维度规则：地块级障碍诊断 → model-1"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    ctx = {"scale": "地块", "data_type": "指标数据", "business_task": "障碍诊断", "expected_output": "诊断报告"}
    final_type, status = apply_exclusive_rules("我这块地到底有啥毛病", 5, ctx)
    assert (final_type, status) == (1, "normal"), f"地块级障碍诊断应路由 model-1，实际 ({final_type}, {status})"


def test_dim_rule_model2_acidification_dosage():
    """维度规则：酸化调理剂用量 → model-2"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    ctx = {"scale": "地块", "data_type": "处方用量", "business_task": "酸化改良", "expected_output": "处方用量"}
    final_type, status = apply_exclusive_rules("酸化调理剂每亩施用量多少", 3, ctx)
    assert (final_type, status) == (2, "normal"), f"酸化调理剂用量应路由 model-2，实际 ({final_type}, {status})"


def test_dim_rule_model3_organic_dosage():
    """维度规则：有机肥施用量 → model-3"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    ctx = {"scale": "地块", "data_type": "处方用量", "business_task": "有机质培肥", "expected_output": "处方用量"}
    final_type, status = apply_exclusive_rules("有机肥每亩施用量多少", 2, ctx)
    assert (final_type, status) == (3, "normal"), f"有机肥施用量应路由 model-3，实际 ({final_type}, {status})"


def test_dim_rules_do_not_affect_wrong_scale():
    """维度规则：scale 不匹配时不应触发（如省/县级质量等级评价不命中地块级 model-5 规则）"""
    from framework.agents.exclusive_rules import apply_exclusive_rules
    ctx = {"scale": "省", "data_type": "评价结果", "business_task": "质量等级评价", "expected_output": "评价结果"}
    # base_type=5，无地块级规则命中，回退 5（不误路由到 model-5 维度规则的副作用是保持原 type）
    final_type, status = apply_exclusive_rules("全省耕地质量等级评价结果", 5, ctx)
    assert (final_type, status) == (5, "normal")


if __name__ == "__main__":
    test_rule_status_refers_to_model1()
    test_rule_acidification_refers_to_model2()
    test_rule_stability_refers_to_model4()
    test_rule_grade_refers_to_model5()
    test_conflicting_rules_return_boundary_pending()
    test_type0_untouched()
    test_model_id_to_question_type_mapping()
    test_route_models_boundary_pending()
    test_aggregate_results_passthrough_boundary_pending()
    test_identify_question_node_writes_routing_status()
    print("\n全部排他规则测试通过！")
