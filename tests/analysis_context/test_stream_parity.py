from types import SimpleNamespace

from framework.agents.orchestrator import MultiAgentOrchestrator


def test_missing_object_has_same_semantics_in_run_and_stream(monkeypatch):
    import uuid
    import framework.observability.observe as observe
    monkeypatch.setattr(uuid, "uuid4", lambda: SimpleNamespace(hex="trace-fixed"))
    monkeypatch.setattr(
        observe, "observe_routing",
        lambda question, context, trace_id=None: (1, 0.9, 1, "normal"),
    )
    request = {
        "question": "这块地稳定吗",
        "analysis_context": {"mode": "spatial", "version": 3, "object": None},
        "validated_identifiers": {}, "scenario_inputs": {},
    }
    orchestrator = MultiAgentOrchestrator()
    normal = orchestrator.run(request)
    events = list(orchestrator.run_stream(request))
    assert [item["type"] for item in events] == ["meta", "done"]
    done = events[-1]["data"]
    for key in ("interaction_state", "analysis_context", "required_object_types", "trace_id"):
        assert done[key] == normal[key]
    assert not any(item["type"] == "token" for item in events)
