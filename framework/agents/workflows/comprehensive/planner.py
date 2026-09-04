"""Constrained comprehensive plan production and validation."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Protocol

from .contracts import DiagnosticPlan
from .prompt_catalog import PLANNER_PROMPT
from .structured_roles import StructuredRoleError, StructuredRoleRunner


@dataclass(frozen=True)
class PlanningFacts:
    history_available: bool
    user_requested_acidification: bool = False
    user_requested_organic_matter: bool = False


class PlanningFactSource(Protocol):
    def count_history_snapshots(self, parcel_id: str) -> int: ...
    def has_stability_result(self, parcel_id: str) -> bool: ...


class OrmPlanningFactSource:
    def count_history_snapshots(self, parcel_id: str) -> int:
        from framework.models.thematic_model import ParcelHistorySnapshot
        return ParcelHistorySnapshot.query.filter_by(parcel_id=parcel_id).count()
    def has_stability_result(self, parcel_id: str) -> bool:
        from framework.models.thematic_model import StabilityRiskResult
        return StabilityRiskResult.query.filter_by(parcel_id=parcel_id).first() is not None


class PlanningFactsResolver:
    ACIDIFICATION_TERMS=("酸化", "酸性", "提高ph", "改良酸土")
    ORGANIC_MATTER_TERMS=("有机质", "培肥", "增施有机肥", "肥力提升")
    def __init__(self, source: PlanningFactSource): self._source=source
    def resolve(self, *, parcel_id: str, user_message: str) -> PlanningFacts:
        msg=user_message.casefold()
        return PlanningFacts(self._source.count_history_snapshots(parcel_id)>=2 or self._source.has_stability_result(parcel_id), any(x in msg for x in self.ACIDIFICATION_TERMS), any(x in msg for x in self.ORGANIC_MATTER_TERMS))


class PlanValidationError(ValueError):
    def __init__(self, code: str): super().__init__(code); self.code=code


class PlanValidator:
    ALLOWED=frozenset({"model-1","model-2","model-3","model-4","model-5"})
    TASK_IDS={"model-1":"stability-risk","model-2":"quality-evaluation","model-3":"problem-diagnosis","model-4":"acidification-remediation","model-5":"organic-matter-improvement"}
    OPTIONAL_PREDICATES={"model-1":{"history_available"},"model-4":{"user_requested_acidification","acidification_evidence"},"model-5":{"user_requested_organic_matter","organic_matter_evidence"}}
    def validate(self, plan: DiagnosticPlan, facts: PlanningFacts) -> DiagnosticPlan:
        ids=[t.agent_id for t in plan.tasks]
        if any(x not in self.ALLOWED for x in ids): raise PlanValidationError("agent_not_allowed")
        if len(ids)!=len(set(ids)): raise PlanValidationError("duplicate_agent")
        if not {"model-2","model-3"}.issubset(ids): raise PlanValidationError("core_task_missing")
        task_ids={t.task_id for t in plan.tasks}
        for task in plan.tasks:
            if task.task_id != self.TASK_IDS[task.agent_id]: raise PlanValidationError("unexpected_task_id")
            if any(dep not in task_ids or dep==task.task_id for dep in task.depends_on): raise PlanValidationError("invalid_dependency")
            if task.agent_id in {"model-2","model-3"} and (not task.required or task.trigger.type!="always"): raise PlanValidationError("invalid_core_task")
            if task.agent_id in self.OPTIONAL_PREDICATES and (task.required or task.trigger.type=="always" or not set(task.trigger.predicates).issubset(self.OPTIONAL_PREDICATES[task.agent_id])): raise PlanValidationError("invalid_trigger")
        if ("model-1" in ids) != facts.history_available: raise PlanValidationError("history_plan_mismatch")
        return plan


class DiagnosticPlanner:
    def __init__(self, runner: StructuredRoleRunner, validator: PlanValidator): self._runner,self._validator=runner,validator
    def create_plan(self, *, request: dict, facts: PlanningFacts, capabilities: list[dict]) -> DiagnosticPlan:
        try:
            plan=self._runner.generate(role="planner", prompt=f"{PLANNER_PROMPT.system}\nrequest={request}\nfacts={asdict(facts)}\ncapabilities={capabilities}", schema=DiagnosticPlan)
        except StructuredRoleError:
            plan=self._deterministic_plan(facts)
        return self._validator.validate(plan, facts)

    @staticmethod
    def _deterministic_plan(facts: PlanningFacts) -> DiagnosticPlan:
        tasks = [
            {
                "task_id": "quality-evaluation",
                "agent_id": "model-2",
                "required": True,
                "depends_on": (),
                "trigger": {"type": "always", "predicates": ()},
            },
            {
                "task_id": "problem-diagnosis",
                "agent_id": "model-3",
                "required": True,
                "depends_on": (),
                "trigger": {"type": "always", "predicates": ()},
            },
            {
                "task_id": "acidification-remediation",
                "agent_id": "model-4",
                "required": False,
                "depends_on": ("problem-diagnosis",),
                "trigger": {
                    "type": "any",
                    "predicates": (
                        "user_requested_acidification",
                        "acidification_evidence",
                    ),
                },
            },
            {
                "task_id": "organic-matter-improvement",
                "agent_id": "model-5",
                "required": False,
                "depends_on": ("problem-diagnosis",),
                "trigger": {
                    "type": "any",
                    "predicates": (
                        "user_requested_organic_matter",
                        "organic_matter_evidence",
                    ),
                },
            },
        ]
        if facts.history_available:
            tasks.insert(0, {
                "task_id": "stability-risk",
                "agent_id": "model-1",
                "required": False,
                "depends_on": (),
                "trigger": {
                    "type": "all",
                    "predicates": ("history_available",),
                },
            })
        return DiagnosticPlan.model_validate({
            "plan_version": 1,
            "analysis_mode": "single_parcel_comprehensive",
            "planner_prompt_version": "planner-deterministic-v1",
            "tasks": tasks,
            "planner_reason": "按已注册能力生成固定、可审计的单地块综合诊断计划。",
        })
