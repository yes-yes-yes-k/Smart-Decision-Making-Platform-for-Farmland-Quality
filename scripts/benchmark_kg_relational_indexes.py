"""Build a 10k synthetic intermediate dataset and verify queue index plans."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
from time import perf_counter

from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.migrate_knowledge_graph_platform import (
    ensure_knowledge_graph_platform_schema,
)


DATASET_SIZE = 10_000


def _chunks(values, size=1000):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _explain(connection, sql: str, params: dict, expected_index: str) -> dict:
    plan_rows = connection.execute(
        text(f"EXPLAIN QUERY PLAN {sql}"), params,
    ).all()
    plan = [str(row[-1]) for row in plan_rows]
    started = perf_counter()
    result_count = len(connection.execute(text(sql), params).all())
    elapsed_ms = (perf_counter() - started) * 1000
    return {
        "expected_index": expected_index,
        "used_expected_index": any(expected_index in item for item in plan),
        "plan": plan,
        "result_count": result_count,
        "elapsed_ms": round(elapsed_ms, 3),
    }


def run_benchmark(size: int = DATASET_SIZE) -> dict:
    if size < DATASET_SIZE:
        raise ValueError("the intermediate benchmark requires at least 10,000 rows")
    engine = create_engine("sqlite:///:memory:")
    now = datetime.now(UTC).replace(tzinfo=None)
    now_sql = now.isoformat(sep=" ")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE kb_document (id INTEGER PRIMARY KEY, "
            "doc_name VARCHAR(255), file_path VARCHAR(500), "
            "file_type VARCHAR(20), create_by INTEGER)"
        ))
    ensure_knowledge_graph_platform_schema(engine)

    jobs = []
    relations = []
    events = []
    for index in range(size):
        if index < int(size * 0.7):
            job_state = "pending"
            lease_expires_at = None
        elif index < int(size * 0.9):
            job_state = "running"
            lease_expires_at = (
                now - timedelta(seconds=index % 60)
            ).isoformat(sep=" ")
        else:
            job_state = "completed"
            lease_expires_at = None
        jobs.append({
            "document_id": 1,
            "content_sha256": f"{index:064x}",
            "schema_version": "synthetic-schema-v1",
            "backend_name": "synthetic-backend",
            "extractor_version": "1.0.0",
            "backend_config_digest": "b" * 64,
            "state": job_state,
            "priority": index % 10,
            "attempt_count": 0,
            "max_attempts": 5,
            "available_at": (
                now - timedelta(seconds=index % 120)
            ).isoformat(sep=" "),
            "lease_expires_at": lease_expires_at,
            "retryable": False,
            "created_at": now_sql,
            "updated_at": now_sql,
        })
        relations.append({
            "job_id": index + 1,
            "candidate_key": f"synthetic-relation-{index}",
            "relation_type": "addresses" if index % 2 else "improves_indicator",
            "source_candidate_id": index * 2 + 1,
            "target_candidate_id": index * 2 + 2,
            "risk_level": "new_fact" if index % 3 else "evidence_append",
            "validation_status": "valid",
            "review_status": "pending" if index < int(size * 0.8) else "approved",
            "confidence": 0.0,
            "support_document_count": 1,
            "created_at": now_sql,
            "updated_at": now_sql,
        })
        events.append({
            "event_key": f"synthetic-event-{index}",
            "event_type": "knowledge_document_indexed",
            "aggregate_type": "kb_document",
            "aggregate_id": str(index + 1),
            "payload": json.dumps({"synthetic": True, "index": index}),
            "state": "pending" if index < int(size * 0.9) else "published",
            "attempt_count": 0,
            "available_at": (
                now - timedelta(seconds=index % 120)
            ).isoformat(sep=" "),
            "created_at": now_sql,
            "updated_at": now_sql,
        })

    with engine.begin() as connection:
        for chunk in _chunks(jobs):
            connection.execute(text(
                "INSERT INTO kg_extraction_job "
                "(document_id, content_sha256, schema_version, backend_name, "
                "extractor_version, backend_config_digest, state, priority, "
                "attempt_count, max_attempts, available_at, lease_expires_at, "
                "retryable, created_at, updated_at) VALUES "
                "(:document_id, :content_sha256, :schema_version, :backend_name, "
                ":extractor_version, :backend_config_digest, :state, :priority, "
                ":attempt_count, :max_attempts, :available_at, :lease_expires_at, "
                ":retryable, :created_at, :updated_at)"
            ), chunk)
        for chunk in _chunks(relations):
            connection.execute(text(
                "INSERT INTO kg_relation_candidate "
                "(job_id, candidate_key, relation_type, source_candidate_id, "
                "target_candidate_id, risk_level, validation_status, review_status, "
                "confidence, support_document_count, created_at, updated_at) VALUES "
                "(:job_id, :candidate_key, :relation_type, :source_candidate_id, "
                ":target_candidate_id, :risk_level, :validation_status, :review_status, "
                ":confidence, :support_document_count, :created_at, :updated_at)"
            ), chunk)
        for chunk in _chunks(events):
            connection.execute(text(
                "INSERT INTO kg_outbox_event "
                "(event_key, event_type, aggregate_type, aggregate_id, payload, "
                "state, attempt_count, available_at, created_at, updated_at) VALUES "
                "(:event_key, :event_type, :aggregate_type, :aggregate_id, :payload, "
                ":state, :attempt_count, :available_at, :created_at, :updated_at)"
            ), chunk)

    queries = {}
    with engine.connect() as connection:
        queries["claim_pending_jobs"] = _explain(
            connection,
            "SELECT id FROM kg_extraction_job "
            "WHERE state IN ('pending', 'retry') AND available_at <= :now "
            "ORDER BY priority DESC, available_at, id LIMIT 100",
            {"now": now_sql},
            "idx_kg_job_claim",
        )
        queries["reclaim_expired_leases"] = _explain(
            connection,
            "SELECT id FROM kg_extraction_job "
            "WHERE state = 'running' AND lease_expires_at <= :now "
            "ORDER BY lease_expires_at, id LIMIT 100",
            {"now": now_sql},
            "idx_kg_job_lease_reclaim",
        )
        queries["pending_relation_review"] = _explain(
            connection,
            "SELECT id FROM kg_relation_candidate WHERE review_status = 'pending' "
            "ORDER BY risk_level, relation_type, id LIMIT 100",
            {},
            "idx_kg_relation_pending_review",
        )
        queries["claim_outbox"] = _explain(
            connection,
            "SELECT id FROM kg_outbox_event "
            "WHERE state IN ('pending', 'retry') AND available_at <= :now "
            "ORDER BY available_at, id LIMIT 100",
            {"now": now_sql},
            "idx_kg_outbox_claim",
        )
    passed = all(item["used_expected_index"] for item in queries.values())
    engine.dispose()
    return {
        "schema": "knowledge-platform-relational-index-benchmark-v1",
        "synthetic_only": True,
        "database": "sqlite-in-memory",
        "generated_at": datetime.now(UTC).isoformat(),
        "rows": {
            "kg_extraction_job": size,
            "kg_relation_candidate": size,
            "kg_outbox_event": size,
        },
        "queries": queries,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=DATASET_SIZE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_benchmark(args.size)
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8", newline="\n")
    print(output, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
