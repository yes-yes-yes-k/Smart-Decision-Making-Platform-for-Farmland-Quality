"""测试 QuestionTypeRouter 基于 question_type 的 1:1 路由"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.router import QuestionTypeRouter, TYPE_AGENTS
from framework.agents.capabilities import (
    CAPABILITY_BY_AGENT_ID,
    get_capability_by_model_id,
)


def test_type_agents_mapping_is_one_to_one():
    """type 5/type 6 共享真实模型2，且每类仅路由一个 Agent。"""
    assert TYPE_AGENTS == {
        1: ["model-1"],
        2: ["model-4"],
        3: ["model-3"],
        4: ["model-6"],
        5: ["model-2"],
        6: ["model-2"],
        7: ["model-5"],
    }, f"TYPE_AGENTS 映射不符: {TYPE_AGENTS}"
    # 每个 type 仅映射到单一 agent
    for q_type, agents in TYPE_AGENTS.items():
        assert len(agents) == 1, f"type {q_type} 应仅映射 1 个 agent，实际: {agents}"
    print("✓ TYPE_AGENTS 将 type 5/type 6 路由到同一模型2")


def test_get_agents_for_type_known_types():
    """已知 type 1-7 各返回对应单一 agent ID 列表"""
    router = QuestionTypeRouter()
    assert router.get_agents_for_type(1) == ["model-1"]
    assert router.get_agents_for_type(2) == ["model-4"]
    assert router.get_agents_for_type(3) == ["model-3"]
    assert router.get_agents_for_type(4) == ["model-6"]
    assert router.get_agents_for_type(5) == ["model-2"]
    assert router.get_agents_for_type(6) == ["model-2"]
    assert router.get_agents_for_type(7) == ["model-5"]
    print("✓ get_agents_for_type 对 type 1-7 返回正确映射")


def test_capability_catalog_has_six_models_and_no_model7_alias():
    """正式能力目录只保留六个模型，旧模型7标识不再解析。"""
    assert set(CAPABILITY_BY_AGENT_ID) == {
        "model-1", "model-2", "model-3", "model-4", "model-5", "model-6",
    }
    assert get_capability_by_model_id("quality-grade-evaluation") is None


def test_get_agents_for_type_returns_copy():
    """返回的列表应是副本，修改不影响 TYPE_AGENTS"""
    router = QuestionTypeRouter()
    result = router.get_agents_for_type(1)
    result.append("model-999")
    assert "model-999" not in TYPE_AGENTS[1], "修改返回值污染了 TYPE_AGENTS"
    print("✓ get_agents_for_type 返回列表副本")


def test_get_agents_for_type_unknown_returns_empty():
    """未知 type（0、8、-1、None）返回空列表"""
    router = QuestionTypeRouter()
    assert router.get_agents_for_type(0) == []
    assert router.get_agents_for_type(8) == []
    assert router.get_agents_for_type(-1) == []
    assert router.get_agents_for_type(None) == []
    print("✓ 未知 type 返回空列表")


def test_role_router_removed():
    """RoleRouter 类已移除"""
    import framework.agents.router as router_mod
    assert not hasattr(router_mod, "RoleRouter"), "RoleRouter 仍存在，应已删除"
    print("✓ RoleRouter 已移除")


if __name__ == "__main__":
    test_type_agents_mapping_is_one_to_one()
    test_get_agents_for_type_known_types()
    test_capability_catalog_has_six_models_and_no_model7_alias()
    test_get_agents_for_type_returns_copy()
    test_get_agents_for_type_unknown_returns_empty()
    test_role_router_removed()
    print("\n所有 QuestionTypeRouter 测试通过！")
