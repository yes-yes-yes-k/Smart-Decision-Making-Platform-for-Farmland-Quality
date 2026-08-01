"""测试 AgentManager 中心化编排器"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.manager import AgentManager


def test_manager_register_seven_agents():
    """Manager 注册 7 个智能体（含 model-7 耕地质量等级评价）"""
    mgr = AgentManager()
    assert set(mgr.agents.keys()) == {
        "model-1", "model-2", "model-3",
        "model-4", "model-5", "model-6",
        "model-7",
    }
    print("✓ AgentManager 注册 7 个智能体")


def test_manager_topological_sort_province():
    """province 角色 [model-1, model-3]，model-3 依赖 model-2 但 model-2 不在集合内，
    因此仅按现有依赖排序，输出顺序保留两个智能体。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-1", "model-3"])
    assert set(ordered) == {"model-1", "model-3"}
    print("✓ 拓扑排序处理部分依赖（依赖不在集合内时安全跳过）")


def test_manager_topological_sort_farmer():
    """farmer 角色 [model-4, model-5, model-6, model-7]，model-6/model-7 依赖为空，
    四个 agent 均无互相依赖，拓扑排序包含全部四个。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])
    assert set(ordered) == {"model-4", "model-5", "model-6"}
    print("✓ 拓扑排序包含 farmer 角色全部三个智能体")


def test_manager_process_type4_returns_structured_result():
    """process 返回符合 API 规范的结构化字典（type 4 → model-6）"""
    mgr = AgentManager()
    result = mgr.process("我的田施肥施多少", {"question_type": 4, "area_code": "lechang"})
    assert result["status"] == "ok"
    data = result["data"]
    assert data["question_type"] == 4
    assert data["agents_invoked"] == ["model-6"]
    assert "summary" in data and isinstance(data["summary"], str)
    assert "details" in data and isinstance(data["details"], dict)
    assert "recommendations" in data and isinstance(data["recommendations"], list)
    # details 中每个智能体结果应包含 simulated 标记
    for agent_id, payload in data["details"].items():
        assert payload.get("simulated") is True
    print("✓ AgentManager.process 返回符合规范的结构化结果")


def test_manager_process_no_question_type_returns_no_routing():
    """无 question_type 的问题返回 no_routing（不再默认 farmer）"""
    mgr = AgentManager()
    result = mgr.process("你好", {})
    assert result["status"] == "no_routing"
    assert result["data"]["agents_invoked"] == []
    print("✓ 无 question_type 返回 no_routing")


def test_model6_dependencies_empty():
    """model-6 dependencies=[]，不依赖 model-4/5"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    assert mgr.agents["model-6"].dependencies == []
    print("✓ model-6 依赖为空")


def test_topological_sort_model6_no_dep():
    """model-6 dependencies=[]，拓扑排序不强制 model-6 在最后"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-6", "model-4", "model-5"])
    assert set(ordered) == {"model-4", "model-5", "model-6"}
    # model-6 不再依赖 model-4/5，不强制排最后
    assert ordered[-1] != "model-6" or len(ordered) == 1
    print("✓ model-6 在拓扑排序中无依赖约束")


def test_manager_loads_fertility_ml_agent():
    """_load_real_agents 加载 FertilityMLAgent"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    agent = mgr.agents["model-6"]
    assert agent.__class__.__name__ == "FertilityMLAgent"
    print("✓ AgentManager 加载 FertilityMLAgent")


def test_type5_routes_to_model7():
    """type=5 应路由到 model-7（1:1 映射）"""
    from framework.agents.router import QuestionTypeRouter
    router = QuestionTypeRouter()
    agents = router.get_agents_for_type(5)
    assert agents == ["model-7"], f"type 5 应仅映射 model-7: {agents}"
    print("✓ type 5 路由到 model-7（1:1 映射）")


def test_model7_executed_for_type5_question():
    """type=5 问题 → details['model-7'] 被执行（不 skipped）"""
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少？", {"question_type": 5, "parcel_code": "A0001"})
    details = result["data"]["details"]
    m7 = details.get("model-7", {})
    assert m7.get("status") != "skipped", f"model-7 不应被跳过，实际: {m7}"
    # parcel_code 已传，model-7 应调 fortran exe（若部署就绪）或走 mock 回退
    assert "answer" in m7 or "simulated" in m7
    print("✓ type=5 质量等级问题 model-7 被执行")


def test_process_type1_routes_to_model1_only():
    """type=1 → 仅调 model-1，不调 model-2/3"""
    mgr = AgentManager()
    result = mgr.process("查询区域内耕地质量等级整体稳定吗", {"question_type": 1})
    assert result["status"] == "ok"
    assert result["data"]["agents_invoked"] == ["model-1"]
    assert result["data"]["question_type"] == 1
    print("✓ type=1 路由到 model-1")


def test_process_type2_routes_to_model4_only():
    """type=2 → 仅调 model-4"""
    mgr = AgentManager()
    result = mgr.process("我的田酸化严重吗", {"question_type": 2})
    assert result["data"]["agents_invoked"] == ["model-4"]
    assert result["data"]["question_type"] == 2
    print("✓ type=2 路由到 model-4")


def test_process_type3_routes_to_model3_only():
    """type=3 → 仅调 model-3，不调 model-2"""
    mgr = AgentManager()
    result = mgr.process("我这块地到底有啥毛病", {"question_type": 3})
    assert result["data"]["agents_invoked"] == ["model-3"]
    assert "model-2" not in result["data"]["agents_invoked"]
    print("✓ type=3 路由到 model-3（不调 model-2）")


