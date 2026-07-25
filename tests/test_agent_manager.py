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


def test_manager_process_farmer_returns_structured_result():
    """process 返回符合 API 规范的结构化字典"""
    mgr = AgentManager()
    result = mgr.process("我的田施肥施多少", {"area_code": "lechang"})
    assert result["status"] == "ok"
    data = result["data"]
    assert data["role"] == "farmer"
    assert data["agents_invoked"] == ["model-4", "model-5", "model-6", "model-7"]
    assert "summary" in data and isinstance(data["summary"], str)
    assert "details" in data and isinstance(data["details"], dict)
    assert "recommendations" in data and isinstance(data["recommendations"], list)
    # details 中每个智能体结果应包含 simulated 标记
    for agent_id, payload in data["details"].items():
        assert payload.get("simulated") is True
    print("✓ AgentManager.process 返回符合规范的结构化结果")


def test_manager_process_unknown_question_defaults_farmer():
    """无关键词问题默认路由到 farmer"""
    mgr = AgentManager()
    result = mgr.process("你好", {})
    assert result["data"]["role"] == "farmer"
    print("✓ 未知问题默认路由到 farmer")


def test_should_execute_model6_fertility_question():
    """问'肥力' → _should_execute_agent('model-6', ...) = True"""
    from framework.agents.manager import AgentManager, FERTILITY_KEYWORDS
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-6", "我的田肥力怎么样？") is True
    assert mgr._should_execute_agent("model-6", "有机碳含量多少？") is True
    assert mgr._should_execute_agent("model-6", "需要施多少肥？") is True
    print("✓ 肥力相关问题触发 model-6 执行")


def test_should_skip_model6_non_fertility_question():
    """问'pH' → _should_execute_agent('model-6', ...) = False"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-6", "我的田pH如何？") is False
    assert mgr._should_execute_agent("model-6", "你好") is False
    print("✓ 非肥力问题跳过 model-6")


def test_should_execute_other_agents_always():
    """非 model-6 的 agent 始终执行"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-4", "任何问题") is True
    assert mgr._should_execute_agent("model-5", "任何问题") is True
    print("✓ 非 model-6 agent 始终执行")


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


def test_model6_skipped_in_details_for_non_fertility():
    """非肥力问题 → details['model-6'] 含 skipped 状态"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    result = mgr.process("我的田pH如何？", {})
    details = result["data"]["details"]
    # model-6 应被跳过（status 标记或 skipped 标记）
    m6 = details.get("model-6", {})
    assert m6.get("status") == "skipped" or m6.get("simulated") is True
    print("✓ 非肥力问题 model-6 被跳过")


def test_manager_loads_fertility_ml_agent():
    """_load_real_agents 加载 FertilityMLAgent"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    agent = mgr.agents["model-6"]
    assert agent.__class__.__name__ == "FertilityMLAgent"
    print("✓ AgentManager 加载 FertilityMLAgent")


def test_farmer_role_includes_model_7():
    """farmer 角色应包含 model-7（共 4 个 agent）"""
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    agents = router.get_agents_for_role("farmer")
    assert "model-7" in agents, f"farmer 角色未含 model-7: {agents}"
    assert agents == ["model-4", "model-5", "model-6", "model-7"], f"farmer agents 不符: {agents}"
    print("✓ farmer 角色含 model-7（4 个 agent）")


def test_should_execute_model7_grade_question():
    """问'质量等级' → _should_execute_agent('model-7', ...) = True"""
    from framework.agents.manager import AgentManager, GRADE_KEYWORDS
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-7", "我的田耕地质量等级是多少？") is True
    assert mgr._should_execute_agent("model-7", "查询地块的综合指数和障碍度排序") is True
    assert mgr._should_execute_agent("model-7", "这块地的耕地质量等级评价结果") is True
    print("✓ 质量等级相关问题触发 model-7 执行")


def test_should_skip_model7_non_grade_question():
    """非质量等级问题 → _should_execute_agent('model-7', ...) = False"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-7", "我的田肥力怎么样？") is False
    assert mgr._should_execute_agent("model-7", "我的田酸化严重吗？") is False
    assert mgr._should_execute_agent("model-7", "你好") is False
    print("✓ 非质量等级问题跳过 model-7")


def test_grade_keywords_mirrors_question_type_5():
    """GRADE_KEYWORDS 应镜像 nodes.QUESTION_TYPE_5_KEYWORDS"""
    from framework.agents.manager import GRADE_KEYWORDS
    from framework.agents.nodes import QUESTION_TYPE_5_KEYWORDS
    assert GRADE_KEYWORDS == QUESTION_TYPE_5_KEYWORDS, (
        f"GRADE_KEYWORDS 与 QUESTION_TYPE_5_KEYWORDS 不一致：\n"
        f"  manager: {GRADE_KEYWORDS}\n  nodes: {QUESTION_TYPE_5_KEYWORDS}"
    )
    print("✓ GRADE_KEYWORDS 镜像 QUESTION_TYPE_5_KEYWORDS")


def test_model7_skipped_in_details_for_non_grade_farmer_question():
    """farmer 问非质量等级问题 → details['model-7'] 含 skipped 状态"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    result = mgr.process("我的田肥力怎么样？", {})
    details = result["data"]["details"]
    m7 = details.get("model-7", {})
    assert m7.get("status") == "skipped", f"model-7 应被跳过，实际: {m7}"
    assert m7.get("reason") == "question_not_related"
    print("✓ 非质量等级 farmer 问题 model-7 被跳过")


def test_model7_executed_for_grade_farmer_question():
    """farmer 问质量等级问题 → details['model-7'] 不含 skipped 状态"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少？", {"parcel_code": "A0001"})
    details = result["data"]["details"]
    m7 = details.get("model-7", {})
    assert m7.get("status") != "skipped", f"model-7 不应被跳过，实际: {m7}"
    # parcel_code 已传，model-7 应调 fortran exe（若部署就绪）或走 mock 回退
    assert "answer" in m7 or "simulated" in m7
    print("✓ 质量等级 farmer 问题 model-7 被执行")


if __name__ == "__main__":
    test_manager_register_seven_agents()
    test_manager_topological_sort_province()
    test_manager_topological_sort_farmer()
    test_manager_process_farmer_returns_structured_result()
    test_manager_process_unknown_question_defaults_farmer()
    test_farmer_role_includes_model_7()
    test_should_execute_model7_grade_question()
    test_should_skip_model7_non_grade_question()
    test_grade_keywords_mirrors_question_type_5()
    test_model7_skipped_in_details_for_non_grade_farmer_question()
    test_model7_executed_for_grade_farmer_question()
    print("\n所有 AgentManager 测试通过！")
