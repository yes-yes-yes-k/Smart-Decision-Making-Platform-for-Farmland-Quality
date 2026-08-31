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
        "request": {"question": question},
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": question_type,
        "relevance": 0.8,
        "analysis_context": {
            "mode": "spatial", "version": 1,
            "object": {
                "type": "parcel", "id": "P001", "display_name": "地块 P001",
                "area_code": "440281", "parent_path": [], "source": "test",
                "validated_at": "2026-08-30T00:00:00+00:00",
            },
        },
        "validated_identifiers": {"parcel_id": "P001", "parcel_code": "A0001"},
        "scenario_inputs": {},
        "calculation_mode": "spatial",
        "trace_id": "integration-trace",
        "user_id": 1,
        "conversation_id": 1,
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
    assert mr["question_type"] == 1
    assert list(mr["models"]) == ["model-1"]
    print("✓ execute_models 通过 AgentManager 路由到 type 1 (model-1 稳定性)")


def test_execute_models_invokes_agent_manager_type4():
    """type=4 酸化改良问题应路由到 model-4（酸化改良）。

    question_type 编号与 routing.py 关键词表语义对齐（直接映射）：
      type=4 → 酸化改良 → model-4 (acidification-remediation)
    """
    state = _make_state("全省耕地酸化程度如何？", question_type=4)
    result = execute_models(state)
    assert result["status"] == "model_completed"
    model_results = result["model_results"]
    assert model_results["question_type"] == 4
    assert list(model_results["models"]) == ["model-4"]
    print("✓ execute_models 通过 AgentManager 路由到 type 4 (model-4 酸化改良)")


def test_execute_models_writes_structured_result():
    state = _make_state("我的田质量怎么样？")
    result = execute_models(state)
    model_results = result["model_results"]
    assert isinstance(model_results["answer"], str)
    assert isinstance(model_results["models"], dict)
    assert isinstance(model_results["recommendations"], list)
    for payload in model_results["models"].values():
        assert set(payload) == {"model_id", "status", "subject", "result", "meta", "issues"}
        assert isinstance(payload["meta"]["simulated"], bool)
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
                  "parcel_id": "UNKNOWN-RAW-ID", "parcel_code": "UNKNOWN-RAW-CODE"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    assert resp.status_code == 422
    payload = resp.get_json()
    assert payload["error"]["code"] in {
        "analysis_object_invalid", "legacy_identifier_ambiguity",
    }


def test_e2e_type1_stability_routing():
    """type=1 稳定性问题应路由到 model-1（稳定性风险评价）。

    question_type 编号与 routing.py 关键词表语义对齐（直接映射）：
      type=1 → 稳定性 → model-1 (stability-risk-evaluation)
    """
    state = _make_state("全省耕地质量整体稳定吗？哪些县区有退化风险？", question_type=1)
    result = execute_models(state)
    model_results = result["model_results"]
    assert model_results["question_type"] == 1
    assert list(model_results["models"]) == ["model-1"]
    assert isinstance(model_results["models"]["model-1"]["meta"]["simulated"], bool)
    print("✓ type=1 稳定性路由正确（model-1）")


def test_e2e_type1_county_stability_routing():
    """type=1 县域稳定性问题也路由到 model-1（1:1 映射）"""
    state = _make_state("本县乡镇任务如何分配？县域耕地质量如何？", question_type=1)
    result = execute_models(state)
    model_results = result["model_results"]
    assert model_results["question_type"] == 1
    assert list(model_results["models"]) == ["model-1"]
    print("✓ type=1 县域稳定性路由正确（model-1，1:1 映射）")


def test_e2e_type4_acidification_routing():
    """type=4 酸化改良问题应路由到 model-4（酸化改良）。

    question_type 编号与 routing.py 关键词表语义对齐（直接映射）：
      type=4 → 酸化改良 → model-4 (acidification-remediation)
    """
    state = _make_state("我的田酸化严重吗？", question_type=4)
    result = execute_models(state)
    model_results = result["model_results"]
    assert model_results["question_type"] == 4
    assert list(model_results["models"]) == ["model-4"]
    assert isinstance(model_results["models"]["model-4"]["meta"]["simulated"], bool)
    print("✓ type=4 酸化改良路由正确（model-4）")


