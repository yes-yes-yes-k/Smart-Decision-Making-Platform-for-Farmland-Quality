import json

from framework.analysis_context.errors import AnalysisContextConflict
from framework.api.routes import chat as chat_routes
from framework.models import Message


class _ContextService:
    def __init__(self, resolved=None, error=None):
        self.resolved = resolved
        self.error = error

    def resolve(self, conversation, *, user_id, body):
        if self.error:
            raise self.error
        return self.resolved


def _events(response):
    return [
        json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
        if line.startswith("data: ")
    ]


def test_stream_context_error_uses_real_http_status_before_response(
    chat_app, auth_header, monkeypatch,
):
    monkeypatch.setattr(
        chat_routes.chat_request_service, "_context_service",
        _ContextService(error=AnalysisContextConflict("stale")),
    )
    response = chat_app.test_client().post(
        "/api/v1/chat/stream", json={"message": "计算等级"}, headers=auth_header,
    )
    assert response.status_code == 409
    assert response.is_json
    with chat_app.app_context():
        assert Message.query.count() == 0


def test_stream_needs_emits_meta_and_done_without_tokens_and_persists(
    chat_app, auth_header, parcel_context, monkeypatch,
):
    monkeypatch.setattr(
        chat_routes.chat_request_service, "_context_service", _ContextService(parcel_context),
    )

    def fake_stream(request, conversation_history=None):
        common = {
            "interaction_state": "needs_analysis_object",
            "required_object_types": ["parcel"],
            "missing_inputs": [],
            "analysis_context": parcel_context.snapshot(),
            "trace_id": "trace-stream",
        }
        yield {"type": "meta", "data": common}
        yield {"type": "done", "data": {**common,
            "answer": "请选择地块后再计算", "question_type": 2,
            "sources": [], "model_results": {"status": "needs_analysis_object", "data": {
                "agents_invoked": [], "recommendations": [],
            }},
        }}

    monkeypatch.setattr(chat_routes.multi_agent_orchestrator, "run_stream", fake_stream)
    response = chat_app.test_client().post(
        "/api/v1/chat/stream", json={"message": "计算等级"}, headers=auth_header,
    )
    assert response.status_code == 200
    events = _events(response)
    assert [event["event"] for event in events] == ["meta", "done"]
    assert events[-1]["data"]["interaction_state"] == "needs_analysis_object"
    assert events[-1]["data"]["analysis_context"] == parcel_context.snapshot()
    with chat_app.app_context():
        assert [item.role for item in Message.query.order_by(Message.id)] == ["user", "assistant"]


def test_completed_http_and_stream_share_response_and_trace_contract(
    chat_app, auth_header, parcel_context, monkeypatch,
):
    monkeypatch.setattr(
        chat_routes.chat_request_service, "_context_service", _ContextService(parcel_context),
    )
    provenance = {
        "trace_id": "trace-parity", "model_id": "quality-grade-evaluation",
        "model_version": "v1", "data_as_of": "2026", "data_version": "d1",
        "calculated_at": "2026-08-30T00:00:00+00:00", "key_inputs": {"parcel_code": "A0001"},
        "scenario_result": False, "spatial_object": parcel_context.snapshot()["object"],
        "object_title": "分析对象：地块 P001",
    }
    completed = {
        "answer": "分析对象：地块 P001\n\n质量等级为二等",
        "question_type": 2, "interaction_state": "completed",
        "trace_id": "trace-parity", "sources": [], "provenance": provenance,
        "model_results": {"status": "ok", "data": {
            "agents_invoked": ["model-2"], "recommendations": [], "details": {},
        }},
    }
    monkeypatch.setattr(
        chat_routes.multi_agent_orchestrator, "run",
        lambda request, conversation_history=None: completed,
    )
    monkeypatch.setattr(
        chat_routes.multi_agent_orchestrator, "run_stream",
        lambda request, conversation_history=None: iter([
            {"type": "token", "content": "质量等级为二等"},
            {"type": "done", "data": completed},
        ]),
    )
    client = chat_app.test_client()
    http_data = client.post(
        "/api/v1/chat/", json={"message": "计算等级"}, headers=auth_header,
    ).get_json()["data"]
    stream_events = _events(client.post(
        "/api/v1/chat/stream", json={"message": "计算等级"}, headers=auth_header,
    ))
    stream_data = stream_events[-1]["data"]
    for key in (
        "interaction_state", "analysis_context", "provenance",
        "scenario_result", "spatial_object", "object_title", "trace_id",
    ):
        assert stream_data[key] == http_data[key]
    with chat_app.app_context():
        assistant_snapshots = [
            item.analysis_context_snapshot for item in Message.query.filter_by(role="assistant")
        ]
        assert {snapshot["trace_id"] for snapshot in assistant_snapshots} == {"trace-parity"}


def test_stream_translates_split_internal_field_codes_and_persists_chinese(
    chat_app, auth_header, parcel_context, monkeypatch,
):
    monkeypatch.setattr(
        chat_routes.chat_request_service, "_context_service", _ContextService(parcel_context),
    )
    raw_answer = "重度障碍：GGNL、DXBW；中度障碍：SXJ。"

    def fake_stream(request, conversation_history=None):
        for content in ("重度障碍：G", "GNL、DX", "BW；中度障碍：S", "XJ。"):
            yield {"type": "token", "content": content}
        yield {"type": "done", "data": {
            "answer": raw_answer,
            "question_type": 3,
            "interaction_state": "completed",
            "trace_id": "trace-field-labels",
            "sources": [],
            "model_results": {"status": "ok", "data": {
                "agents_invoked": ["model-3"], "recommendations": [], "details": {},
            }},
        }}

    monkeypatch.setattr(chat_routes.multi_agent_orchestrator, "run_stream", fake_stream)
    response = chat_app.test_client().post(
        "/api/v1/chat/stream", json={"message": "主要障碍是什么"}, headers=auth_header,
    )
    events = _events(response)
    streamed_text = "".join(
        event["content"] for event in events if event["event"] == "token"
    )
    assert streamed_text == "重度障碍：灌溉能力、地形部位；中度障碍：速效钾。"
    assert events[-1]["data"]["answer"].endswith(streamed_text)
    with chat_app.app_context():
        assistant = Message.query.filter_by(role="assistant").one()
        assert assistant.content.endswith(streamed_text)
        assert all(code not in assistant.content for code in ("GGNL", "DXBW", "SXJ"))
