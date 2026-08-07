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
    # v1 规则应至少 4 条
    assert len(EXCLUSIVE_RULES) >= 4
    for rule in EXCLUSIVE_RULES:
        # 现有规则 condition 必为字符串（非 None）
        assert isinstance(rule.condition, str), f"{rule} 的 condition 应为字符串"
        # 现有规则 dimension_conditions 必为空 dict
        assert rule.dimension_conditions == {}, f"{rule} 的 dimension_conditions 应为空"


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