def test_e2e_uses_canonical_result_without_legacy_answer_adapter():
    """AgentManager 只消费规范结果，不再调用旧展示适配器。"""
    from framework.agents.manager import agent_manager

    real_agent = agent_manager.agents["model-4"]

    class _FakeAgent:
        dependencies: list = []
        model_id = "acidification-remediation"
        agent_id = "model-4"

        def analyze(self, payload):
            return {
                "model_id": self.model_id,
                "status": "ok",
                "subject": {"type": "unknown", "id": None},
                "result": {"acidification_level": "轻度"},
                "meta": {"data_source": "test", "simulated": False, "model_version": None},
                "issues": [],
            }

        def answer_from_analysis(self, analysis):
            raise AssertionError("Schema 2.0 不应调用旧 answer_from_analysis")

    try:
        agent_manager.agents["model-4"] = _FakeAgent()
        state = _make_state("我的田酸化严重吗？", question_type=4)
        result = execute_models(state)
        model_results = result["model_results"]
        assert model_results["models"]["model-4"]["result"]["acidification_level"] == "轻度"
        assert model_results["recommendations"] == []
        assert "酸化程度：轻度" in model_results["answer"]
    finally:
        agent_manager.agents["model-4"] = real_agent
    print("✓ AgentManager 仅使用规范模型结果生成回答")


def test_chat_api_passes_top_level_parcel_id_and_code():
    """POST body 含 top-level parcel_id/parcel_code → 透传到 orchestrator request"""
    from framework.api.app import create_app
    from framework.agents.orchestrator import multi_agent_orchestrator

    app = create_app("sqlite")
    app.config["TESTING"] = True

    with app.app_context():
        from framework.models import db, User, ParcelInfo
        db.create_all()
        user = User.query.filter_by(username="tester").first()
        if not user:
            user = User(username="tester", password="x")
            db.session.add(user)
            db.session.commit()
        user_id = user.id
        if not ParcelInfo.query.filter_by(parcel_id="1").first():
            db.session.add(ParcelInfo(parcel_id="1", legacy_parcel_code="A0001", area_code="440281"))
            db.session.commit()
        from flask_jwt_extended import create_access_token
        access_token = create_access_token(identity=str(user_id))

    captured = {}

    def fake_run(req, conversation_history=None):
        captured["request"] = req
        return {
            "answer": "ok",
            "question_type": 5,
            "models": {},
            "recommendations": [],
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
        from framework.models import db, User, ParcelInfo
        db.create_all()
        user = User.query.filter_by(username="tester").first()
        if not user:
            user = User(username="tester", password="x")
            db.session.add(user)
            db.session.commit()
        user_id = user.id
        if not ParcelInfo.query.filter_by(parcel_id="1").first():
            db.session.add(ParcelInfo(parcel_id="1", legacy_parcel_code="A0001", area_code="440281"))
            db.session.commit()
        from flask_jwt_extended import create_access_token
        access_token = create_access_token(identity=str(user_id))

    captured = {}

    def fake_run(req, conversation_history=None):
        captured["request"] = req
        return {
            "answer": "ok",
            "question_type": 5,
            "models": {},
            "recommendations": [],
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
            "models": {},
            "recommendations": [],
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
                "parcel_id": "UNKNOWN-PARCEL",
                "parcel_code": "UNKNOWN-CODE",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
    assert resp.status_code == 422
    payload = resp.get_json()
    assert payload["error"]["code"] in {
        "analysis_object_invalid", "legacy_identifier_ambiguity",
    }


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
    qt = data["routing"]["question_type"]
    assert qt == 0, f"知识性问题「什么是土壤酸化」期望 type 0，实际 type {qt}"
    assert "models" not in data
    assert "agents_invoked" not in data
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
    qt = data["routing"]["question_type"]
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
    test_chat_api_type2_routes_to_model2_only()
    test_chat_api_knowledge_question_routes_to_rag()
    test_chat_api_knowledge_question_概念_pattern()
    print("\n所有端到端验证与集成测试通过！")
