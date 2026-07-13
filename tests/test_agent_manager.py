"""测试 AgentManager 中心化编排器"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.manager import AgentManager


def test_manager_register_six_agents():
    """Manager 注册 6 个智能体"""
    mgr = AgentManager()
    assert set(mgr.agents.keys()) == {
        "model-1", "model-2", "model-3",
        "model-4", "model-5", "model-6",
    }
    print("✓ AgentManager 注册 6 个智能体")


def test_manager_topological_sort_province():
    """province 角色 [model-1, model-3]，model-3 依赖 model-2 但 model-2 不在集合内，
    因此仅按现有依赖排序，输出顺序保留两个智能体。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-1", "model-3"])
    assert set(ordered) == {"model-1", "model-3"}
    print("✓ 拓扑排序处理部分依赖（依赖不在集合内时安全跳过）")


def test_manager_topological_sort_farmer():
    """farmer 角色 [model-4, model-5, model-6]，model-6 依赖 model-4 和 model-5，
    因此 model-6 应排在最后。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])
    assert ordered[-1] == "model-6"
    assert set(ordered) == {"model-4", "model-5", "model-6"}
    print("✓ 拓扑排序将依赖项放在被依赖项之后")


def test_manager_process_farmer_returns_structured_result():
    """process 返回符合 API 规范的结构化字典"""
    mgr = AgentManager()
    result = mgr.process("我的田施氮肥施多少", {"area_code": "lechang"})
    assert result["status"] == "ok"
    data = result["data"]
    assert data["role"] == "farmer"
    assert data["agents_invoked"] == ["model-4", "model-5", "model-6"]
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


if __name__ == "__main__":
    test_manager_register_six_agents()
    test_manager_topological_sort_province()
    test_manager_topological_sort_farmer()
    test_manager_process_farmer_returns_structured_result()
    test_manager_process_unknown_question_defaults_farmer()
    print("\n所有 AgentManager 测试通过！")
