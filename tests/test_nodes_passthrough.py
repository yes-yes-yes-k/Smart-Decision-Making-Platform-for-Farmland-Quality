# tests/test_nodes_passthrough.py
"""Task 5: API 层透传 fertilizer_type —— execute_models 透传测试 + 路由回归。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_execute_models_passes_fertilizer_type(monkeypatch):
    """execute_models 应将顶层 fertilizer_type 注入 context（与 land_type 并列）。"""
    from framework.agents import nodes
    import framework.agents.manager as manager_mod

    captured = {}

    class FakeManager:
        def process(self, question, context):
            captured["context"] = context
            return {"status": "ok", "data": {}}

    # execute_models 内部 `from framework.agents.manager import agent_manager`
    # 因此必须 patch manager 模块上的单例，而非 nodes 模块。
    monkeypatch.setattr(manager_mod, "agent_manager", FakeManager(), raising=False)

    state = {
        "request": {
            "question": "如何改良酸化？",
            "land_type": "paddy",
            "fertilizer_type": "urea",
        },
        "question_type": 4,
        "data": {},
    }
    nodes.execute_models(state)

    assert captured["context"].get("fertilizer_type") == "urea"
    assert captured["context"].get("land_type") == "paddy"


def test_question_type_4_routes_to_model_4():
    """回归：question_type=4 仍路由到 model-4（AcidificationRemediationAgent）。"""
    from framework.agents.router import QuestionTypeRouter

    router = QuestionTypeRouter()
    assert "model-4" in router.get_agents_for_type(4)
