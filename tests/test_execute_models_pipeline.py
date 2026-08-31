"""execute_models 只消费中央解析后的规范对象与已验证旧标识。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.state import MultiAgentState
from framework.agents.nodes import execute_models


def _make_state(question: str, request_extra: dict | None = None) -> MultiAgentState:
    req = {"question": question, "area_code": "lechang"}
    if request_extra:
        req.update(request_extra)
    return {
        "request": req,
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": 3,
        "relevance": 0.8,
        "analysis_context": {"mode": "spatial", "version": 0, "object": None},
        "calculation_mode": "spatial",
        "guard_decision": {"allowed": True, "interaction_state": "completed"},
        "validated_identifiers": {},
        "scenario_inputs": {},
        "user_id": 7,
        "conversation_id": 1,
    }


def _parcel_object(parcel_id="P001", area_code="440281"):
    return {
        "type": "parcel", "id": parcel_id, "display_name": f"地块 {parcel_id}",
        "area_code": area_code, "parent_path": [], "source": "parcel_info",
        "validated_at": "2026-08-31T00:00:00+00:00",
    }


def _stub_process_return():
    """agent_manager.process 的桩返回值，符合 execute_models 期望的 {status: ok, data: {...}} 结构。"""
    return {
        "status": "ok",
        "data": {
            "question_type": 5,
            "agents_invoked": ["model-5"],
            "summary": "",
            "details": {},
            "recommendations": [],
        },
    }


def test_execute_models_uses_canonical_parcel_and_verified_legacy_code():
    from framework.agents.manager import agent_manager

    captured = {}

    def fake_process(question, context):
        captured["question"] = question
        captured["context"] = context
        return _stub_process_return()

    real_process = agent_manager.process
    agent_manager.process = fake_process
    try:
        state = _make_state("我的田质量等级", {"parcel_id": "UNTRUSTED", "parcel_code": "BAD"})
        state["analysis_context"] = {"mode": "spatial", "version": 2, "object": _parcel_object()}
        state["validated_identifiers"] = {"parcel_id": "P001", "parcel_code": "A0001"}
        state["question_type"] = 2
        execute_models(state)
    finally:
        agent_manager.process = real_process

    ctx = captured["context"]
    assert ctx["parcel_id"] == "P001"
    assert ctx["parcel_code"] == "A0001"
    assert ctx["area_code"] == "440281"
    assert ctx["question_type"] == 2
    assert ctx["guard_passed"] is True and ctx["execution_channel"] == "chat"


def test_execute_models_no_parcel_when_canonical_object_absent():
    """request 不含 parcel_id/parcel_code 时 context 不应包含这两个字段。"""
    from framework.agents.manager import agent_manager

    captured = {}

    def fake_process(question, context):
        captured["context"] = context
        return _stub_process_return()

    real_process = agent_manager.process
    agent_manager.process = fake_process
    try:
        state = _make_state("我的田质量等级")
        execute_models(state)
    finally:
        agent_manager.process = real_process

    ctx = captured["context"]
    assert "parcel_id" not in ctx, f"不应含 parcel_id: {ctx}"
    assert "parcel_code" not in ctx, f"不应含 parcel_code: {ctx}"
    print("✓ request 无 parcel 标识符时 context 不含这两个字段")


def test_execute_models_never_reads_unverified_raw_ids():
    from framework.agents.manager import agent_manager

    captured = {}

    def fake_process(question, context):
        captured["context"] = context
        return _stub_process_return()

    real_process = agent_manager.process
    agent_manager.process = fake_process
    try:
        state = _make_state("我的田质量等级", {"parcel_id": "RAW", "parcel_code": "RAW-CODE"})
        state["analysis_context"] = {"mode": "spatial", "version": 1, "object": _parcel_object("P010")}
        execute_models(state)
    finally:
        agent_manager.process = real_process

    ctx = captured["context"]
    assert ctx.get("parcel_id") == "P010"
    assert "parcel_code" not in ctx


if __name__ == "__main__":
    test_execute_models_uses_canonical_parcel_and_verified_legacy_code()
    test_execute_models_no_parcel_when_canonical_object_absent()
    test_execute_models_never_reads_unverified_raw_ids()
    print("\n所有 execute_models 管道透传测试通过！")
