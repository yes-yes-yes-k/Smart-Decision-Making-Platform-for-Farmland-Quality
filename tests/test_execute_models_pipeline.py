"""测试 execute_models 管道透传 parcel_id/parcel_code 到 context。

通过 monkeypatch agent_manager.process 拦截 context，验证：
1. request 含 parcel_id/parcel_code 时 context top-level 含这两个字段
2. request 不含时 context 不含这两个字段（现有行为不变）
"""
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


def test_execute_models_passes_parcel_id_and_parcel_code_to_context():
    """execute_models 应从 state['request'] 提取 parcel_id/parcel_code 到 context top-level。"""
    from framework.agents.manager import agent_manager

    captured = {}

    def fake_process(question, context):
        captured["question"] = question
        captured["context"] = context
        return _stub_process_return()

    real_process = agent_manager.process
    agent_manager.process = fake_process
    try:
        state = _make_state("我的田质量等级", {"parcel_id": "1", "parcel_code": "A0001"})
        execute_models(state)
    finally:
        agent_manager.process = real_process

    ctx = captured["context"]
    assert ctx.get("parcel_id") == "1", f"parcel_id 未透传到 context top-level: {ctx}"
    assert ctx.get("parcel_code") == "A0001", f"parcel_code 未透传到 context top-level: {ctx}"
    # area_code 仍应存在（现有行为不变）
    assert ctx.get("area_code") == "lechang"
    # question_type 应从 state 透传到 context
    assert ctx.get("question_type") == 3, f"question_type 未透传到 context: {ctx}"
    print("✓ execute_models 透传 parcel_id/parcel_code 到 context top-level")


def test_execute_models_no_parcel_when_absent():
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


def test_execute_models_passes_only_parcel_id():
    """request 仅含 parcel_id 时 context 仅含 parcel_id（model-5 走 mock 回退）。"""
    from framework.agents.manager import agent_manager

    captured = {}

    def fake_process(question, context):
        captured["context"] = context
        return _stub_process_return()

    real_process = agent_manager.process
    agent_manager.process = fake_process
    try:
        state = _make_state("我的田质量等级", {"parcel_id": "10"})
        execute_models(state)
    finally:
        agent_manager.process = real_process

    ctx = captured["context"]
    assert ctx.get("parcel_id") == "10"
    assert "parcel_code" not in ctx
    print("✓ request 仅含 parcel_id 时 context 仅含 parcel_id")


if __name__ == "__main__":
    test_execute_models_passes_parcel_id_and_parcel_code_to_context()
    test_execute_models_no_parcel_when_absent()
    test_execute_models_passes_only_parcel_id()
    print("\n所有 execute_models 管道透传测试通过！")
