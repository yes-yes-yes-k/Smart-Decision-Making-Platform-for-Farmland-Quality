"""测试 AgentManager 与 LangGraph 节点集成"""
import sys
import os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.state import MultiAgentState
from framework.agents.nodes import execute_models


class _UnavailableLLM:
    """防止 API 集成测试访问本机配置的外部模型服务。"""

    def is_available(self):
        return False

    def generate(self, prompt, messages=None, **kwargs):
        return {
            "success": False,
            "content": "AI服务暂时不可用",
            "type": "fallback",
        }


@pytest.fixture(autouse=True)
def disable_external_llm(monkeypatch):
    """集成测试只验证本地路由和降级结构，不依赖外部运行时。"""
    from framework.agents import nodes
    from framework.rag import chain
    from framework.config import Config

    llm = _UnavailableLLM()
    monkeypatch.setattr(nodes, "llm_service", llm)
    monkeypatch.setattr(chain, "llm_service", llm)
    monkeypatch.setattr(chain.rag_chain, "llm_service", llm)
    monkeypatch.setattr(Config, "ROUTING_MODE", "keyword")
    monkeypatch.setattr(
        chain.rag_chain,
        "chat",
        lambda question, conversation_history=None: {
            "success": False,
            "answer": "RAG服务暂时不可用",
            "sources": [],
        },
    )


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


def test_execute_models_invokes_agent_manager_type1():
    """type=1 稳定性问题应路由到 model-1（稳定性风险评价）。

    question_type 编号与 routing.py 关键词表语义对齐（直接映射）：
      type=1 → 稳定性 → model-1 (stability-risk-evaluation)
    """
    state = _make_state("我的田质量等级稳定吗？", question_type=1)
    result = execute_models(state)
    assert result["status"] == "model_completed"
    mr = result["model_results"]
    assert mr.get("status") == "ok"
    data = mr.get("data", {})
    assert data.get("question_type") == 1
    assert data.get("agents_invoked") == ["model-1"]
    print("✓ execute_models 通过 AgentManager 路由到 type 1 (model-1 稳定性)")


def test_execute_models_invokes_agent_manager_type4():
    """type=4 酸化改良问题应路由到 model-4（酸化改良）。

    question_type 编号与 routing.py 关键词表语义对齐（直接映射）：
      type=4 → 酸化改良 → model-4 (acidification-remediation)
    """
    state = _make_state("全省耕地酸化程度如何？", question_type=4)
    result = execute_models(state)
    assert result["status"] == "model_completed"
    data = result["model_results"].get("data", {})
    assert data.get("question_type") == 4
    assert data.get("agents_invoked") == ["model-4"]
    print("✓ execute_models 通过 AgentManager 路由到 type 4 (model-4 酸化改良)")


def test_execute_models_writes_structured_result():
    state = _make_state("我的田质量怎么样？")
    result = execute_models(state)
    data = result["model_results"].get("data", {})
    assert "summary" in data
    assert "details" in data
    assert "recommendations" in data
    # 每个智能体详情应携带 simulated 标记（真实/降级路径下为 False）
    for aid, payload in data["details"].items():
        assert "simulated" in payload
        assert payload.get("simulated") is False
    print("✓ execute_models 写入结构化多智能体结果")


