"""测试 AgentManager 与 LangGraph 节点集成"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.state import MultiAgentState
from framework.agents.nodes import execute_models


def _make_state(question: str, question_type: int = 1) -> MultiAgentState:
    return {
        "request": {"question": question, "area_code": "lechang"},
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": question_type,
        "relevance": 0.8,
    }


def test_execute_models_invokes_agent_manager_farmer():
    """execute_models 应通过 AgentManager 路由到 farmer 智能体组合"""
    state = _make_state("我的田施氮肥施多少？")
    result = execute_models(state)
    assert result["status"] == "model_completed"
    mr = result["model_results"]
    assert mr.get("status") == "ok"
    data = mr.get("data", {})
    assert data.get("role") == "farmer"
    assert data.get("agents_invoked") == ["model-4", "model-5", "model-6"]
    print("✓ execute_models 通过 AgentManager 路由到 farmer")


def test_execute_models_invokes_agent_manager_province():
    state = _make_state("全省耕地酸化程度如何？")
    result = execute_models(state)
    assert result["status"] == "model_completed"
    data = result["model_results"].get("data", {})
    assert data.get("role") == "province"
    assert set(data.get("agents_invoked", [])) == {"model-1", "model-3"}
    print("✓ execute_models 通过 AgentManager 路由到 province")


def test_execute_models_writes_structured_result():
    state = _make_state("我的田质量怎么样？")
    result = execute_models(state)
    data = result["model_results"].get("data", {})
    assert "summary" in data
    assert "details" in data
    assert "recommendations" in data
    # 每个智能体详情应携带 simulated 标记
    for aid, payload in data["details"].items():
        assert payload.get("simulated") is True
    print("✓ execute_models 写入结构化多智能体结果")


if __name__ == "__main__":
    test_execute_models_invokes_agent_manager_farmer()
    test_execute_models_invokes_agent_manager_province()
    test_execute_models_writes_structured_result()
    print("\n所有 LangGraph 集成测试通过！")
