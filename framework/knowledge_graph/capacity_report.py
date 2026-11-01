"""Composition of independently measured capacity evidence into one run report."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from .capacity_gate import evaluate_capacity_run
from .contracts import stable_digest


class CapacityReportError(ValueError):
    pass


def _require(report: Mapping[str, Any], schema: str, label: str) -> None:
    if report.get("schema") != schema or report.get("status") != "completed":
        raise CapacityReportError(f"invalid or incomplete {label} report")


def compose_capacity_report(
    *,
    target: Mapping[str, Any],
    metadata: Mapping[str, Any],
    load_report: Mapping[str, Any],
    runtime_report: Mapping[str, Any],
    job_report: Mapping[str, Any],
    vector_report: Mapping[str, Any],
    backup_report: Mapping[str, Any],
    run_id: str,
) -> dict[str, Any]:
    if not run_id:
        raise CapacityReportError("run_id is required")
    _require(
        load_report, "knowledge-platform-synthetic-age-load-v1", "AGE load",
    )
    _require(
        runtime_report, "knowledge-platform-age-runtime-benchmark-v1", "AGE runtime",
    )
    _require(
        job_report, "knowledge-platform-job-conservation-v1", "job conservation",
    )
    if vector_report.get("schema") != "knowledge-platform-vector-availability-v1":
        raise CapacityReportError("invalid vector availability report")
    if backup_report.get("schema") not in {
        "knowledge-platform-backup-restore-verification-v1",
        "postgres-age-restore-verification-v1",
    }:
        raise CapacityReportError("invalid backup/restore report")

    counts = load_report.get("counts") if isinstance(load_report.get("counts"), Mapping) else {}
    query = dict(runtime_report.get("query") or {})
    release = dict(runtime_report.get("release") or {})
    release["vector_retrieval_available"] = (
        vector_report.get("available_during_graph_failures") is True
    )
    report = {
        "schema": "knowledge-platform-capacity-run-v1",
        "run_id": run_id,
        "status": "completed",
        "synthetic_only": load_report.get("synthetic_only") is True,
        "metadata": dict(metadata),
        "counts": {
            "source_documents": counts.get("documents"),
            "canonical_entities": counts.get("entities"),
            "relation_evidence": counts.get("evidence"),
            "queued_jobs": counts.get("jobs"),
            "relations": counts.get("relations"),
        },
        "query": query,
        "release": release,
        "jobs": dict(job_report),
        "backup_restore": dict(backup_report),
        "source_reports": {
            "load": stable_digest(load_report),
            "runtime": stable_digest(runtime_report),
            "jobs": stable_digest(job_report),
            "vector": stable_digest(vector_report),
            "backup_restore": stable_digest(backup_report),
        },
        "composed_at": datetime.now(UTC).isoformat(),
    }
    report["acceptance"] = evaluate_capacity_run(target, report)
    return report
