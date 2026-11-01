"""Invalidate document-bound evidence without silently deleting production facts."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import inspect

from framework.models.knowledge_graph import (
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphClaimEvidence,
    KnowledgeGraphRelationCandidate,
    KnowledgeGraphRelationRetirementCandidate,
)


def invalidate_document_evidence(
    session, *, document_id: int, reason: str,
    keep_content_sha256: str | None = None,
) -> dict[str, int]:
    """Invalidate evidence for a withdrawal or every stale hash after reparse."""
    empty = {
        "relation_evidence_invalidated": 0,
        "claim_evidence_invalidated": 0,
        "relations_recounted": 0,
        "retirement_candidates_created": 0,
    }
    if not inspect(session.get_bind()).has_table("kg_candidate_evidence"):
        return empty
    now = datetime.now(UTC).replace(tzinfo=None)
    relation_query = session.query(KnowledgeGraphCandidateEvidence).filter_by(
        document_id=document_id, is_active=True,
    )
    claim_query = session.query(KnowledgeGraphClaimEvidence).filter_by(
        document_id=document_id, is_active=True,
    )
    if keep_content_sha256 is not None:
        relation_query = relation_query.filter(
            KnowledgeGraphCandidateEvidence.content_sha256 != keep_content_sha256,
        )
        claim_query = claim_query.filter(
            KnowledgeGraphClaimEvidence.content_sha256 != keep_content_sha256,
        )
    relation_evidence = relation_query.all()
    claim_evidence = claim_query.all()
    affected_relations = {row.relation_candidate_id for row in relation_evidence}
    for row in (*relation_evidence, *claim_evidence):
        row.is_active = False
        row.invalidated_at = now
        row.invalidation_reason = str(reason)[:255]

    retirement_count = 0
    for relation_id in sorted(affected_relations):
        relation = session.get(KnowledgeGraphRelationCandidate, relation_id)
        if relation is None:
            continue
        remaining = session.query(KnowledgeGraphCandidateEvidence).filter_by(
            relation_candidate_id=relation_id, is_active=True,
        ).all()
        relation.support_document_count = len({row.document_id for row in remaining})
        if remaining:
            continue
        pending = session.query(KnowledgeGraphRelationRetirementCandidate).filter_by(
            relation_candidate_id=relation_id, review_status="pending",
        ).one_or_none()
        if pending is None:
            relation_key = "|".join((
                relation.relation_type, str(relation.canonical_source_id or ""),
                str(relation.canonical_target_id or ""),
            ))
            session.add(KnowledgeGraphRelationRetirementCandidate(
                relation_candidate_id=relation_id, relation_key=relation_key,
                relation_snapshot={
                    "type": relation.relation_type,
                    "source": relation.canonical_source_id,
                    "target": relation.canonical_target_id,
                    "candidate_id": relation.id,
                },
                trigger_document_id=document_id, reason=str(reason)[:255],
                active_evidence_count=0,
            ))
            retirement_count += 1
    session.flush()
    return {
        "relation_evidence_invalidated": len(relation_evidence),
        "claim_evidence_invalidated": len(claim_evidence),
        "relations_recounted": len(affected_relations),
        "retirement_candidates_created": retirement_count,
    }
