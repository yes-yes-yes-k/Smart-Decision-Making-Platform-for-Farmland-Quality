"""Conversation-scoped analysis-object lifecycle service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from framework.models import Conversation, db

from .contracts import AnalysisContext, AnalysisObject, CalculationMode, ContextAction
from .errors import AnalysisContextConflict, AnalysisObjectInvalid
from .legacy import LegacyAnalysisContextAdapter


@dataclass(frozen=True)
class ResolvedRequestContext:
    context: AnalysisContext
    validated_identifiers: dict[str, str]
    deprecations: Sequence[str]
    scenario_inputs: dict[str, Any]

    def snapshot(self) -> dict[str, Any]:
        return self.context.to_dict()


class AnalysisContextService:
    CONTROL_FIELDS = {
        "analysis_context", "calculation_mode", "parcel_id", "parcel_code",
        "area_code", "question", "conversation_id",
    }

    def __init__(self, legacy_adapter: LegacyAnalysisContextAdapter | None = None):
        self._legacy_adapter = legacy_adapter or LegacyAnalysisContextAdapter()

    def resolve(
        self,
        conversation: Conversation,
        *,
        user_id: int,
        body: Mapping[str, Any],
    ) -> ResolvedRequestContext:
        if not isinstance(body, Mapping):
            raise AnalysisObjectInvalid("请求体必须为对象")
        self._ensure_owned(conversation, user_id)
        mode = self._parse_mode(body)
        if mode is CalculationMode.SCENARIO:
            return ResolvedRequestContext(
                context=AnalysisContext(mode=mode, version=None, object=None),
                validated_identifiers={},
                deprecations=(),
                scenario_inputs={
                    key: value for key, value in body.items()
                    if key not in self.CONTROL_FIELDS
                },
            )

        action, implicit_legacy_set = self._parse_action(body)
        if action is ContextAction.INHERIT:
            return self._inherit(conversation)

        request_context = body.get("analysis_context") or {}
        expected_version = request_context.get("expected_version")
        if implicit_legacy_set and expected_version is None:
            expected_version = conversation.context_version
        self._validate_expected_version(expected_version)

        canonical_object = None
        identifiers: dict[str, str] = {}
        deprecations: Sequence[str] = ()
        if action is ContextAction.SET:
            resolution = self._legacy_adapter.resolve(body, user_id=user_id)
            if resolution.object is None:
                raise AnalysisObjectInvalid("set 操作必须提供分析对象")
            canonical_object = resolution.object
            identifiers = resolution.validated_identifiers
            deprecations = resolution.deprecations

        return self._update(
            conversation,
            user_id=user_id,
            expected_version=expected_version,
            canonical_object=canonical_object,
            identifiers=identifiers,
            deprecations=deprecations,
        )

    @staticmethod
    def _ensure_owned(conversation: Conversation, user_id: int) -> None:
        if conversation is None or conversation.id is None or conversation.user_id != user_id:
            raise AnalysisObjectInvalid("会话不存在或无权访问")

    @staticmethod
    def _parse_mode(body: Mapping[str, Any]) -> CalculationMode:
        value = body.get("calculation_mode", CalculationMode.SPATIAL.value)
        try:
            return CalculationMode(value)
        except (TypeError, ValueError) as exc:
            raise AnalysisObjectInvalid("calculation_mode 非法") from exc

    @staticmethod
    def _parse_action(body: Mapping[str, Any]) -> tuple[ContextAction, bool]:
        context = body.get("analysis_context")
        if context is not None and not isinstance(context, Mapping):
            raise AnalysisObjectInvalid("analysis_context 必须为对象")
        legacy_present = any(body.get(name) is not None for name in ("parcel_id", "parcel_code", "area_code"))
        if context is not None and "action" not in context and context:
            raise AnalysisObjectInvalid("analysis_context.action 缺失")
        if context is None or "action" not in context:
            return (ContextAction.SET, True) if legacy_present else (ContextAction.INHERIT, False)
        try:
            return ContextAction(context["action"]), False
        except (TypeError, ValueError) as exc:
            raise AnalysisObjectInvalid("analysis_context.action 非法") from exc

    @staticmethod
    def _validate_expected_version(value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AnalysisObjectInvalid("set/clear 必须提供非负整数 expected_version")

    @staticmethod
    def _inherit(conversation: Conversation) -> ResolvedRequestContext:
        try:
            obj = (
                AnalysisObject.from_dict(conversation.analysis_object)
                if conversation.analysis_object is not None else None
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AnalysisObjectInvalid("会话中保存的分析对象已损坏") from exc
        return ResolvedRequestContext(
            context=AnalysisContext(
                mode=CalculationMode.SPATIAL,
                version=conversation.context_version,
                object=obj,
            ),
            validated_identifiers={},
            deprecations=(),
            scenario_inputs={},
        )

    @staticmethod
    def _update(
        conversation: Conversation,
        *,
        user_id: int,
        expected_version: int,
        canonical_object: AnalysisObject | None,
        identifiers: dict[str, str],
        deprecations: Sequence[str],
    ) -> ResolvedRequestContext:
        object_json = canonical_object.to_dict() if canonical_object else None
        updated = Conversation.query.filter_by(
            id=conversation.id,
            user_id=user_id,
            context_version=expected_version,
        ).update({
            Conversation.analysis_object: object_json,
            Conversation.context_version: expected_version + 1,
            Conversation.analysis_object_updated_at: datetime.now(timezone.utc),
        }, synchronize_session=False)
        if updated != 1:
            db.session.rollback()
            latest = Conversation.query.filter_by(id=conversation.id, user_id=user_id).one_or_none()
            if latest is None:
                raise AnalysisObjectInvalid("会话不存在或无权访问")
            raise AnalysisContextConflict(
                "分析对象已被其他请求更新",
                details={
                    "latest_version": latest.context_version,
                    "latest_object": latest.analysis_object,
                },
            )
        db.session.commit()
        db.session.refresh(conversation)
        return ResolvedRequestContext(
            context=AnalysisContext(
                mode=CalculationMode.SPATIAL,
                version=expected_version + 1,
                object=canonical_object,
            ),
            validated_identifiers=dict(identifiers),
            deprecations=tuple(deprecations),
            scenario_inputs={},
        )
