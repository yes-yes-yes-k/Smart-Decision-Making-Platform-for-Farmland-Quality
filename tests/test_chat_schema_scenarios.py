"""聊天 Schema 2.0、流式一致性和 Function Calling 公共边界测试。"""

import json
from unittest.mock import MagicMock

import pytest

from framework.agents.output_contract import normalize_execution
from framework.agents.manager import agent_manager
from framework.api.routes.chat import _serialize_chat_response


MODEL_RESULTS = {
    "model-1": ("stability-risk-evaluation", {"region": "440281", "score": 0.82, "grade": "稳定", "modules": {}}),
    "model-2": ("quality-grade-evaluation", {"quality_grade": "3等", "composite_index": 0.76, "indicators": [], "obstacle_degree": []}),
    "model-3": ("obstacle-diagnosis", {"obstacle_type": "酸化", "primary_factors": ["pH"], "secondary_factors": [], "obstacle_degrees": [], "obstacle_levels": [], "obstacle_combination": "pH"}),
    "model-4": ("acidification-remediation", {"acidification_level": "中度", "background_acid": 1.0, "acid_deposition_input": 2.0, "crop_acid_output": 3.0, "nitrogen_cycle_acid": 4.0, "agricultural_acid": 5.0, "soil_conditioner_dosage": 6.0, "woody_peat_dosage": 7.0, "sub_model": "upland"}),
    "model-5": ("organic-matter-improvement", {"soc_prediction": 20.1, "dose_prediction": 9.2, "soc_confidence": 0.91, "dose_confidence": 0.88, "region": "lechang", "land_type": "paddy", "imputed_features": []}),
}


def _envelope(agent_id="model-1"):
    model_id, raw_result = MODEL_RESULTS[agent_id]
    agent = type(
        "ChatScenarioAgent",
        (),
        {"agent_id": agent_id, "model_id": model_id, "capability": {"model_id": model_id}},
    )()
    execution = {
        "status": "ok",
        "result": raw_result,
        "data_source": "precomputed",
    }
    if agent_id == "model-5":
        execution["data_source"] = "shaoguan_rf"
        execution["model_version"] = "SG_RF_test_v1"
    return normalize_execution(
        agent,
        {"parcel_id": "P-1"},
        execution,
    )


def _orchestrator_result(question_type=1, routing_status="normal", answer="模型分析完成"):
    agent_id = f"model-{question_type}"
    models = {} if question_type == 0 else {agent_id: _envelope(agent_id)}
    return {
        "status": "ok",
        "question_type": question_type,
        "routing_status": routing_status,
        "routing": {"question_type": question_type, "status": routing_status},
        "answer": answer,
        "sources": [{"title": "来源"}] if question_type == 0 else [],
        "recommendations": ["持续监测"] if question_type else [],
        "models": models,
        "trace_id": "trace-chat",
    }


def test_manager_fallback_answer_uses_business_name_not_internal_agent_id():
    result = agent_manager._summarize(2, ["model-2"], {"model-2":_envelope("model-2")})
    assert result["answer"].startswith("耕地质量等级评价：")
    assert "model-2" not in result["answer"]


