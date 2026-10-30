from __future__ import annotations

import json
from pathlib import Path

from framework.knowledge_graph.capacity_gate import evaluate_capacity_run


ROOT = Path(__file__).resolve().parents[1]


def _target():
    return json.loads((
        ROOT / "benchmarks" / "knowledge_platform" / "target-v1.json"
    ).read_text(encoding="utf-8"))


def _passing_run():
    target = _target()
    return {
        "run_id": "synthetic-full-1",
        "status": "completed",
        "synthetic_only": True,
        "metadata": {field: "recorded" for field in target["run_metadata_required"]},
        "counts": {
            "source_documents": 100_000,
            "canonical_entities": 100_000,
            "relation_evidence": 1_000_000,
            "queued_jobs": 100_000,
        },
        "query": {
            "p95_ms": 999.0, "max_hops": 2, "top_k": 100,
            "single_document_full_graph_scan": False,
        },
        "release": {
            "activate_seconds": 59.0, "rollback_seconds": 59.0,
            "vector_retrieval_available": True,
        },
        "jobs": {
            "unique_jobs": 100_000, "succeeded": 99_000,
            "failed": 900, "dead_letter": 100,
            "duplicate_business_effects": 0,
            "duplicate_delivery_tested": True, "worker_restart_tested": True,
            "production_eligible": True,
        },
        "backup_restore": {"passed": True},
    }


def test_full_capacity_report_passes_only_when_every_gate_has_evidence():
    result = evaluate_capacity_run(_target(), _passing_run())

    assert result["passed"] is True
    assert result["eligible_for_age_primary"] is True
    assert result["blockers"] == []


def test_missing_or_failed_evidence_blocks_age_primary():
    run = _passing_run()
    run["metadata"].pop("apache_age_version")
    run["query"]["p95_ms"] = 1001
    run["jobs"]["succeeded"] -= 1
    run["jobs"]["duplicate_business_effects"] = 1
    run["backup_restore"]["passed"] = False

    result = evaluate_capacity_run(_target(), run)

    assert result["passed"] is False
    assert result["eligible_for_age_primary"] is False
    assert set(result["blockers"]) >= {
        "missing_metadata:apache_age_version",
        "query_p95_exceeded_or_missing",
        "job_count_not_conserved",
        "duplicate_business_effects",
        "backup_restore_unverified",
    }


def test_boolean_counts_are_not_accepted_as_benchmark_numbers():
    run = _passing_run()
    run["counts"]["source_documents"] = True

    result = evaluate_capacity_run(_target(), run)

    assert "capacity_not_met:source_documents" in result["blockers"]
