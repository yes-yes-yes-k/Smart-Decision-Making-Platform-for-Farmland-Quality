"""Transaction and serialization boundary shared by HTTP and SSE chat APIs."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from framework.agents.workflows.comprehensive.contracts import InteractionResponse

from framework.agents.capabilities import (
    get_capability_by_question_type,
    public_comprehensive_capabilities,
)
from framework.analysis_context.contracts import AnalysisContext
from framework.analysis_context.errors import AnalysisObjectInvalid
from framework.analysis_context.provenance import (
    ResultProvenanceBuilder,
    prepend_object_title,
)
from framework.analysis_context.service import AnalysisContextService
from framework.domain.public_field_labels import translate_public_text
from framework.domain.public_numbers import round_long_decimals
from framework.models import AcidificationMeasurement, Conversation, Message, ParcelInfo, db
from framework.observability.analysis_context_metrics import (
    EVENT_LEGACY_FIELD_USED,
    EVENT_NEEDS_ANALYSIS_OBJECT,
    EVENT_NEEDS_SCENARIO_INPUTS,
    record_analysis_context_event,
)


@dataclass(frozen=True)
class PreparedChat:
    conversation: Conversation
    user_message: Message | None
    history: list[dict[str, str]]
    orchestrator_request: dict[str, Any]
    context_snapshot: dict[str, Any]
    interaction_response: InteractionResponse | None = None


class ChatRequestService:
    """Own chat preparation, persistence and wire-format serialization."""

    def __init__(self, context_service: AnalysisContextService | None = None):
        self._context_service = context_service or AnalysisContextService()
        self._provenance_builder = ResultProvenanceBuilder()

    def prepare(self, *, user_id: int, body: Mapping[str, Any]) -> PreparedChat:
        if not isinstance(body, Mapping):
            raise AnalysisObjectInvalid("请求体必须为对象")
        response_payload = body.get("interaction_response")
        if response_payload is not None:
            response = InteractionResponse.model_validate(response_payload)
            conversation = self._get_or_create_owned_conversation(user_id, body, "综合诊断恢复")
            history=[{
                "role": item.role,
                "content": (
                    translate_public_text(item.content)
                    if item.role == "assistant" else item.content
                ),
            } for item in conversation.messages]
            snapshot={"mode":"spatial","version":conversation.context_version or 0,"object":deepcopy(conversation.analysis_object)}
            return PreparedChat(conversation,None,history,{"conversation_id":conversation.id,"user_id":user_id},snapshot,response)
        question = body.get("message", "")
        if not isinstance(question, str) or not question.strip():
            raise AnalysisObjectInvalid("问题不能为空", details={"field": "message"})

        try:
            conversation = self._get_or_create_owned_conversation(user_id, body, question)
            cd_message = max(
                (item for item in conversation.messages if item.role == "assistant"
                 and (item.analysis_context_snapshot or {}).get("cd_draft")),
                key=lambda item: item.analysis_context_snapshot["cd_draft"]["revision"],
                default=None,
            )
            cd_snapshot = cd_message.analysis_context_snapshot if cd_message else {}
            cd_draft = cd_snapshot.get("cd_draft")
            history = [
                {
                    "role": item.role,
                    "content": (
                        translate_public_text(item.content)
                        if item.role == "assistant" else item.content
                    ),
                }
                for item in conversation.messages
            ]
            resolved = self._context_service.resolve(
                conversation, user_id=user_id, body=body,
            )
            acidification_history = []
            current_measurement = None
            measurement_id = body.get("acidification_measurement_id")
            if measurement_id is not None:
                try:
                    measurement_id = int(measurement_id)
                except (TypeError, ValueError) as exc:
                    raise AnalysisObjectInvalid("酸化测算记录标识无效") from exc
                current_measurement = AcidificationMeasurement.query.filter_by(
                    id=measurement_id,
                    user_id=user_id,
                    conversation_id=conversation.id,
                ).first()
                if current_measurement is None:
                    raise AnalysisObjectInvalid("酸化测算记录不存在或无权访问")
                acidification_history = [
                    {
                        "measurement_id": item.id,
                        "parcel_id": item.parcel_id,
                        "mode": item.mode,
                        "land_type": item.land_type,
                        "input_data": item.input_data or {},
                        "result_data": item.result_data,
                        "source_info": item.source_info or {},
                        "status": item.status,
                        "created_at": item.created_at.isoformat() if item.created_at else None,
                    }
                    for item in AcidificationMeasurement.query.filter_by(
                        user_id=user_id,
                        conversation_id=conversation.id,
                    ).order_by(
                        AcidificationMeasurement.created_at,
                        AcidificationMeasurement.id,
                    ).all()
                ]
            for field in resolved.deprecations:
                record_analysis_context_event(EVENT_LEGACY_FIELD_USED, field=field)
            snapshot = deepcopy(resolved.snapshot())
            if measurement_id is not None:
                snapshot["acidification_measurement_id"] = measurement_id
                # Use the conversation-owned persisted measurement as the authority;
                # never trust client-supplied result values for the agent context.
                snapshot["acidification_result_context"] = {
                    "mode": current_measurement.mode,
                    "model_id": (current_measurement.result_data or {}).get("model_id"),
                    "metric": (
                        "quicklime_dose" if current_measurement.mode == "governance"
                        else "ph_drop_amount" if (current_measurement.result_data or {}).get("model_id") == 38
                        else "unknown"
                    ),
                    "value": (((current_measurement.result_data or {}).get("predictions") or [{}])[0]).get("result"),
                    "unit": (((current_measurement.result_data or {}).get("predictions") or [{}])[0]).get("unit"),
                    "material": "生石灰" if current_measurement.mode == "governance" else None,
                    "source": (current_measurement.result_data or {}).get("source"),
                    "inputs": current_measurement.input_data or {},
                    "assumptions": (current_measurement.result_data or {}).get("assumed_fields", {}),
                }
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
                "question": (
                    question
                    + "\n\n【本轮酸化结果权威上下文】\n"
                    + json.dumps(snapshot.get("acidification_result_context", {}), ensure_ascii=False, separators=(",", ":"))
                    + "\n仅解释本轮结果。治理模式只回答生石灰剂量；预测 model_id=38 的结果是 pH 下降量，不是预测后的 pH。不得引入其他酸化模型或其他材料的剂量。"
                    + "\n\n【当前会话全部酸化测算记录】\n"
                    + json.dumps(acidification_history, ensure_ascii=False, separators=(",", ":"))
                    + "\n请将以上记录作为本轮分析上下文，区分每条记录的地块、模式和结果类别。"
                    if measurement_id is not None else question
                ),
                "analysis_context": deepcopy(snapshot),
                "calculation_mode": snapshot["mode"],
                "validated_identifiers": execution_identifiers,
                "scenario_inputs": dict(resolved.scenario_inputs),
                "capabilities": public_comprehensive_capabilities(),
                "user_id": user_id,
                "conversation_id": conversation.id,
                "_cd_draft": deepcopy(cd_draft),
                "_cd_trial_message_id": cd_message.id if cd_snapshot.get("cd_trial_result") else None,
                "_cd_revision": user_message.id,
            })
            if measurement_id is not None:
                request_data["acidification_measurement_id"] = measurement_id
                request_data["acidification_measurement_history"] = acidification_history
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
        cd_revision = prepared.orchestrator_request.get("_cd_revision")
        if normalized.get("_cd_draft") and cd_revision is not None:
            snapshot["cd_draft"] = {
                **deepcopy(normalized["_cd_draft"]),
                "revision": cd_revision,
            }
            cd_result = models.get("cd_conversation", {})
            if cd_result.get("status") in {"success", "degraded"} and cd_result.get("prediction") is not None:
                snapshot["cd_trial_result"] = {key: value for key, value in cd_result.items() if key != "draft"}
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
        if not normalized.get("answer"):
            normalized["answer"] = self._interaction_prompt(
                normalized["interaction_state"]
            )
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
                normalized["answer"] = prepend_object_title(
                    normalized.get("answer", ""),
                    object_title=provenance["object_title"],
                )
        normalized["answer"] = translate_public_text(normalized.get("answer", ""))
        normalized["answer"] = round_long_decimals(normalized["answer"])
        if isinstance(normalized.get("report_draft"), str):
            normalized["report_draft"] = translate_public_text(normalized["report_draft"])
        recommendations = normalized.get("recommendations")
        if isinstance(recommendations, list):
            normalized["recommendations"] = [
                translate_public_text(item) if isinstance(item, str) else item
                for item in recommendations
            ]
        return normalized

    @staticmethod
    def _interaction_prompt(interaction_state: str) -> str:
        return {
            "needs_input": "请补充必要的地块信息后继续。",
            "needs_confirmation": "分析范围和所需输入已准备好，请确认后开始计算。",
            "awaiting_release": "报告草稿已生成，请确认发布或提出修改意见。",
            "canceled": "本次综合诊断已取消。",
            "failed": "本次综合诊断未能完成，请检查地块数据后重试。",
        }.get(interaction_state, "请求已处理。")

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
