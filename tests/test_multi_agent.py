"""测试多智能体并发工作流"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.state import MultiAgentState
from framework.agents.nodes import (
    initialize_state,
    identify_question_node,
    route_models,
    rag_chat_node,
    execute_models,
    aggregate_results,
    check_relevance,
    identify_question_type,
)

def test_state_initialization():
    """测试状态初始化"""
    initial_state: MultiAgentState = {
        "request": {"question": "测试问题"},
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "pending",
        "error": None,
        "question_type": None,
        "relevance": None,
    }
    result = initialize_state(initial_state)
    assert result["status"] == "running"
    assert result["rag_response"] == {}
    assert result["conversation_history"] == []
    print("✓ 状态初始化成功")

def test_question_type_identification(monkeypatch):
    """测试问题类型识别"""
    from framework.config import Config
    monkeypatch.setattr(Config, "ROUTING_MODE", "keyword")
    # 测试通用问题
    q_type, relevance = identify_question_type("今天天气怎么样？")
    print(f"  通用问题: type={q_type}, relevance={relevance:.2f}")

    # 测试酸化评估问题
    q_type, relevance = identify_question_type("全省耕地酸化程度如何？")
    print(f"  酸化评估: type={q_type}, relevance={relevance:.2f}")

    # 测试治理方案问题
    q_type, relevance = identify_question_type("如何治理强酸性耕地？")
    print(f"  治理方案: type={q_type}, relevance={relevance:.2f}")

    print("✓ 问题类型识别成功")

def test_route_models():
    """测试路由函数"""
    # type=0 应路由到 rag_chat
    state_type0 = {"question_type": 0}
    assert route_models(state_type0) == "rag_chat"

    # type=1 应路由到 execute_models
    state_type1 = {"question_type": 1}
    assert route_models(state_type1) == "execute_models"

    print("✓ 路由函数正确")

def test_rag_chat_node(monkeypatch):
    """测试 RAG 节点"""
    from framework.agents import nodes
    monkeypatch.setattr(
        nodes.rag_chain, "chat",
        lambda *args, **kwargs: {"success": True, "answer": "本地测试答案", "sources": []},
    )
    state: MultiAgentState = {
        "request": {"question": "什么是土壤酸化？"},
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": 0,
        "relevance": 0.5,
    }
    result = rag_chat_node(state)
    assert "rag_response" in result
    assert result["rag_response"] is not None
    print("✓ RAG 节点执行成功")

def test_aggregate_results_rag():
    """测试 RAG 结果聚合"""
    state: MultiAgentState = {
        "request": {"question": "测试问题"},
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {"answer": "测试答案", "sources": [{"doc_name": "test.pdf"}]},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": 0,
        "relevance": 0.8,
    }
    result = aggregate_results(state)
    assert result["status"] == "completed"
    assert result["model_results"]["answer"] == "测试答案"
    assert len(result["model_results"]["sources"]) == 1
    print("✓ RAG 结果聚合成功")

def test_aggregate_results_model():
    """测试专业模型结果聚合"""
    state: MultiAgentState = {
        "request": {"question": "酸化程度如何？"},
        "data": {},
        "model_results": {"acidification_assessment": {"success": True, "result": {}}},
        "llm_response": {"content": "酸化评估结果", "success": True},
        "rag_response": {},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": 3,
        "relevance": 0.9,
    }
    result = aggregate_results(state)
    assert result["status"] == "completed"
    assert result["model_results"]["answer"] == "酸化评估结果"
    print("✓ 专业模型结果聚合成功")

def test_type2_routes_to_model2_end_to_end(monkeypatch):
    """type=2 的问题通过 execute_models 路由后，agents_invoked 仅含 model-2"""
    from framework.agents import nodes
    from framework.agents.manager import agent_manager
    captured = {}

    def fake_process(question, context):
        captured["context"] = context
        # 真实调用以验证路由
        real = agent_manager.__class__.process(agent_manager, question, context)
        captured["real_result"] = real
        return real

    real_process = agent_manager.process
    monkeypatch.setattr(nodes, "_execute_via_function_calling", lambda *args, **kwargs: None)
    agent_manager.process = fake_process
    try:
        state: MultiAgentState = {
            "request": {"question": "我的田耕地质量等级是多少"},
            "data": {},
            "model_results": {},
            "llm_response": {},
            "rag_response": {},
            "conversation_history": [],
            "status": "running",
            "error": None,
            "question_type": 2,
            "relevance": 0.9,
            "analysis_context": {
                "mode": "spatial", "version": 1,
                "object": {"type": "parcel", "id": "P001", "area_code": "440281"},
            },
            "validated_identifiers": {"parcel_id": "P001", "parcel_code": "A0001"},
        }
        execute_models(state)
    finally:
        agent_manager.process = real_process

    # question_type 应已透传到 context
    assert captured["context"].get("question_type") == 2
    # agents_invoked 应仅含 model-2
    agents_invoked = captured["real_result"]["data"]["agents_invoked"]
    assert agents_invoked == ["model-2"], f"type 2 应仅调 model-2: {agents_invoked}"
    print("✓ type=2 端到端路由到 model-2")


if __name__ == "__main__":
    test_state_initialization()
    test_question_type_identification()
    test_route_models()
    test_rag_chat_node()
    test_aggregate_results_rag()
    test_aggregate_results_model()
    test_type2_routes_to_model2_end_to_end()
    print("\n所有多智能体并发工作流测试通过！")
