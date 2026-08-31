from framework.agents import nodes
from framework.agents.manager import agent_manager
from framework.agents.orchestrator import MultiAgentOrchestrator


def _route(monkeypatch, question_type):
    import framework.observability.observe as observe
    monkeypatch.setattr(
        observe, "observe_routing",
        lambda question, context, trace_id=None: (question_type, 0.9, question_type, "normal"),
    )


def _empty_request(question="这块地稳定吗"):
    return {
        "question": question,
        "analysis_context": {"mode": "spatial", "version": 0, "object": None},
        "validated_identifiers": {}, "scenario_inputs": {},
    }


def test_missing_parcel_short_circuits_all_execution(monkeypatch):
    _route(monkeypatch, 1)
    calls = {"fc": 0, "manager": 0, "llm": 0}
    monkeypatch.setattr(nodes, "_execute_via_function_calling", lambda *a, **k: calls.__setitem__("fc", calls["fc"] + 1))
    monkeypatch.setattr(agent_manager, "process", lambda *a, **k: calls.__setitem__("manager", calls["manager"] + 1))
    monkeypatch.setattr(nodes.llm_service, "generate", lambda *a, **k: calls.__setitem__("llm", calls["llm"] + 1))
    result = MultiAgentOrchestrator().run(_empty_request())
    assert result["interaction_state"] == "needs_analysis_object"
    assert result["required_object_types"] == ["parcel"]
    assert result["answer"] == "请选择满足该能力尺度要求的分析对象"
    assert result["model_results"]["data"]["agents_invoked"] == []
    assert calls == {"fc": 0, "manager": 0, "llm": 0}


def test_scenario_missing_inputs_short_circuits_execution(monkeypatch):
    _route(monkeypatch, 4)
    calls = {"manager": 0}
    monkeypatch.setattr(agent_manager, "process", lambda *a, **k: calls.__setitem__("manager", 1))
    result = MultiAgentOrchestrator().run({
        "question": "酸化改良试算",
        "analysis_context": {"mode": "scenario", "version": None, "object": None},
        "scenario_inputs": {"SJD": 5.2},
    })
    assert result["interaction_state"] == "needs_scenario_inputs"
    assert set(result["missing_inputs"]) == {"JHX", "JLA", "land_type", "fertilizer_type"}
    assert calls["manager"] == 0


def test_complete_model4_scenario_reaches_professional_execution(monkeypatch):
    _route(monkeypatch, 4)
    captured = {}
    monkeypatch.setattr(nodes, "_execute_via_function_calling", lambda *a, **k: None)
    def process(question, context):
        captured.update(context)
        return {"status": "ok", "data": {"agents_invoked": ["model-4"], "summary": "完成", "details": {}, "recommendations": []}}
    monkeypatch.setattr(agent_manager, "process", process)
    monkeypatch.setattr(nodes, "LLM_AVAILABLE", False)
    inputs = {"SJD": 5.2, "JHX": 1.0, "JLA": 2.0, "land_type": "upland", "fertilizer_type": "compound"}
    result = MultiAgentOrchestrator().run({
        "question": "酸化改良试算",
        "analysis_context": {"mode": "scenario", "version": None, "object": None},
        "scenario_inputs": inputs,
    })
    assert result["interaction_state"] == "completed"
    assert {key: captured[key] for key in inputs} == inputs
    assert captured["guard_passed"] is True


def test_type_zero_is_not_blocked_by_spatial_guard(monkeypatch):
    _route(monkeypatch, 0)
    monkeypatch.setattr(nodes.rag_chain, "chat", lambda *a, **k: {"answer": "知识回答", "sources": []})
    result = MultiAgentOrchestrator().run(_empty_request("什么是耕地质量"))
    assert result["answer"] == "知识回答"
    assert result["interaction_state"] == "completed"
