"""测试 QuestionTypeRouter 基于 question_type 的 1:1 路由"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.router import QuestionTypeRouter, TYPE_AGENTS


def test_type_agents_mapping_is_one_to_one():
    """TYPE_AGENTS 必须覆盖 6 项能力（含 model-6 占位），且每类仅路由一个 Agent。

    question_type 编号与 routing.py 关键词表语义对齐（直接映射）：
      type=1 稳定性 → model-1
      type=2 质量等级 → model-2
      type=3 障碍诊断 → model-3
      type=4 酸化改良 → model-4
      type=5 有机质培肥 → model-5
      type=6 占位 → model-6
    """
    assert TYPE_AGENTS == {
        1: ["model-1"],
        2: ["model-2"],
        3: ["model-3"],
        4: ["model-4"],
        5: ["model-5"],
        6: ["model-6"],
    }, f"TYPE_AGENTS 映射不符: {TYPE_AGENTS}"
    # 每个 type 仅映射到单一 agent
    for q_type, agents in TYPE_AGENTS.items():
        assert len(agents) == 1, f"type {q_type} 应仅映射 1 个 agent，实际: {agents}"
    print("✓ TYPE_AGENTS 为 1:1 映射")


def test_get_agents_for_type_known_types():
    """已知 type 1-6 各返回对应单一 agent ID 列表（直接映射）"""
    router = QuestionTypeRouter()
    assert router.get_agents_for_type(1) == ["model-1"]
    assert router.get_agents_for_type(2) == ["model-2"]
    assert router.get_agents_for_type(3) == ["model-3"]
    assert router.get_agents_for_type(4) == ["model-4"]
    assert router.get_agents_for_type(5) == ["model-5"]
    assert router.get_agents_for_type(6) == ["model-6"]
    print("✓ get_agents_for_type 对 type 1-6 返回正确映射")


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


if __name__ == "__main__":
    test_type_agents_mapping_is_one_to_one()
    test_get_agents_for_type_known_types()
    test_get_agents_for_type_returns_copy()
    test_get_agents_for_type_unknown_returns_empty()
    print("\n所有 QuestionTypeRouter 测试通过！")