@pytest.fixture()
def chat_client(tmp_path, monkeypatch):
    from flask_jwt_extended import create_access_token
    from framework.api.app import create_app
    from framework.config import SQLiteConfig
    from framework.models.user import User, db

    monkeypatch.setattr(SQLiteConfig, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{(tmp_path / 'chat.db').as_posix()}")
    monkeypatch.setattr(SQLiteConfig, "SQLALCHEMY_ENGINE_OPTIONS", {})
    app = create_app("sqlite")
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        user = User(username="schema20-chat", password="x")
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
    yield app.test_client(), {"Authorization": f"Bearer {token}"}
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _post_chat(client, headers, monkeypatch, result, **payload):
    monkeypatch.setattr(
        "framework.api.routes.chat.multi_agent_orchestrator.run",
        lambda request, conversation_history=None: result,
    )
    return client.post(
        "/api/v1/chat/",
        json={"message": "请分析", **payload},
        headers=headers,
    )


def test_rag_response_omits_models_even_when_explicitly_requested(chat_client, monkeypatch):
    client, headers = chat_client
    response = _post_chat(
        client,
        headers,
        monkeypatch,
        _orchestrator_result(question_type=0, answer="RAG 回答"),
        include_model_results=True,
    )

    data = response.get_json()["data"]
    assert data["answer"] == "RAG 回答"
    assert data["routing"] == {"question_type": 0, "status": "normal"}
    assert "models" not in data


@pytest.mark.parametrize("question_type", [1, 2, 3, 4, 5])
def test_professional_models_omit_details_by_default(chat_client, monkeypatch, question_type):
    client, headers = chat_client
    response = _post_chat(client, headers, monkeypatch, _orchestrator_result(question_type))

    assert response.status_code == 200
    body = response.get_json()
    assert body["schema_version"] == "2.0"
    assert {"message_id", "answer", "sources", "recommendations", "routing"} <= set(body["data"])
    assert "models" not in body["data"]
    assert body["data"]["routing"]["question_type"] == question_type


@pytest.mark.parametrize("question_type", [1, 2, 3, 4, 5])
def test_explicit_professional_models_keep_their_discriminated_schema(chat_client, monkeypatch, question_type):
    client, headers = chat_client
    response = _post_chat(
        client,
        headers,
        monkeypatch,
        _orchestrator_result(question_type),
        include_model_results=True,
    )

    agent_id = f"model-{question_type}"
    model_id, raw_result = MODEL_RESULTS[agent_id]
    model = response.get_json()["data"]["models"][agent_id]
    assert model["model_id"] == model_id
    if agent_id == "model-5":
        assert set(raw_result) <= set(model["result"])
        assert model["result"]["dose"] == raw_result["dose_prediction"]
        assert model["result"]["manure_dosage"] == raw_result["dose_prediction"]
        assert model["result"]["potential_increase"] is None
    else:
        assert set(model["result"]) == set(raw_result)


def test_explicit_model_results_use_compact_schema_without_internal_details(chat_client, monkeypatch):
    client, headers = chat_client
    result = _orchestrator_result(1)
    result["data"] = {"details": {"secret": "internal"}}
    result["tool_calls_trace"] = [{"arguments": {"secret": "internal"}}]

    response = _post_chat(
        client,
        headers,
        monkeypatch,
        result,
        include_model_results=True,
    )

    data = response.get_json()["data"]
    assert set(data["models"]["model-1"]) == {"model_id", "status", "subject", "result", "meta", "issues"}
    assert "agents_invoked" not in data
    serialized = json.dumps(data, ensure_ascii=False)
    assert "details" not in serialized
    assert "tool_calls_trace" not in serialized
    assert "secret" not in serialized


def test_boundary_pending_is_exposed_only_as_routing_status(chat_client, monkeypatch):
    client, headers = chat_client
    result = _orchestrator_result(2, routing_status="boundary_pending", answer="请确认要评价的专题")
    result["models"] = {}

    response = _post_chat(client, headers, monkeypatch, result, include_model_results=True)

    data = response.get_json()["data"]
    assert data["routing"] == {"question_type": 2, "status": "boundary_pending"}
    assert "routing_status" not in data
    assert data["models"] == {}


def test_llm_success_and_failure_answers_keep_the_same_public_shape(chat_client, monkeypatch):
    client, headers = chat_client
    success = _post_chat(client, headers, monkeypatch, _orchestrator_result(1, answer="LLM 总结"))
    failure = _post_chat(client, headers, monkeypatch, _orchestrator_result(1, answer="确定性降级答复"))

    success_data = success.get_json()["data"]
    failure_data = failure.get_json()["data"]
    assert set(success_data) == set(failure_data)
    assert success_data["answer"] == "LLM 总结"
    assert failure_data["answer"] == "确定性降级答复"


def _done_event(response):
    for line in response.get_data(as_text=True).splitlines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[6:])
        if event.get("event") == "done":
            return event["data"]
    raise AssertionError("流式响应缺少 done 事件")


