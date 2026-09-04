import pytest

from framework.analysis_context.errors import (
    AnalysisContextConflict,
    AnalysisObjectInvalid,
    AnalysisObjectValidationUnavailable,
)
from framework.api.routes import chat as chat_routes
from framework.models import Conversation, Message, db


class _ContextService:
    def __init__(self, resolved=None, error=None):
        self.resolved = resolved
        self.error = error

    def resolve(self, conversation, *, user_id, body):
        if self.error:
            raise self.error
        return self.resolved


def _needs_result(state="needs_analysis_object"):
    message = "请选择地块后再计算" if state == "needs_analysis_object" else "请补充情景参数"
    return {
        "answer": message,
        "question_type": 2,
        "interaction_state": state,
        "required_object_types": ["parcel"] if state == "needs_analysis_object" else [],
        "missing_inputs": [] if state == "needs_analysis_object" else ["SJD"],
        "trace_id": "trace-needs",
        "model_results": {"status": state, "data": {
            "agents_invoked": [], "recommendations": [], "summary": message,
        }},
    }


@pytest.mark.parametrize("error,status,code", [
    (AnalysisObjectInvalid("unknown"), 422, "analysis_object_invalid"),
    (AnalysisContextConflict("stale"), 409, "analysis_context_conflict"),
    (AnalysisObjectValidationUnavailable("down"), 503, "analysis_object_validation_unavailable"),
])
def test_context_errors_precede_message_persistence(
    chat_app, auth_header, monkeypatch, error, status, code,
):
    monkeypatch.setattr(
        chat_routes.chat_request_service, "_context_service", _ContextService(error=error),
    )
    response = chat_app.test_client().post(
        "/api/v1/chat/", json={"message": "计算等级"}, headers=auth_header,
    )
    assert response.status_code == status
    assert response.get_json()["error"]["code"] == code
    with chat_app.app_context():
        assert Message.query.count() == 0


def test_needs_state_persists_two_equal_snapshots_without_execution(
    chat_app, auth_header, parcel_context, monkeypatch,
):
    monkeypatch.setattr(
        chat_routes.chat_request_service, "_context_service", _ContextService(parcel_context),
    )
    calls = []
    monkeypatch.setattr(
        chat_routes.multi_agent_orchestrator, "run",
        lambda request, conversation_history=None: calls.append(request) or _needs_result(),
    )
    response = chat_app.test_client().post(
        "/api/v1/chat/", json={"message": "计算等级"}, headers=auth_header,
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["interaction_state"] == "needs_analysis_object"
    assert data["analysis_context"] == parcel_context.snapshot()
    assert len(calls) == 1
    assert [item["agent_id"] for item in calls[0]["capabilities"]] == [
        "model-1", "model-2", "model-3", "model-4", "model-5",
    ]
    with chat_app.app_context():
        messages = Message.query.order_by(Message.id).all()
        assert [item.role for item in messages] == ["user", "assistant"]
        assert messages[0].analysis_context_snapshot == parcel_context.snapshot()
        assistant_base = dict(messages[1].analysis_context_snapshot)
        assistant_base.pop("trace_id")
        assistant_base.pop("provenance")
        assert assistant_base == parcel_context.snapshot()
        assert messages[1].analysis_context_snapshot["provenance"] == {}


def test_message_snapshots_remain_immutable_after_later_request(
    chat_app, auth_header, parcel_context, monkeypatch,
):
    monkeypatch.setattr(
        chat_routes.chat_request_service, "_context_service", _ContextService(parcel_context),
    )
    monkeypatch.setattr(
        chat_routes.multi_agent_orchestrator, "run",
        lambda request, conversation_history=None: _needs_result(),
    )
    first = chat_app.test_client().post(
        "/api/v1/chat/", json={"message": "第一次"}, headers=auth_header,
    )
    assert first.status_code == 200
    with chat_app.app_context():
        first_snapshot = db.session.get(Message, 1).analysis_context_snapshot.copy()
        conversation = Conversation.query.one()
        updated_object = dict(conversation.analysis_object or parcel_context.snapshot()["object"])
        updated_object["id"] = "P002"
        updated_object["display_name"] = "地块 P002"
        conversation.analysis_object = updated_object
        conversation.context_version = (conversation.context_version or 0) + 1
        db.session.commit()
        assert db.session.get(Message, 1).analysis_context_snapshot == first_snapshot


def test_comprehensive_interaction_fields_are_exposed_to_client(
    chat_app, auth_header, parcel_context, monkeypatch,
):
    monkeypatch.setattr(
        chat_routes.chat_request_service, "_context_service", _ContextService(parcel_context),
    )
    monkeypatch.setattr(
        chat_routes.multi_agent_orchestrator, "run",
        lambda request, conversation_history=None: {
            "interaction_state":"needs_confirmation",
            "run_id":"run-http-1", "checkpoint_version":1,
            "plan_summary":{"plan_version":1,"tasks":[]},
            "proposed_defaults":{"target_ph":6.5},
            "report_draft":None, "degradations":[], "trace_id":"trace-http-1",
            "answer":"请确认分析范围。", "sources":[], "models":{},
        },
    )
    response=chat_app.test_client().post(
        "/api/v1/chat/", json={"message":"生成综合报告"}, headers=auth_header,
    )
    assert response.status_code==200
    data=response.get_json()["data"]
    assert data["interaction_state"]=="needs_confirmation"
    assert data["run_id"]=="run-http-1"
    assert data["checkpoint_version"]==1
    assert data["plan_summary"]=={"plan_version":1,"tasks":[]}
    assert data["proposed_defaults"]=={"target_ph":6.5}
    assert data["degradations"]==[]


def test_comprehensive_interaction_without_answer_persists_user_prompt(
    chat_app, auth_header, parcel_context, monkeypatch,
):
    monkeypatch.setattr(
        chat_routes.chat_request_service, "_context_service", _ContextService(parcel_context),
    )
    monkeypatch.setattr(
        chat_routes.multi_agent_orchestrator, "run",
        lambda request, conversation_history=None: {
            "interaction_state":"needs_confirmation",
            "run_id":"run-http-prompt", "checkpoint_version":1,
            "plan_summary":{"plan_version":1,"tasks":[]},
            "report_draft":None, "degradations":[], "trace_id":"trace-http-prompt",
        },
    )
    response=chat_app.test_client().post(
        "/api/v1/chat/", json={"message":"生成综合报告"}, headers=auth_header,
    )
    assert response.status_code==200
    assert response.get_json()["data"]["answer"] == (
        "分析范围和所需输入已准备好，请确认后开始计算。"
    )
    with chat_app.app_context():
        assistant=Message.query.filter_by(role="assistant").one()
        assert assistant.content == "分析范围和所需输入已准备好，请确认后开始计算。"
