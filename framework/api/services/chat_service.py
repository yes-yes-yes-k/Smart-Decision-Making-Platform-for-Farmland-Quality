"""Transaction and serialization boundary shared by HTTP and SSE chat APIs."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from framework.agents.capabilities import get_capability_by_question_type
from framework.analysis_context.contracts import AnalysisContext
from framework.analysis_context.errors import AnalysisObjectInvalid
from framework.analysis_context.provenance import ResultProvenanceBuilder
from framework.analysis_context.service import AnalysisContextService
from framework.models import Conversation, Message, ParcelInfo, db
from framework.observability.analysis_context_metrics import (
    EVENT_LEGACY_FIELD_USED,
    EVENT_NEEDS_ANALYSIS_OBJECT,
    EVENT_NEEDS_SCENARIO_INPUTS,
    record_analysis_context_event,
)


@dataclass(frozen=True)
class PreparedChat:
    conversation: Conversation
    user_message: Message
    history: list[dict[str, str]]
    orchestrator_request: dict[str, Any]
    context_snapshot: dict[str, Any]


class ChatRequestService:
    """Own chat preparation, persistence and wire-format serialization."""

    def __init__(self, context_service: AnalysisContextService | None = None):
        self._context_service = context_service or AnalysisContextService()
        self._provenance_builder = ResultProvenanceBuilder()

    def prepare(self, *, user_id: int, body: Mapping[str, Any]) -> PreparedChat:
        if not isinstance(body, Mapping):
            raise AnalysisObjectInvalid("请求体必须为对象")
        question = body.get("message", "")
        if not isinstance(question, str) or not question.strip():
            raise AnalysisObjectInvalid("问题不能为空", details={"field": "message"})

        try:
            conversation = self._get_or_create_owned_conversation(user_id, body, question)
            history = [
                {"role": item.role, "content": item.content}
                for item in conversation.messages
            ]
            resolved = self._context_service.resolve(
                conversation, user_id=user_id, body=body,
            )
            for field in resolved.deprecations:
                record_analysis_context_event(EVENT_LEGACY_FIELD_USED, field=field)
            snapshot = deepcopy(resolved.snapshot())
            execution_identifiers = self._execution_identifiers(
                snapshot, resolved.validated_identifiers,
            )
            user_message = Message(
                conversation_id=conversation.id,
                role="user",
                content=question,
                analysis_context_snapshot=deepcopy(snapshot),
            )
            db.session.add(user_message)
            db.session.commit()

            request_data: dict[str, Any] = {}
            context = body.get("context")
            if isinstance(context, Mapping):
                request_data.update(context)
            request_data.update({
                key: value for key, value in resolved.scenario_inputs.items()
                if key not in {"message", "context"}
            })
            request_data.update(execution_identifiers)
            request_data.update({
                "question": question,
                "analysis_context": deepcopy(snapshot),
                "calculation_mode": snapshot["mode"],
                "validated_identifiers": execution_identifiers,
                "scenario_inputs": dict(resolved.scenario_inputs),
                "user_id": user_id,
                "conversation_id": conversation.id,
            })
            return PreparedChat(
                conversation=conversation,
                user_message=user_message,
                history=history,
                orchestrator_request=request_data,
                context_snapshot=snapshot,
            )
        except Exception:
            db.session.rollback()
            raise

    def persist_assistant(
        self, prepared: PreparedChat, result: Mapping[str, Any],
    ) -> Message:
        normalized = self._normalize_result(prepared, result)
        interaction_state = normalized.get("interaction_state")
        if interaction_state == "needs_analysis_object":
            record_analysis_context_event(EVENT_NEEDS_ANALYSIS_OBJECT)
        elif interaction_state == "needs_scenario_inputs":
            record_analysis_context_event(EVENT_NEEDS_SCENARIO_INPUTS)
        model_results = normalized.get("model_results", {})
        agent_data = model_results.get("data", {}) if isinstance(model_results, Mapping) else {}
        models = normalized.get("models") or (
            model_results.get("models", {}) if isinstance(model_results, Mapping) else {}
        )
        agents_invoked = agent_data.get("agents_invoked") or (
            list(models) if isinstance(models, Mapping) else []
        )
        snapshot = deepcopy(prepared.context_snapshot)
        snapshot["trace_id"] = normalized.get("trace_id")
        snapshot["provenance"] = deepcopy(normalized.get("provenance") or {})
        message = Message(
            conversation_id=prepared.conversation.id,
            role="assistant",
            content=normalized.get("answer", ""),
            sources=deepcopy(normalized.get("sources") or None),
            agents_invoked=deepcopy(agents_invoked or None),
            recommendations=deepcopy(agent_data.get("recommendations") or None),
            analysis_context_snapshot=snapshot,
        )
        try:
            db.session.add(message)
            db.session.commit()
            return message
        except Exception:
            db.session.rollback()
            raise

    def build_response(
        self,
        prepared: PreparedChat,
        result: Mapping[str, Any],
        *,
        message_id: int | None,
    ) -> dict[str, Any]:
        normalized = self._normalize_result(prepared, result)
        response = dict(normalized)
        response["message_id"] = message_id
        response["analysis_context"] = deepcopy(prepared.context_snapshot)
        provenance = response.get("provenance") or {}
        response["scenario_result"] = provenance.get("scenario_result")
        response["spatial_object"] = deepcopy(provenance.get("spatial_object"))
        response["object_title"] = provenance.get("object_title")
        model_results = response.get("model_results", {})
        agent_data = model_results.get("data", {}) if isinstance(model_results, Mapping) else {}
        if agent_data.get("agents_invoked"):
            response["agents_invoked"] = deepcopy(agent_data["agents_invoked"])
        if agent_data.get("recommendations"):
            response["recommendations"] = deepcopy(agent_data["recommendations"])
        return response

    @staticmethod
    def _execution_identifiers(
        snapshot: Mapping[str, Any], validated: Mapping[str, str],
    ) -> dict[str, str]:
        identifiers = dict(validated)
        obj = snapshot.get("object")
        if not isinstance(obj, Mapping):
            return identifiers
        if obj.get("area_code"):
            identifiers["area_code"] = obj["area_code"]
        if obj.get("type") == "parcel":
            identifiers["parcel_id"] = obj["id"]
            if "parcel_code" not in identifiers:
                parcel = ParcelInfo.query.filter_by(parcel_id=obj["id"]).one_or_none()
                if parcel is not None and parcel.legacy_parcel_code:
                    identifiers["parcel_code"] = parcel.legacy_parcel_code
        return identifiers

    def _get_or_create_owned_conversation(
        self, user_id: int, body: Mapping[str, Any], question: str,
    ) -> Conversation:
        conversation_id = body.get("conversation_id")
        if conversation_id is not None:
            conversation = Conversation.query.filter_by(
                id=conversation_id, user_id=user_id,
            ).first()
            if conversation is None:
                raise AnalysisObjectInvalid("会话不存在或无权访问")
            return conversation
        conversation = Conversation(user_id=user_id, title=question[:50] or "新对话")
        db.session.add(conversation)
        db.session.flush()
        return conversation

    def _normalize_result(
        self, prepared: PreparedChat, result: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized = deepcopy(dict(result))
        normalized.setdefault("interaction_state", "completed")
        normalized.setdefault("analysis_context", deepcopy(prepared.context_snapshot))
        normalized.setdefault("sources", [])
        normalized.setdefault("model_results", {})
        if "models" not in normalized:
            model_results = normalized.get("model_results", {})
            if isinstance(model_results, Mapping):
                normalized["models"] = deepcopy(model_results.get("models", {}))
        normalized.setdefault("required_object_types", [])
        normalized.setdefault("missing_inputs", [])
        if normalized.get("provenance") is None:
            provenance = self._stream_provenance(prepared, normalized)
            if provenance:
                normalized["provenance"] = provenance
                title = provenance["object_title"]
                answer = normalized.get("answer", "")
                if answer and not answer.startswith(title):
                    normalized["answer"] = f"{title}\n\n{answer}"
        return normalized

    def _stream_provenance(
        self, prepared: PreparedChat, result: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if result.get("interaction_state") != "completed":
            return None
        capability = get_capability_by_question_type(result.get("question_type"))
        trace_id = result.get("trace_id")
        if capability is None or not trace_id:
            return None
        analysis_context = AnalysisContext.from_dict(prepared.context_snapshot)
        if analysis_context.mode.value == "spatial" and analysis_context.object is None:
            return None
        model_results = result.get("model_results", {})
        agent_data = model_results.get("data", {}) if isinstance(model_results, Mapping) else {}
        details = agent_data.get("details", {}) if isinstance(agent_data, Mapping) else {}
        models = result.get("models") or (
            model_results.get("models", {}) if isinstance(model_results, Mapping) else {}
        )
        first_agent = next(iter(models.values()), {}) if isinstance(models, Mapping) else {}
        if not first_agent and isinstance(details, Mapping):
            first_agent = next(iter(details.values()), {})
        meta = first_agent.get("meta", {}) if isinstance(first_agent, Mapping) else {}
        provenance_input = {
            "model_version": first_agent.get("model_version") or meta.get("model_version"),
            "data_as_of": first_agent.get("data_as_of") or meta.get("data_as_of"),
            "data_version": first_agent.get("data_version") or meta.get("data_version"),
            "actual_inputs": first_agent.get("actual_inputs", {}),
        } if isinstance(first_agent, Mapping) else {}
        return self._provenance_builder.build(
            trace_id=trace_id,
            analysis_context=analysis_context,
            capability=capability,
            agent_result=provenance_input,
            calculated_at=datetime.now(timezone.utc),
        )


chat_request_service = ChatRequestService()
