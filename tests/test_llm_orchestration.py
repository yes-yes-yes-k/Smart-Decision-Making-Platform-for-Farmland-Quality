"""验证多智能体路线只在编排末尾调用一次 LLM。"""
from typing import Any, Dict

from framework.agents.base import BaseAgent
from framework.agents import nodes


class _TestAgent(BaseAgent):
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return {}


def test_agent_rag_generation_is_disabled_by_default():
    agent = _TestAgent("test", "测试", "test", "test")
    agent._retrieve_knowledge = lambda _: (_ for _ in ()).throw(AssertionError("不应检索"))
    agent._get_llm_service = lambda: (_ for _ in ()).throw(AssertionError("不应调用 LLM"))

    result = agent._generate_with_rag("测试问题")

    assert result["success"] is False
    assert result["skipped"] is True


def test_all_model_question_types_use_final_llm_summary(monkeypatch):
    calls = []

    class FakeLLM:
        def is_available(self):
            return True

        def generate(self, prompt):
            calls.append(prompt)
            return {"success": True, "content": "统一润色结果"}

    monkeypatch.setattr(nodes, "LLM_AVAILABLE", True)
    monkeypatch.setattr(nodes, "llm_service", FakeLLM(), raising=False)
    state = {
        "request": {"question": "我的田怎么改良？"},
        "question_type": 5,
        "model_results": {"status": "ok", "data": {"summary": "规则结果"}},
        "llm_response": {},
    }

    result = nodes.llm_generate(state)

    assert result["llm_response"]["success"] is True
    assert result["llm_response"]["content"] == "统一润色结果"
    assert len(calls) == 1


def test_failed_llm_does_not_override_agent_summary():
    state = {
        "request": {"question": "我的田怎么改良？"},
        "question_type": 5,
        "relevance": 0.8,
        "model_results": {"data": {"summary": "专业模型汇总", "details": {}}},
        "llm_response": {"success": False, "content": "不应覆盖专业结果"},
        "rag_response": {},
    }

    result = nodes.aggregate_results(state)

    assert result["status"] == "completed"
    assert result["model_results"]["answer"] == "专业模型汇总"