def test_process_type4_routes_to_model6_only():
    """type=4 → 仅调 model-6，不调 model-5"""
    mgr = AgentManager()
    result = mgr.process("我的田肥力怎么样", {"question_type": 4})
    assert result["data"]["agents_invoked"] == ["model-6"]
    assert "model-5" not in result["data"]["agents_invoked"]
    assert "model-4" not in result["data"]["agents_invoked"]
    print("✓ type=4 路由到 model-6（不调 model-4/5）")


def test_process_type5_routes_to_model7_only():
    """type=5 → 仅调 model-7，不调 model-4/5/6"""
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少", {"question_type": 5, "parcel_code": "A0001"})
    assert result["data"]["agents_invoked"] == ["model-7"]
    assert "model-4" not in result["data"]["agents_invoked"]
    assert "model-5" not in result["data"]["agents_invoked"]
    assert "model-6" not in result["data"]["agents_invoked"]
    print("✓ type=5 路由到 model-7（不调 model-4/5/6）")


def test_process_type6_routes_to_model2_only():
    """type=6 → 仅调 model-2 提升潜力评估。"""
    mgr = AgentManager()
    result = mgr.process("提升潜力有多大", {"question_type": 6})
    assert result["data"]["agents_invoked"] == ["model-2"]


def test_process_type7_routes_to_model5_only():
    """type=7 → 仅调 model-5 有机质培肥。"""
    mgr = AgentManager()
    result = mgr.process("有机肥每亩施用量多少", {"question_type": 7})
    assert result["data"]["agents_invoked"] == ["model-5"]


def test_process_no_routing_when_question_type_none():
    """question_type=None（context 缺失）→ no_routing 空结果"""
    mgr = AgentManager()
    result = mgr.process("你好", {})
    assert result["status"] == "no_routing"
    assert result["data"]["agents_invoked"] == []
    assert result["data"]["summary"] == "未识别问题类型"
    print("✓ question_type=None 返回 no_routing")


def test_process_no_routing_when_question_type_zero():
    """question_type=0 → no_routing（route_models 保证不进入，此处为防御性）"""
    mgr = AgentManager()
    result = mgr.process("什么是土壤酸化", {"question_type": 0})
    assert result["status"] == "no_routing"
    assert result["data"]["agents_invoked"] == []
    print("✓ question_type=0 返回 no_routing")


def test_process_no_routing_when_question_type_unknown():
    """question_type=8（超出范围）→ no_routing"""
    mgr = AgentManager()
    result = mgr.process("未知问题", {"question_type": 8})
    assert result["status"] == "no_routing"
    assert result["data"]["question_type"] == 8
    print("✓ 未知 question_type 返回 no_routing")


def test_no_skipped_entries_in_details_for_type4():
    """type=4 路由到 model-6，details 中 model-6 不应有 skipped 状态"""
    mgr = AgentManager()
    result = mgr.process("我的田肥力怎么样", {"question_type": 4})
    details = result["data"]["details"]
    m6 = details.get("model-6", {})
    assert m6.get("status") != "skipped", f"model-6 不应被 skipped: {m6}"
    assert m6.get("reason") != "question_not_related"
    print("✓ type=4 details 中 model-6 未被 skipped")


def test_no_skipped_entries_in_details_for_type5():
    """type=5 路由到 model-7，details 中 model-7 不应有 skipped 状态"""
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少", {"question_type": 5, "parcel_code": "A0001"})
    details = result["data"]["details"]
    m7 = details.get("model-7", {})
    assert m7.get("status") != "skipped", f"model-7 不应被 skipped: {m7}"
    print("✓ type=5 details 中 model-7 未被 skipped")


def test_should_execute_agent_method_removed():
    """_should_execute_agent 方法应已删除"""
    mgr = AgentManager()
    assert not hasattr(mgr, "_should_execute_agent"), "_should_execute_agent 仍存在"
    print("✓ _should_execute_agent 已移除")


def test_fertility_keywords_constant_removed():
    """FERTILITY_KEYWORDS 常量应已删除"""
    import framework.agents.manager as mgr_mod
    assert not hasattr(mgr_mod, "FERTILITY_KEYWORDS"), "FERTILITY_KEYWORDS 仍存在"
    print("✓ FERTILITY_KEYWORDS 已移除")


def test_grade_keywords_constant_removed():
    """GRADE_KEYWORDS 常量应已删除"""
    import framework.agents.manager as mgr_mod
    assert not hasattr(mgr_mod, "GRADE_KEYWORDS"), "GRADE_KEYWORDS 仍存在"
    print("✓ GRADE_KEYWORDS 已移除")


if __name__ == "__main__":
    test_manager_register_seven_agents()
    test_manager_topological_sort_province()
    test_manager_topological_sort_farmer()
    test_manager_process_type4_returns_structured_result()
    test_manager_process_no_question_type_returns_no_routing()
    test_model6_dependencies_empty()
    test_topological_sort_model6_no_dep()
    test_manager_loads_fertility_ml_agent()
    test_type5_routes_to_model7()
    test_model7_executed_for_type5_question()
    test_process_type1_routes_to_model1_only()
    test_process_type2_routes_to_model4_only()
    test_process_type3_routes_to_model3_only()
    test_process_type4_routes_to_model6_only()
    test_process_type5_routes_to_model7_only()
    test_process_no_routing_when_question_type_none()
    test_process_no_routing_when_question_type_zero()
    test_process_no_routing_when_question_type_unknown()
    test_no_skipped_entries_in_details_for_type4()
    test_no_skipped_entries_in_details_for_type5()
    test_should_execute_agent_method_removed()
    test_fertility_keywords_constant_removed()
    test_grade_keywords_constant_removed()
    print("\n所有 AgentManager 测试通过！")