def test_chat_api_raw_legacy_ids_do_not_bypass_central_guard():
    """API 尚未解析的原始旧 ID 不得直接触发专业 Agent。"""
    from framework.api.app import create_app

    app = create_app("sqlite")
    app.config["TESTING"] = True

    with app.app_context():
        from framework.models.user import db, User
        db.create_all()
        # 注册测试用户（若已存在则复用），并签发真实 JWT 以通过装饰器鉴权
        user = User.query.filter_by(username="tester").first()
        if not user:
            user = User(username="tester", password="x")
            db.session.add(user)
            db.session.commit()
        user_id = user.id

        from flask_jwt_extended import create_access_token
        access_token = create_access_token(identity=str(user_id))

    client = app.test_client()
    with app.app_context():
        resp = client.post(
            "/api/v1/chat/",
            json={"message": "我的田耕地质量等级是多少",
                  "parcel_id": "1", "parcel_code": "A0001"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "ok"
    data = payload["data"]
    # Task 9 接入上下文服务前，旧字段仍是未验证输入；中央守卫必须拒绝执行。
    assert "role" not in data, f"响应不应含 role 字段: {data}"
    assert "question_type" in data
    qt = data.get("question_type")
    agents_invoked = data.get("agents_invoked", [])
    assert agents_invoked == []
    assert data["model_results"]["status"] == "needs_analysis_object"
    assert data["model_results"]["data"]["agents_invoked"] == []
    # recommendations 字段仅在非空时写入响应
    assert isinstance(data.get("recommendations", []), list)
    assert "answer" in data

    print(f"✓ /api/v1/chat/ 未验证旧 ID 被中央守卫拦截 (type={qt})")


def test_e2e_type1_stability_routing():
    """type=1 稳定性问题应路由到 model-1（稳定性风险评价）。

    question_type 编号与 routing.py 关键词表语义对齐（直接映射）：
      type=1 → 稳定性 → model-1 (stability-risk-evaluation)
    """
    state = _make_state("全省耕地质量整体稳定吗？哪些县区有退化风险？", question_type=1)
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["question_type"] == 1
    assert data["agents_invoked"] == ["model-1"]
    assert "model-1" in data["details"]
    assert data["details"]["model-1"]["simulated"] is False
    print("✓ type=1 稳定性路由正确（model-1）")


def test_e2e_type1_county_stability_routing():
    """type=1 县域稳定性问题也路由到 model-1（1:1 映射）"""
    state = _make_state("本县乡镇任务如何分配？县域耕地质量如何？", question_type=1)
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["question_type"] == 1
    assert data["agents_invoked"] == ["model-1"]
    print("✓ type=1 县域稳定性路由正确（model-1，1:1 映射）")


def test_e2e_type4_acidification_routing():
    """type=4 酸化改良问题应路由到 model-4（酸化改良）。

    question_type 编号与 routing.py 关键词表语义对齐（直接映射）：
      type=4 → 酸化改良 → model-4 (acidification-remediation)
    """
    state = _make_state("我的田酸化严重吗？", question_type=4)
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["question_type"] == 4
    assert data["agents_invoked"] == ["model-4"]
    assert "model-4" in data["details"]
    assert data["details"]["model-4"]["simulated"] is False
    print("✓ type=4 酸化改良路由正确（model-4）")


def test_e2e_recommendations_aggregated():
    """汇总的 recommendations 应来自智能体 evidence 中的 recommendation/source。

    1:1 路由后，type 4 仅调 model-4（酸化改良），其 evidence 为 metric/value 格式，
    不含 recommendation/source。使用 mock 验证：当 agent evidence 含
    recommendation/source 时，_summarize 能正确聚合并去重；metric/value 不混入。
    """
    from framework.agents.manager import agent_manager

    real_agent = agent_manager.agents["model-4"]

    class _FakeAgent:
        dependencies: list = []

        def analyze(self, payload):
            return {"status": "ok", "result": {}}

        def answer_from_analysis(self, analysis):
            return {
                "answer": "测试回复",
                "evidence": [
                    {"recommendation": "增施有机肥 2 t/亩"},
                    {"source": "农业农村部指南"},
                    {"metric": "soc_prediction", "value": 12.0},  # 不应进入 recommendations
                ],
                "confidence": 0.8,
                "simulated": True,
            }

    try:
        agent_manager.agents["model-4"] = _FakeAgent()
        state = _make_state("我的田酸化严重吗？", question_type=4)
        result = execute_models(state)
        data = result["model_results"]["data"]
        assert isinstance(data["recommendations"], list)
        # 应收集 recommendation 和 source 两条，去重
        assert len(data["recommendations"]) >= 2, f"应至少聚合 2 条建议: {data['recommendations']}"
        assert "增施有机肥 2 t/亩" in data["recommendations"]
        assert "农业农村部指南" in data["recommendations"]
        # metric/value 格式的 evidence 不应出现在 recommendations
        assert "soc_prediction" not in data["recommendations"]
    finally:
        agent_manager.agents["model-4"] = real_agent
    print("✓ recommendations 字段已聚合智能体建议（mock 验证）")


def test_chat_api_passes_top_level_parcel_id_and_code():
    """POST body 含 top-level parcel_id/parcel_code → 透传到 orchestrator request"""
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

    captured = {}

    def fake_run(req, conversation_history=None):
        captured["request"] = req
        return {
            "answer": "ok",
            "question_type": 5,
            "model_results": {
                "data": {
                    "question_type": 5,
                    "agents_invoked": ["model-5"],
                    "summary": "",
                    "details": {},
                    "recommendations": [],
                }
            },
        }

    real_run = multi_agent_orchestrator.run
    multi_agent_orchestrator.run = fake_run
    client = app.test_client()
    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/",
                json={
                    "message": "我的田耕地质量等级是多少",
                    "parcel_id": "1",
                    "parcel_code": "A0001",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        multi_agent_orchestrator.run = real_run

    assert resp.status_code == 200
    req = captured["request"]
    assert req.get("parcel_id") == "1", f"parcel_id 未透传: {req}"
    assert req.get("parcel_code") == "A0001", f"parcel_code 未透传: {req}"
    assert req.get("question") == "我的田耕地质量等级是多少"
    print("✓ /api/v1/chat/ 透传 top-level parcel_id/parcel_code")


def test_chat_api_top_level_parcel_overrides_context():
    """top-level parcel_id 优先于 context.parcel_id"""
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

    captured = {}

    def fake_run(req, conversation_history=None):
        captured["request"] = req
        return {
            "answer": "ok",
            "question_type": 5,
            "model_results": {"data": {"question_type": 5, "agents_invoked": [], "summary": "", "details": {}, "recommendations": []}},
        }

    real_run = multi_agent_orchestrator.run
    multi_agent_orchestrator.run = fake_run
    client = app.test_client()
    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/",
                json={
                    "message": "我的田质量等级",
                    "parcel_id": "1",            # top-level 优先
                    "context": {"parcel_id": "999"},  # 应被覆盖
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        multi_agent_orchestrator.run = real_run

    assert resp.status_code == 200
    req = captured["request"]
    assert req.get("parcel_id") == "1", f"top-level 应优先，实际: {req}"
    print("✓ top-level parcel_id 优先于 context.parcel_id")


def test_chat_api_no_parcel_when_absent():
    """POST body 不含 parcel_id/parcel_code → orchestrator request 不含（现有行为不变）"""
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

    captured = {}

    def fake_run(req, conversation_history=None):
        captured["request"] = req
        return {
            "answer": "ok",
            "question_type": 0,
            "model_results": {},
        }

    real_run = multi_agent_orchestrator.run
    multi_agent_orchestrator.run = fake_run
    client = app.test_client()
    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "你好"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        multi_agent_orchestrator.run = real_run

    assert resp.status_code == 200
    req = captured["request"]
    assert "parcel_id" not in req, f"不应含 parcel_id: {req}"
    assert "parcel_code" not in req, f"不应含 parcel_code: {req}"
    print("✓ body 无 parcel 标识符时 orchestrator request 不含")


def test_chat_api_type5_raw_ids_are_blocked_before_model2():
    """未经上下文服务验证的旧 ID 不得在 API 路径触发 model-2。"""
    from framework.api.app import create_app

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

    client = app.test_client()
    with app.app_context():
        resp = client.post(
            "/api/v1/chat/",
            json={
                "message": "我的田耕地质量等级是多少",
                "parcel_id": "1",
                "parcel_code": "A0001",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "ok"
    data = payload["data"]
    # spec 验证：无 role 字段
    assert "role" not in data, f"响应不应含 role 字段: {data}"
    # type 2 路由到 model-2（1:1 直接映射，质量等级）
    qt = data.get("question_type")
    agents_invoked = data.get("agents_invoked", [])
    assert qt == 2, f"质量等级问题期望 type 2，实际 type {qt}"
    assert agents_invoked == []
    assert data["model_results"]["status"] == "needs_analysis_object"
    print(f"✓ Task 6.2: type 2 未验证旧 ID 被拦截 (type={qt}, 无 role)")


def test_chat_api_knowledge_question_routes_to_rag():
    """Task 6.3: 知识性问题「什么是土壤酸化」经 API 路由后 question_type=0（走 RAG）"""
    from framework.api.app import create_app

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

    client = app.test_client()
    with app.app_context():
        resp = client.post(
            "/api/v1/chat/",
            json={"message": "什么是土壤酸化"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "ok"
    data = payload["data"]
    # 知识性问题应返回 type 0（走 RAG），不路由到专业模型
    qt = data.get("question_type")
    assert qt == 0, f"知识性问题「什么是土壤酸化」期望 type 0，实际 type {qt}"
    # type 0 不应有 agents_invoked（走 RAG 而非 execute_models）
    agents_invoked = data.get("agents_invoked", [])
    assert agents_invoked == [] or "agents_invoked" not in data, (
        f"知识性问题不应调用专业模型: {agents_invoked}"
    )
    print(f"✓ Task 6.3: 知识性问题走 RAG (type={qt}, 无专业模型调用)")


def test_chat_api_knowledge_question_概念_pattern():
    """Task 6.3: 「耕地质量等级是什么意思」也应走 RAG（type 0）"""
    from framework.api.app import create_app

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

    client = app.test_client()
    with app.app_context():
        resp = client.post(
            "/api/v1/chat/",
            json={"message": "耕地质量等级是什么意思"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    assert resp.status_code == 200
    payload = resp.get_json()
    data = payload["data"]
    qt = data.get("question_type")
    assert qt == 0, f"知识性问题期望 type 0，实际 type {qt}"
    print(f"✓ Task 6.3: 「耕地质量等级是什么意思」走 RAG (type={qt})")


if __name__ == "__main__":
    test_execute_models_invokes_agent_manager_type4()
    test_execute_models_invokes_agent_manager_type1()
    test_execute_models_writes_structured_result()
    test_chat_api_returns_structured_multi_agent_result()
    test_e2e_type1_stability_routing()
    test_e2e_type1_county_stability_routing()
    test_e2e_type4_stability_routing()
    test_e2e_recommendations_aggregated()
    test_chat_api_passes_top_level_parcel_id_and_code()
    test_chat_api_top_level_parcel_overrides_context()
    test_chat_api_no_parcel_when_absent()
    test_chat_api_type5_routes_to_model5_only()
    test_chat_api_knowledge_question_routes_to_rag()
    test_chat_api_knowledge_question_概念_pattern()
    print("\n所有端到端验证与集成测试通过！")
