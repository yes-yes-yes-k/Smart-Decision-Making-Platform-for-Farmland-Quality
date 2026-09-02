"""Conservative intent classification and deterministic traffic gate."""
from __future__ import annotations

from .contracts import InteractionIntent, InteractionKind
from .prompt_catalog import COORDINATOR_PROMPT
from .structured_roles import StructuredRoleError, StructuredRoleRunner


class Coordinator:
    EXPLICIT_TERMS = ("综合诊断", "综合报告", "全面诊断", "诊断与改良报告")
    def __init__(self, runner: StructuredRoleRunner): self._runner = runner

    def classify(self, message: str, *, deterministic_question_type: int | None = None, context: dict | None = None) -> InteractionIntent:
        explicit = any(term in message for term in self.EXPLICIT_TERMS)
        try:
            intent = self._runner.generate(role="coordinator", prompt=f"{COORDINATOR_PROMPT.system}\nmessage={message}\ncontext={context or {}}", schema=InteractionIntent)
        except StructuredRoleError:
            kind = InteractionKind.COMPREHENSIVE_ANALYSIS if explicit else (InteractionKind.SINGLE_ANALYSIS if deterministic_question_type else InteractionKind.KNOWLEDGE)
            return InteractionIntent(kind=kind, confidence=1 if explicit else .5, reason_code="EXPLICIT_COMPREHENSIVE_REPORT" if explicit else "DETERMINISTIC_FALLBACK", prompt_version=COORDINATOR_PROMPT.version)
        if intent.kind == InteractionKind.COMPREHENSIVE_ANALYSIS and not explicit:
            return InteractionIntent(kind=InteractionKind.SINGLE_ANALYSIS if deterministic_question_type else InteractionKind.KNOWLEDGE, confidence=intent.confidence, reason_code="DETERMINISTIC_FALLBACK", prompt_version=intent.prompt_version)
        return intent


class TrafficGate:
    def route(self, intent: InteractionIntent, *, calculation_mode: str, object_type: str | None) -> str:
        if intent.kind != InteractionKind.COMPREHENSIVE_ANALYSIS:
            return "fast"
        return "comprehensive" if calculation_mode == "spatial" and object_type == "parcel" else "unsupported"
