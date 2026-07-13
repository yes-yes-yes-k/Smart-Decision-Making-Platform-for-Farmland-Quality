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


def test_chat_api_returns_structured_multi_agent_result():
    """通过 Flask test client 验证 /api/v1/chat/ 返回多智能体结构化结果"""
    from framework.api.app import create_app

    app = create_app()
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
            json={"message": "我的田施氮肥施多少？"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "ok"
    data = payload["data"]
    # 多智能体结构化字段
    assert data.get("role") == "farmer"
    assert data.get("agents_invoked") == ["model-4", "model-5", "model-6"]
    assert isinstance(data.get("recommendations"), list)
    assert "answer" in data

    print("✓ /api/v1/chat/ 返回多智能体结构化结果")


def test_e2e_province_role_routing():
    """省市管理端问题应路由到 model-1 + model-3"""
    state = _make_state("全省耕地质量整体稳定吗？哪些县区有退化风险？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["role"] == "province"
    assert data["agents_invoked"] == ["model-1", "model-3"]
    # model-3 依赖 model-2，但 model-2 不在 invoked 集合内 —— 应安全跳过
    for aid in ["model-1", "model-3"]:
        assert aid in data["details"]
        assert data["details"][aid]["simulated"] is True
    print("✓ 省市管理端路由正确（model-1 + model-3）")


def test_e2e_county_role_routing():
    """县域执行端问题应路由到 model-1 + model-3 + model-2，model-3 排在 model-2 之后"""
    state = _make_state("本县乡镇任务如何分配？县域耕地质量如何？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["role"] == "county"
    assert set(data["agents_invoked"]) == {"model-1", "model-2", "model-3"}
    # model-2 应在 model-3 之前（拓扑序）
    assert data["agents_invoked"].index("model-2") < data["agents_invoked"].index("model-3")
    print("✓ 县域执行端路由正确（model-1 + model-2 + model-3，拓扑序正确）")


def test_e2e_farmer_role_routing():
    """农户种植端问题应路由到 model-4 + model-5 + model-6，model-6 排在最后"""
    state = _make_state("我的田施氮肥施多少？这块地质量怎么样？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["role"] == "farmer"
    assert data["agents_invoked"] == ["model-4", "model-5", "model-6"]
    # model-6 应排在最后
    assert data["agents_invoked"][-1] == "model-6"
    # model-6 应消费了 model-4 与 model-5 的结果
    m6_evidence = str(data["details"]["model-6"]["evidence"])
    assert "model-4" in m6_evidence or "model-5" in m6_evidence or "石灰" in m6_evidence or "有机肥" in m6_evidence
    print("✓ 农户种植端路由正确（model-4 + model-5 + model-6，依赖传递正确）")


def test_e2e_recommendations_aggregated():
    """汇总的 recommendations 应来自各智能体 evidence 中的 recommendation/source"""
    state = _make_state("我的田怎么改良？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert isinstance(data["recommendations"], list)
    # 至少应包含一条建议（来自 model-4 或 model-5 或 model-6）
    assert len(data["recommendations"]) >= 1
    print("✓ recommendations 字段已聚合各智能体建议")


if __name__ == "__main__":
    test_execute_models_invokes_agent_manager_farmer()
    test_execute_models_invokes_agent_manager_province()
    test_execute_models_writes_structured_result()
    test_chat_api_returns_structured_multi_agent_result()
    test_e2e_province_role_routing()
    test_e2e_county_role_routing()
    test_e2e_farmer_role_routing()
    test_e2e_recommendations_aggregated()
    print("\n所有端到端验证与集成测试通过！")
