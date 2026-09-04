"""Deterministic contract-only data factories for comprehensive workflow tests."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from framework.agents.workflows.comprehensive.contracts import (
    DiagnosticPlan,
    EvidenceBundle,
    EvidenceItem,
    InputResolution,
    ReportPayload,
    ReportSection,
    ResolvedValue,
    TaskResult,
)


def make_valid_plan_payload(*, history: bool = False) -> dict[str, Any]:
    tasks = [
        {"task_id": "quality-evaluation", "agent_id": "model-2",
         "required": True, "depends_on": (),
         "trigger": {"type": "always", "predicates": ()}},
        {"task_id": "problem-diagnosis", "agent_id": "model-3",
         "required": True, "depends_on": (),
         "trigger": {"type": "always", "predicates": ()}},
        {"task_id": "acidification-remediation", "agent_id": "model-4",
         "required": False,
         "depends_on": ("problem-diagnosis",),
         "trigger": {"type": "any", "predicates": (
             "user_requested_acidification", "acidification_evidence")}},
        {"task_id": "organic-matter-improvement", "agent_id": "model-5",
         "required": False,
         "depends_on": ("problem-diagnosis",),
         "trigger": {"type": "any", "predicates": (
             "user_requested_organic_matter", "organic_matter_evidence")}},
    ]
    if history:
        tasks.insert(0, {
            "task_id": "stability-risk", "agent_id": "model-1",
            "required": False, "depends_on": (),
            "trigger": {"type": "all", "predicates": ("history_available",)},
        })
    return {
        "plan_version": 1,
        "analysis_mode": "single_parcel_comprehensive",
        "planner_prompt_version": "planner-v1",
        "tasks": tasks,
        "planner_reason": "固定综合诊断计划",
    }


def valid_plan(*, history: bool = False) -> DiagnosticPlan:
    return DiagnosticPlan.model_validate(make_valid_plan_payload(history=history))


def plan_without(agent_id: str) -> DiagnosticPlan:
    payload = make_valid_plan_payload(history=agent_id != "model-1")
    payload["tasks"] = [t for t in payload["tasks"] if t["agent_id"] != agent_id]
    return DiagnosticPlan.model_validate(payload)


def parcel_context(parcel_id: str = "P001", *, version: int = 4) -> dict[str, Any]:
    return {"object": {"type": "parcel", "id": parcel_id,
                       "display_name": "示例地块"},
            "version": version, "mode": "spatial"}


def verified_execution_context(parcel_id: str = "P001") -> dict[str, Any]:
    return {"analysis_context": parcel_context(parcel_id),
            "verified": True, "trace_id": "trace-1"}


def complete_resolution() -> InputResolution:
    values = {
        "parcel_id": ResolvedValue(value="P001", source="parcel_db",
                                   source_version="parcel:4"),
        "soil_ph": ResolvedValue(value=5.2, unit="pH", source="parcel_db",
                                 source_version="sample:9"),
    }
    return InputResolution(
        task_arguments={task.task_id: {"parcel_id": "P001", "soil_ph": 5.2}
                        for task in valid_plan().tasks},
        resolved_values=values, object_version=4,
    )


def successful_model2_result(*, composite_index: float = 0.734) -> TaskResult:
    return TaskResult(
        task_id="quality-evaluation", agent_id="model-2", status="succeeded",
        payload={"composite_index": composite_index, "quality_grade": "Ⅱ"},
        key_inputs={"parcel_id": "P001"}, model_version="model-2-v1",
        data_as_of="2026-08-31", data_version="sample:9",
        calculated_at="2026-09-01T00:00:00+00:00", trace_id="trace-1",
    )


def validated_results(*, composite_index: float = 0.734) -> dict[str, TaskResult]:
    return {"quality-evaluation": successful_model2_result(
        composite_index=composite_index)}


def valid_evidence() -> EvidenceBundle:
    return EvidenceBundle(items=(EvidenceItem(
        source_id="doc-1:0:1", doc_name="改良手册", chunk_index=0, page=1,
        claim_ids=("claim-1",), score=0.93,
    ),))


def report_payload(*, prose_template: str, fact_refs: tuple[str, ...]) -> ReportPayload:
    titles = {
        "object-summary": "分析对象",
        "execution-summary": "执行摘要",
        "quality": "质量评价",
        "obstacles": "障碍诊断",
        "conditional-specialty-results": "条件专项结果",
        "priority-remediation": "优先改良措施",
        "limitations": "限制与降级",
        "provenance": "数据与模型溯源",
    }
    return ReportPayload(
        title="单地块综合诊断与改良报告",
        sections=tuple(
            ReportSection(
                section_id=section_id,
                title=title,
                prose_template=(
                    prose_template if section_id == "quality" else "已验证内容。"
                ),
                fact_refs=fact_refs if section_id == "quality" else (),
                claim_ids=("claim-1",) if section_id == "quality" else (),
                source_ids=("doc-1:0:1",) if section_id == "quality" else (),
            )
            for section_id, title in titles.items()
        ),
        degradations=(), prompt_version="reporter-v1",
    )


def replace_agent(plan: DiagnosticPlan, old: str, new: str) -> DiagnosticPlan:
    payload = plan.model_dump(mode="python")
    for task in payload["tasks"]:
        if task["agent_id"] == old:
            task["agent_id"] = new
    return DiagnosticPlan.model_validate(payload)


def make_model4_always(plan: DiagnosticPlan) -> DiagnosticPlan:
    payload = deepcopy(plan.model_dump(mode="python"))
    for task in payload["tasks"]:
        if task["agent_id"] == "model-4":
            task["trigger"] = {"type": "always", "predicates": ()}
    return DiagnosticPlan.model_validate(payload)
