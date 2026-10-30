from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.knowledge_graph.capacity_report import (
    CapacityReportError,
    compose_capacity_report,
)


ROOT = Path(__file__).resolve().parents[1]


def _target():
    return json.loads((
        ROOT / "benchmarks" / "knowledge_platform" / "target-v1.json"
    ).read_text(encoding="utf-8"))


def _reports():
    target = _target()
    metadata = {field: "recorded" for field in target["run_metadata_required"]}
    load = {
        "schema": "knowledge-platform-synthetic-age-load-v1", "status": "completed",
        "synthetic_only": True,
        "counts": {
            "documents": 100_000, "entities": 100_000, "relations": 100_000,
            "evidence": 1_000_000, "jobs": 100_000,
        },
    }
    runtime = {
        "schema": "knowledge-platform-age-runtime-benchmark-v1", "status": "completed",
        "query": {
            "p95_ms": 900, "max_hops": 2, "top_k": 100,
            "single_document_full_graph_scan": False,
        },
        "release": {
            "activate_seconds": 20, "rollback_seconds": 15,
        },
    }
    jobs = {
        "schema": "knowledge-platform-job-conservation-v1", "status": "completed",
        "unique_jobs": 100_000, "succeeded": 99_900, "failed": 0,
        "dead_letter": 100, "duplicate_business_effects": 0,
        "duplicate_delivery_tested": True, "worker_restart_tested": True,
        "production_eligible": True,
    }
    vector = {
        "schema": "knowledge-platform-vector-availability-v1",
        "available_during_graph_failures": True,
    }
    backup = {
        "schema": "knowledge-platform-backup-restore-verification-v1",
        "passed": True,
    }
    return target, metadata, load, runtime, jobs, vector, backup


def test_five_real_evidence_reports_compose_to_passing_capacity_run():
    target, metadata, load, runtime, jobs, vector, backup = _reports()

    report = compose_capacity_report(
        target=target, metadata=metadata, load_report=load,
        runtime_report=runtime, job_report=jobs, vector_report=vector,
        backup_report=backup, run_id="synthetic-full-v1",
    )

    assert report["acceptance"]["passed"] is True
    assert report["acceptance"]["eligible_for_age_primary"] is True
    assert len(report["source_reports"]) == 5


def test_composed_report_preserves_blockers_instead_of_filling_missing_evidence():
    target, metadata, load, runtime, jobs, vector, backup = _reports()
    runtime["query"].pop("p95_ms")
    vector["available_during_graph_failures"] = False

    report = compose_capacity_report(
        target=target, metadata=metadata, load_report=load,
        runtime_report=runtime, job_report=jobs, vector_report=vector,
        backup_report=backup, run_id="synthetic-blocked-v1",
    )

    assert report["acceptance"]["passed"] is False
    assert set(report["acceptance"]["blockers"]) >= {
        "query_p95_exceeded_or_missing",
        "vector_retrieval_availability_unverified",
    }


def test_source_report_must_explicitly_declare_completed_status():
    target, metadata, load, runtime, jobs, vector, backup = _reports()
    load.pop("status")

    with pytest.raises(CapacityReportError, match="AGE load report"):
        compose_capacity_report(
            target=target, metadata=metadata, load_report=load,
            runtime_report=runtime, job_report=jobs, vector_report=vector,
            backup_report=backup, run_id="synthetic-missing-status-v1",
        )
