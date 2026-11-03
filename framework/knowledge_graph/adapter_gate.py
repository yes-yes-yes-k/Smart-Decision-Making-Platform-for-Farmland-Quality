"""Production gate for extraction adapter selection."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def _identity(name: Any, version: Any) -> str:
    return f"{str(name or '').strip()}@{str(version or '').strip()}"


def evaluate_adapter_policy(
    policy: Mapping[str, Any],
    evaluations: Sequence[Mapping[str, Any]],
    conformance: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Require exact-version live evaluation, conformance and explicit approval."""
    evaluation_by_id = {
        _identity((item.get("backend") or {}).get("name"), (item.get("backend") or {}).get("version")): item
        for item in evaluations
        if isinstance(item.get("backend"), Mapping)
    }
    conformance_by_id = {
        _identity(item.get("backend_name"), item.get("backend_version")): item
        for item in conformance
    }
    blockers: list[str] = []
    decisions: list[dict[str, Any]] = []
    selected: dict[str, str | None] = {"primary": None, "fallback": None}
    candidates = policy.get("candidates") if isinstance(policy.get("candidates"), list) else []

    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            blockers.append("invalid_candidate")
            continue
        name = candidate.get("name")
        version = candidate.get("version")
        role = candidate.get("role")
        key = _identity(name, version)
        candidate_blockers: list[str] = []
        if not name or not version or str(version).casefold() == "latest":
            candidate_blockers.append("exact_version_required")
        if role not in {"primary", "fallback"}:
            candidate_blockers.append("invalid_role")

        report = evaluation_by_id.get(key)
        if report is None or report.get("status") != "completed":
            candidate_blockers.append("live_gold_evaluation_required")
        elif report.get("evaluation_mode") != "live_backend_predictions":
            candidate_blockers.append("live_prediction_provenance_required")
        else:
            thresholds = candidate.get("minimum_metrics") or {}
            metrics = report.get("metrics") if isinstance(report.get("metrics"), Mapping) else {}
            for metric_path, minimum in thresholds.items():
                group, _, field = str(metric_path).partition(".")
                value = (metrics.get(group) or {}).get(field) if isinstance(metrics.get(group), Mapping) else None
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value < minimum:
                    candidate_blockers.append(f"metric_below_threshold:{metric_path}")

        conformance_report = conformance_by_id.get(key)
        if conformance_report is None or conformance_report.get("passed") is not True:
            candidate_blockers.append("conformance_required")
        if candidate.get("approved") is not True:
            candidate_blockers.append("explicit_approval_required")

        eligible = not candidate_blockers
        if eligible and role in selected:
            if selected[role] is not None:
                candidate_blockers.append("duplicate_role_selection")
                eligible = False
            else:
                selected[role] = key
        blockers.extend(f"{key}:{item}" for item in candidate_blockers)
        decisions.append({
            "adapter": key, "role": role, "eligible": eligible,
            "blockers": candidate_blockers,
        })

    if selected["primary"] is None:
        blockers.append("primary_adapter_not_selected")
    if selected["fallback"] is None:
        blockers.append("fallback_adapter_not_selected")
    unique_blockers = list(dict.fromkeys(blockers))
    ready = not unique_blockers and policy.get("status") == "approved"
    if policy.get("status") != "approved":
        unique_blockers.append("policy_not_approved")
    return {
        "schema": "knowledge-graph-adapter-gate-v1",
        "policy_version": policy.get("policy_version"),
        "production_ready": ready,
        "selected": selected if ready else {"primary": None, "fallback": None},
        "decisions": decisions,
        "blockers": unique_blockers,
    }
