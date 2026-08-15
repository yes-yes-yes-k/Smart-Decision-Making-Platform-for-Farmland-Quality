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


def test_identify_question_node_writes_trace_id(monkeypatch):
    """identify_question_node 应生成 trace_id 写入 state，且与观测日志一致。"""
    import tempfile
    import os
    import json
    from framework.agents import routing as _routing
    from framework.agents.nodes import identify_question_node
    from framework.observability.routing_log import set_log_path

    real = _routing.EMBEDDING_AVAILABLE
    try:
        _routing.EMBEDDING_AVAILABLE = False  # 确定性关键词路径
        with tempfile.TemporaryDirectory() as tmp:
            set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
            state = {"request": {"question": "我的田耕地质量等级是多少"}}
            result = identify_question_node(state)
            assert result["trace_id"]
            assert len(result["trace_id"]) == 32
            with open(os.path.join(tmp, "routing_calls_test.jsonl"), encoding="utf-8") as f:
                entry = json.loads(f.readline())
            assert entry["trace_id"] == result["trace_id"]
    finally:
        _routing.EMBEDDING_AVAILABLE = real


def test_orchestrator_run_attaches_trace_id():
    """orchestrator.run 返回的 dict 应附加 state 中的 trace_id。"""
    from framework.agents.orchestrator import MultiAgentOrchestrator

    class FakeApp:
        def invoke(self, initial_state):
            return {
                "status": "completed",
                "model_results": {"status": "ok", "answer": "ok", "question_type": 2, "sources": []},
                "trace_id": "tid-1",
            }

    orch = MultiAgentOrchestrator()
    orch._app = FakeApp()  # 绕过真实图编译
    result = orch.run({"question": "q"})
    assert result["trace_id"] == "tid-1"
    assert result["answer"] == "ok"


def test_chat_response_contains_trace_id():
    """POST /api/v1/chat/ → response data 含 trace_id（取自 orchestrator.run 结果）。"""
    from framework.api.app import create_app
    from framework.agents.orchestrator import multi_agent_orchestrator

    app = create_app("sqlite")
    app.config["TESTING"] = True

    with app.app_context():
        from framework.models.user import db, User
        db.create_all()
        user = User.query.filter_by(username="tester").first()
        if not user:
            user = User(username="tester", password="x")
            db.session.add(user)
            db.session.commit()
        user_id = user.id
        from flask_jwt_extended import create_access_token
        access_token = create_access_token(identity=str(user_id))

    def fake_run(req, conversation_history=None):
        return {
            "answer": "ok",
            "question_type": 2,
            "model_results": {"data": {"question_type": 2, "agents_invoked": [], "summary": "", "details": {}, "recommendations": []}},
            "trace_id": "chat-trace-1",
        }

    real_run = multi_agent_orchestrator.run
    multi_agent_orchestrator.run = fake_run
    client = app.test_client()
    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "我的田耕地质量等级是多少"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        multi_agent_orchestrator.run = real_run

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["trace_id"] == "chat-trace-1"


def test_chat_stream_done_contains_trace_id():
    """POST /api/v1/chat/stream → done 事件 data 含 trace_id。"""
    from framework.api.app import create_app
    from framework.agents.orchestrator import multi_agent_orchestrator

    app = create_app("sqlite")
    app.config["TESTING"] = True

    with app.app_context():
        from framework.models.user import db, User
        db.create_all()
        user = User.query.filter_by(username="tester").first()
        if not user:
            user = User(username="tester", password="x")
            db.session.add(user)
            db.session.commit()
        user_id = user.id
        from flask_jwt_extended import create_access_token
        access_token = create_access_token(identity=str(user_id))

    def fake_run_stream(req, conversation_history=None):
        yield {
            "type": "done",
            "data": {
                "answer": "ok",
                "sources": [],
                "model_results": {},
                "question_type": 2,
                "question": "q",
                "trace_id": "stream-trace-1",
            },
        }

    real_run_stream = multi_agent_orchestrator.run_stream
    multi_agent_orchestrator.run_stream = fake_run_stream
    client = app.test_client()
    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/stream",
                json={"message": "我的田耕地质量等级是多少"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        multi_agent_orchestrator.run_stream = real_run_stream

    assert resp.status_code == 200
    assert "stream-trace-1" in resp.get_data(as_text=True)
