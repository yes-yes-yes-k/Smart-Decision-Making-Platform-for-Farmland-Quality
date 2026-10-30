"""Sanitized operational metrics and alert conditions for graph governance."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, inspect, select

from framework.models.knowledge_graph import (
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphControl,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphRelationCandidate,
    KnowledgeGraphRelease,
    KnowledgeGraphReviewDecision,
    KnowledgeGraphRollbackAudit,
)


def snapshot_graph_governance_metrics(session, *, now=None, thresholds=None) -> dict:
    now = now or datetime.now(UTC).replace(tzinfo=None)
    thresholds = {
        "pending_jobs": 10_000, "failed_rate": 0.1,
        "expired_leases": 0, "pending_reviews": 5_000,
        "evidence_free_relations": 0,
        **(thresholds or {}),
    }
    if not inspect(session.get_bind()).has_table("kg_extraction_job"):
        return {"ready": False, "alerts": ["graph_schema_missing"]}
    job_states = dict(session.query(
        KnowledgeGraphExtractionJob.state, func.count(KnowledgeGraphExtractionJob.id),
    ).group_by(KnowledgeGraphExtractionJob.state).all())
    hour_ago = now - timedelta(hours=1)
    completed_hour = session.query(KnowledgeGraphExtractionJob).filter(
        KnowledgeGraphExtractionJob.finished_at >= hour_ago,
        KnowledgeGraphExtractionJob.state == "completed",
    ).count()
    failed_hour = session.query(KnowledgeGraphExtractionJob).filter(
        KnowledgeGraphExtractionJob.finished_at >= hour_ago,
        KnowledgeGraphExtractionJob.state == "dead_letter",
    ).count()
    terminal = completed_hour + failed_hour
    expired_leases = session.query(KnowledgeGraphExtractionJob).filter(
        KnowledgeGraphExtractionJob.state == "running",
        KnowledgeGraphExtractionJob.lease_expires_at < now,
    ).count()
    pending_risk = dict(session.query(
        KnowledgeGraphRelationCandidate.risk_level,
        func.count(KnowledgeGraphRelationCandidate.id),
    ).filter(
        KnowledgeGraphRelationCandidate.review_status.in_(("pending", "blocked")),
    ).group_by(KnowledgeGraphRelationCandidate.risk_level).all())
    pending_entities = session.query(KnowledgeGraphEntityCandidate).filter(
        KnowledgeGraphEntityCandidate.review_status.in_(("pending", "blocked")),
    ).count()
    pending_relations = sum(int(value) for value in pending_risk.values())
    oldest_rows = []
    for model in (KnowledgeGraphEntityCandidate, KnowledgeGraphRelationCandidate):
        value = session.query(func.min(model.created_at)).filter(
            model.review_status.in_(("pending", "blocked")),
        ).scalar()
        if value:
            oldest_rows.append(value)
    oldest_pending_seconds = max(
        (now - value).total_seconds() for value in oldest_rows
    ) if oldest_rows else 0.0
    reviewed_hour = session.query(KnowledgeGraphReviewDecision).filter(
        KnowledgeGraphReviewDecision.created_at >= hour_ago,
    ).count()
    active_evidence = select(
        KnowledgeGraphCandidateEvidence.relation_candidate_id,
    ).where(KnowledgeGraphCandidateEvidence.is_active.is_(True)).distinct()
    evidence_free = session.query(KnowledgeGraphRelationCandidate).filter(
        KnowledgeGraphRelationCandidate.review_status == "approved",
        ~KnowledgeGraphRelationCandidate.id.in_(active_evidence),
    ).count()
    control = session.get(KnowledgeGraphControl, "active")
    latest_release = KnowledgeGraphRelease.query.order_by(
        KnowledgeGraphRelease.sequence_no.desc(),
    ).first()
    latest_rollback = KnowledgeGraphRollbackAudit.query.order_by(
        KnowledgeGraphRollbackAudit.id.desc(),
    ).first()
    failed_rate = failed_hour / terminal if terminal else 0.0
    pending_jobs = int(job_states.get("pending", 0)) + int(job_states.get("retry", 0))
    pending_reviews = pending_entities + pending_relations
    alert_values = {
        "pending_jobs_high": pending_jobs > thresholds["pending_jobs"],
        "job_failure_rate_high": failed_rate > thresholds["failed_rate"],
        "expired_leases_present": expired_leases > thresholds["expired_leases"],
        "review_backlog_high": pending_reviews > thresholds["pending_reviews"],
        "evidence_free_relations_present": evidence_free > thresholds["evidence_free_relations"],
    }
    return {
        "ready": True,
        "jobs": {
            "states": job_states, "completed_last_hour": completed_hour,
            "failed_last_hour": failed_hour, "failure_rate_last_hour": round(failed_rate, 6),
            "pending": pending_jobs, "expired_leases": expired_leases,
        },
        "reviews": {
            "pending_entities": pending_entities, "pending_relations": pending_relations,
            "pending_relation_risk": pending_risk,
            "oldest_pending_seconds": round(oldest_pending_seconds, 3),
            "decisions_last_hour": reviewed_hour,
        },
        "graph_quality": {"approved_relations_without_active_evidence": evidence_free},
        "release": {
            "active_release_id": control.active_release_id if control else None,
            "latest_diff_summary": latest_release.diff_summary if latest_release else None,
            "latest_release_state": latest_release.state if latest_release else None,
        },
        "rollback": {
            "source_release_id": latest_rollback.source_release_id if latest_rollback else None,
            "target_release_id": latest_rollback.target_release_id if latest_rollback else None,
            "duration_ms": latest_rollback.duration_ms if latest_rollback else None,
            "occurred_at": latest_rollback.created_at.isoformat() if latest_rollback else None,
        },
        "alerts": [key for key, active in alert_values.items() if active],
        "thresholds": thresholds,
    }