def test_stream_and_non_stream_share_fields_and_nested_routing(chat_client, monkeypatch):
    client, headers = chat_client
    result = _orchestrator_result(2, routing_status="boundary_pending", answer="请确认问题边界")
    result["models"] = {}
    non_stream = _post_chat(
        client,
        headers,
        monkeypatch,
        result,
        include_model_results=True,
    ).get_json()["data"]

    stream_done = {
        "answer": result["answer"],
        "sources": result["sources"],
        "recommendations": result["recommendations"],
        "question_type": result["question_type"],
        "models": result["models"],
        "trace_id": result["trace_id"],
        "routing": result["routing"],
    }
    monkeypatch.setattr(
        "framework.api.routes.chat.multi_agent_orchestrator.run_stream",
        lambda request, conversation_history=None: iter([{"type": "done", "data": stream_done}]),
    )
    stream_response = client.post(
        "/api/v1/chat/stream",
        json={"message": "请分析", "include_model_results": True},
        headers=headers,
    )
    streamed = _done_event(stream_response)

    assert set(streamed) == set(non_stream)
    assert streamed["routing"] == non_stream["routing"] == {
        "question_type": 2,
        "status": "boundary_pending",
    }
    assert {key: value for key, value in streamed.items() if key != "message_id"} == {
        key: value for key, value in non_stream.items() if key != "message_id"
    }


def _execution_state():
    return {
        "request": {"question": "请分析稳定性", "parcel_id": "P-1"},
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "pending",
        "error": None,
        "question_type": 1,
        "relevance": 1.0,
        "routing_status": "normal",
        "trace_id": "trace-fc",
    }


def _assert_public_execution(result, expected_answer):
    public = _serialize_chat_response(
        {**result["model_results"], "routing_status": "normal", "trace_id": "trace-fc"},
        1,
        include_model_results=True,
    )
    assert public["data"]["answer"] == expected_answer
    assert set(public["data"]["models"]["model-1"]) == {
        "model_id", "status", "subject", "result", "meta", "issues",
    }
    serialized = json.dumps(public, ensure_ascii=False)
    assert "details" not in serialized
    assert "tool_calls_trace" not in serialized


def test_function_calling_success_reuses_generated_answer_without_leaking_trace(monkeypatch):
    from framework.agents import nodes
    from framework.config import Config

    monkeypatch.setattr(Config, "FUNCTION_CALLING_ENABLED", True)
    llm = MagicMock()
    llm.is_available.return_value = True
    llm.generate_with_tools.return_value = {
        "success": True,
        "content": "Function Calling 最终答复",
        "tool_results": {"model-1": _envelope()},
        "tool_calls_trace": [{"tool_name": "model_1_stability_evaluation", "arguments": {"parcel_id": "P-1"}}],
        "iterations": 2,
    }
    monkeypatch.setattr("framework.llm.service.llm_service", llm)
    monkeypatch.setattr("framework.function_calling.specialized_tools.get_specialized_tools", lambda: [{"name": "tool"}])

    result = nodes.execute_models(_execution_state())

    assert result["model_results"]["routing_method"] == "function_calling"
    _assert_public_execution(result, "Function Calling 最终答复")


@pytest.mark.parametrize(
    "fc_enabled,fc_response",
    [
        (True, {"success": True, "content": "未调工具", "tool_results": {}, "tool_calls_trace": [], "iterations": 1}),
        (True, {"success": False, "reason": "tool_execution_failed", "tool_results": {}, "tool_calls_trace": [], "iterations": 1}),
        (False, None),
    ],
    ids=["no-tool-call", "tool-failure", "keyword-fallback"],
)
def test_function_calling_fallback_scenarios_share_public_response(monkeypatch, fc_enabled, fc_response):
    from framework.agents import nodes
    from framework.agents.manager import agent_manager
    from framework.config import Config

    monkeypatch.setattr(Config, "FUNCTION_CALLING_ENABLED", fc_enabled)
    if fc_enabled:
        llm = MagicMock()
        llm.is_available.return_value = True
        llm.generate_with_tools.return_value = fc_response
        monkeypatch.setattr("framework.llm.service.llm_service", llm)
        monkeypatch.setattr("framework.function_calling.specialized_tools.get_specialized_tools", lambda: [{"name": "tool"}])
    fallback = MagicMock(return_value={
        "status": "ok",
        "question_type": 1,
        "models": {"model-1": _envelope()},
        "answer": "关键词回退答复",
        "recommendations": [],
        "routing_method": "keyword_fallback",
    })
    monkeypatch.setattr(agent_manager, "process", fallback)

    result = nodes.execute_models(_execution_state())

    fallback.assert_called_once()
    assert result["model_results"]["routing_method"] == "keyword_fallback"
    _assert_public_execution(result, "关键词回退答复")
