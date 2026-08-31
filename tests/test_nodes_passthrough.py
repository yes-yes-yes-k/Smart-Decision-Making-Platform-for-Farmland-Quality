# tests/test_nodes_passthrough.py
"""Task 5: API 层透传 fertilizer_type —— execute_models 透传测试 + 路由回归。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_execute_models_does_not_pass_unvalidated_request_inputs(monkeypatch):
    """空间执行只使用规范上下文，不扫描原始 request 的业务字段。"""
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
        "question_type": 2,
        "data": {},
    }
    nodes.execute_models(state)

    assert "fertilizer_type" not in captured["context"]
    assert "land_type" not in captured["context"]


def test_question_type_4_routes_to_model_4():
    """回归：question_type=4 路由到 model-4（AcidificationRemediationAgent）。

    question_type 编号与 routing.py 关键词表语义对齐（直接映射）：
      type=4 → 酸化改良 → model-4 (acidification-remediation)
    """
    from framework.agents.router import QuestionTypeRouter

    router = QuestionTypeRouter()
    assert "model-4" in router.get_agents_for_type(4)
