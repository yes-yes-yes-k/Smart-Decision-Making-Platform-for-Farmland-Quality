"""Machine-readable acceptance gate for the full knowledge-platform benchmark."""
from __future__ import annotations

from typing import Any, Mapping


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def evaluate_capacity_run(
    target: Mapping[str, Any], run: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate one benchmark report without inferring or filling missing evidence."""
    blockers: list[str] = []
    required_metadata = tuple(target.get("run_metadata_required") or ())
    metadata = run.get("metadata") if isinstance(run.get("metadata"), Mapping) else {}
    for field in required_metadata:
        if metadata.get(field) in (None, "", [], {}):
            blockers.append(f"missing_metadata:{field}")

    if run.get("status") != "completed":
        blockers.append("run_not_completed")
    if run.get("synthetic_only") is not True:
        blockers.append("synthetic_isolation_unverified")

    expected_counts = target.get("capacity") if isinstance(target.get("capacity"), Mapping) else {}
    actual_counts = run.get("counts") if isinstance(run.get("counts"), Mapping) else {}
    count_mapping = {
        "source_documents": "source_documents",
        "canonical_entities": "canonical_entities",
        "relation_evidence": "relation_evidence",
        "queued_jobs": "queued_jobs",
    }
    for target_key, run_key in count_mapping.items():
        expected = _number(expected_counts.get(target_key))
        actual = _number(actual_counts.get(run_key))
        if expected is None or actual is None or actual < expected:
            blockers.append(f"capacity_not_met:{target_key}")

    query_target = target.get("query_profile") if isinstance(target.get("query_profile"), Mapping) else {}
    query = run.get("query") if isinstance(run.get("query"), Mapping) else {}
    p95 = _number(query.get("p95_ms"))
    p95_limit = _number(query_target.get("p95_ms_max"))
    if p95 is None or p95_limit is None or p95 > p95_limit:
        blockers.append("query_p95_exceeded_or_missing")
    if query.get("max_hops") != query_target.get("max_hops"):
        blockers.append("query_hop_profile_mismatch")
    if query.get("top_k") != query_target.get("top_k"):
        blockers.append("query_top_k_profile_mismatch")
    if query.get("single_document_full_graph_scan") is not False:
        blockers.append("single_document_update_scan_unverified")

    release_target = target.get("release_profile") if isinstance(target.get("release_profile"), Mapping) else {}
    release = run.get("release") if isinstance(run.get("release"), Mapping) else {}
    for metric, limit_key in (
        ("activate_seconds", "activate_seconds_max"),
        ("rollback_seconds", "rollback_seconds_max"),
    ):
        value = _number(release.get(metric))
        limit = _number(release_target.get(limit_key))
        if value is None or limit is None or value > limit:
            blockers.append(f"release_slo_failed:{metric}")
    if release_target.get("vector_retrieval_must_remain_available") is True and (
        release.get("vector_retrieval_available") is not True
    ):
        blockers.append("vector_retrieval_availability_unverified")

    jobs = run.get("jobs") if isinstance(run.get("jobs"), Mapping) else {}
    unique = _number(jobs.get("unique_jobs"))
    terminal = sum(
        _number(jobs.get(key)) or 0
        for key in ("succeeded", "failed", "dead_letter")
    )
    if unique is None or unique < (_number(expected_counts.get("queued_jobs")) or 0):
        blockers.append("job_scale_not_met")
    if unique is None or terminal != unique:
        blockers.append("job_count_not_conserved")
    if (_number(jobs.get("duplicate_business_effects")) or 0) != 0:
        blockers.append("duplicate_business_effects")
    if jobs.get("duplicate_delivery_tested") is not True:
        blockers.append("duplicate_delivery_unverified")
    if jobs.get("worker_restart_tested") is not True:
        blockers.append("worker_restart_unverified")
    if jobs.get("production_eligible") is not True:
        blockers.append("job_benchmark_not_production_eligible")

    restore = run.get("backup_restore") if isinstance(run.get("backup_restore"), Mapping) else {}
    if restore.get("passed") is not True:
        blockers.append("backup_restore_unverified")

    unique_blockers = list(dict.fromkeys(blockers))
    passed = not unique_blockers
    return {
        "schema": "knowledge-platform-capacity-acceptance-v1",
        "target_version": target.get("benchmark_version"),
        "run_id": run.get("run_id"),
        "passed": passed,
        "eligible_for_age_primary": passed,
        "blockers": unique_blockers,
    }
