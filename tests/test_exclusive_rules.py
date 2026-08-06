"""排他规则与「模型边界待确认」降级测试。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _apply(q, base_type, ctx=None):
    from framework.agents.exclusive_rules import apply_exclusive_rules
    return apply_exclusive_rules(q, base_type, ctx)


def test_rule_status_refers_to_model():
    """现状评价 → model-3：候选为 model-7 时修正到 model-3(5→3)"""
    final_type, status = _apply("耕地质量现状评价如何", 5, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 3, f"现状评价应路由到 model-3(type 3)，实际 type {final_type}"


def test_rule_potential_refers_to_model2():
    """潜力 → model-2：候选为 model-7 时修正到 model-2(5→6)"""
    final_type, status = _apply("耕地质量提升潜力多大", 5, {"scale": "县"})
    assert status == "normal"
    assert final_type == 6, f"潜力应路由到 model-2(type 6)，实际 type {final_type}"


def test_rule_organic_input_refers_to_model6():
    """有机质投入量 → model-6(4)"""
    final_type, status = _apply("有机肥每亩施用量多少", 7, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 4, f"有机质投入量应路由到 model-6(type 4)，实际 type {final_type}"


def test_rule_acidification_refers_to_model4():
    """酸化调理剂 → model-4(2)"""
    final_type, status = _apply("我要施加多少酸化调理剂", 4, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 2, f"酸化调理剂应路由到 model-4(type 2)，实际 type {final_type}"


def test_rule_stability_refers_to_model1():
    """稳定性风险 → model-1(1)"""
    final_type, status = _apply("这块地稳定性退化风险如何", 3, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 1, f"稳定性风险应路由到 model-1(type 1)，实际 type {final_type}"


def test_rule_grade_refers_to_model7():
    """质量等级评价 → model-7(5)"""
    final_type, status = _apply("耕地质量等级评价结果", 3, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 5, f"质量等级评价应路由到 model-7(type 5)，实际 type {final_type}"


def test_conflicting_rules_return_boundary_pending():
    """同一易混淆对内两条规则同时命中 → 边界待确认"""
    final_type, status = _apply("酸化调理剂每亩施用量多少", 2, {"scale": "地块"})
    assert status == "boundary_pending", f"冲突应降级 boundary_pending，实际 {status}"


def test_type0_untouched():
    """TYPE_0(RAG) 不应用排他规则"""
    final_type, status = _apply("什么是土壤酸化", 0, {"scale": "地块"})
    assert (final_type, status) == (0, "normal")


def test_model_id_to_question_type_mapping():
    from framework.agents.exclusive_rules import model_id_to_question_type
    assert model_id_to_question_type("model-3") == 3
    assert model_id_to_question_type("model-7") == 5
    assert model_id_to_question_type("model-2") == 6
    assert model_id_to_question_type("model-6") == 4
    assert model_id_to_question_type("model-4") == 2
    assert model_id_to_question_type("model-1") == 1


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
        "request": {"question": "酸化调理剂每亩施用量多少"},
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": 2,
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


if __name__ == "__main__":
    test_rule_status_refers_to_model()
    test_rule_potential_refers_to_model2()
    test_rule_organic_input_refers_to_model6()
    test_rule_acidification_refers_to_model4()
    test_rule_stability_refers_to_model1()
    test_rule_grade_refers_to_model7()
    test_conflicting_rules_return_boundary_pending()
    test_type0_untouched()
    test_model_id_to_question_type_mapping()
    test_route_models_boundary_pending()
    test_aggregate_results_passthrough_boundary_pending()
    test_identify_question_node_writes_routing_status()
    print("\n全部排他规则测试通过！")