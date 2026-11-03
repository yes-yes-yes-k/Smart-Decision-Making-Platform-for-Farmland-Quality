"""Read pending KG candidates with shared source/permission checks.

R2.6c read side. Candidates are returned in their ``pending`` review state —
they never pass through the publish API. When the live document version no
longer matches the extraction job's ``content_sha256``, the reader returns
``status='invalidated'`` instead of silently dropping the candidates.
"""
from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import text

from framework.models.knowledge_graph import (
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphClaimCandidate,
    KnowledgeGraphClaimEvidence,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphRelationCandidate,
    KnowledgeGraphStudyCandidate,
)
from framework.models.user import db

# Document kinds eligible for research-evidence extraction.
ELIGIBLE_KINDS = frozenset({"academic_paper", "standard", "policy", "method_guideline"})


def _live_source_from_kb_document(document_id: int) -> Mapping[str, Any] | None:
    """Read the live document metadata directly from ``kb_document``.

    Mirrors the field projection used by
    :class:`PublishedResearchSources` so the same eligibility rules apply
    without requiring the read-only adapter to be wired up.
    """
    row = db.session.execute(text(
        "SELECT id, file_hash, review_status, visibility_scope, "
        "document_kind, status, processing_stage, chunk_count "
        "FROM kb_document WHERE id = :doc_id"
    ), {"doc_id": document_id}).mappings().first()
    if row is None:
        return None
    completed = (
        row["status"] == 1
        and row["processing_stage"] == "completed"
        and row["document_kind"] in ELIGIBLE_KINDS
        and (row["chunk_count"] or 0) > 0
    )
    return {
        "document_id": row["id"],
        "content_sha256": row["file_hash"],
        "review_status": row["review_status"],
        "visibility_scope": row["visibility_scope"],
        "document_kind": row["document_kind"],
        "completed": completed,
    }


def _source_eligible(live: Mapping[str, Any]) -> bool:
    """Shared baseline check: public, approved, eligible kind, completed."""
    return bool(
        live
        and live.get("completed")
        and live.get("visibility_scope") == "public"
        and live.get("review_status") == "approved"
        and live.get("document_kind") in ELIGIBLE_KINDS
    )


def _serialize_evidence(row) -> dict[str, Any]:
    return {
        "evidence_key": row.evidence_key,
        "chunk_index": row.chunk_index,
        "page": row.page,
        "span_start": row.span_start,
        "span_end": row.span_end,
        "quote": row.quote,
        "quote_sha256": row.quote_sha256,
        "is_active": row.is_active,
        "review_status": row.review_status,
    }


def read_candidates(
    document_id: int,
    *,
    live_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read pending candidates for ``document_id``.

    Parameters
    ----------
    document_id:
        The live ``kb_document`` id to read candidates for.
    live_source:
        Optional pre-resolved source metadata. When omitted the reader
        queries ``kb_document`` directly. Callers that already hold a
        :class:`PublishedResearchSources` result should pass it here to
        avoid a second lookup.

    Returns
    -------
    dict
        ``status`` is one of:

        * ``"ok"`` — source eligible and version matches; candidates returned.
        * ``"ineligible"`` — source failed the public/approved/kind check;
          no candidates returned.
        * ``"invalidated"`` — source eligible but the extraction job's
          ``content_sha256`` no longer matches the live document hash;
          candidates are returned with ``is_active=False`` so reviewers can
          see what drifted.
        * ``"not_found"`` — no extraction job exists for the document.
    """
    live = live_source if live_source is not None else _live_source_from_kb_document(document_id)
    if live is None or not _source_eligible(live):
        return {"status": "ineligible", "document_id": document_id, "candidates": {}}

    job = (
        db.session.query(KnowledgeGraphExtractionJob)
        .filter_by(document_id=document_id)
        .order_by(KnowledgeGraphExtractionJob.id.desc())
        .first()
    )
    if job is None:
        return {"status": "not_found", "document_id": document_id, "candidates": {}}

    version_matches = job.content_sha256 == live.get("content_sha256")
    status = "ok" if version_matches else "invalidated"

    studies = db.session.query(KnowledgeGraphStudyCandidate).filter_by(job_id=job.id).all()
    entities = db.session.query(KnowledgeGraphEntityCandidate).filter_by(job_id=job.id).all()
    relations = db.session.query(KnowledgeGraphRelationCandidate).filter_by(job_id=job.id).all()
    claims = db.session.query(KnowledgeGraphClaimCandidate).filter_by(job_id=job.id).all()

    relation_ids = [r.id for r in relations]
    claim_ids = [c.id for c in claims]
    rel_evidence = (
        db.session.query(KnowledgeGraphCandidateEvidence)
        .filter(KnowledgeGraphCandidateEvidence.relation_candidate_id.in_(relation_ids))
        .all()
    ) if relation_ids else []
    claim_evidence = (
        db.session.query(KnowledgeGraphClaimEvidence)
        .filter(KnowledgeGraphClaimEvidence.claim_candidate_id.in_(claim_ids))
        .all()
    ) if claim_ids else []

    rel_ev_by_rel: dict[int, list[dict]] = {}
    for ev in rel_evidence:
        rel_ev_by_rel.setdefault(ev.relation_candidate_id, []).append(_serialize_evidence(ev))
    claim_ev_by_claim: dict[int, list[dict]] = {}
    for ev in claim_evidence:
        claim_ev_by_claim.setdefault(ev.claim_candidate_id, []).append(_serialize_evidence(ev))

    return {
        "status": status,
        "document_id": document_id,
        "job": {
            "id": job.id,
            "schema_version": job.schema_version,
            "backend_name": job.backend_name,
            "extractor_version": job.extractor_version,
            "content_sha256": job.content_sha256,
            "state": job.state,
            "result_digest": job.result_digest,
        },
        "candidates": {
            "studies": [
                {
                    "id": s.id, "candidate_key": s.candidate_key,
                    "study_kind": s.study_kind, "review_status": s.review_status,
                    "context_evidence_count": s.context_evidence_count,
                    "attribution_evidence_key": s.attribution_evidence_key,
                }
                for s in studies
            ],
            "entities": [
                {
                    "id": e.id, "candidate_key": e.candidate_key,
                    "entity_type": e.entity_type, "mention": e.mention,
                    "resolution_status": e.resolution_status,
                    "canonical_entity_id": e.canonical_entity_id,
                    "review_status": e.review_status,
                }
                for e in entities
            ],
            "relations": [
                {
                    "id": r.id, "candidate_key": r.candidate_key,
                    "relation_type": r.relation_type,
                    "source_candidate_id": r.source_candidate_id,
                    "target_candidate_id": r.target_candidate_id,
                    "review_status": r.review_status,
                    "evidence": rel_ev_by_rel.get(r.id, []),
                }
                for r in relations
            ],
            "claims": [
                {
                    "id": c.id, "candidate_key": c.candidate_key,
                    "claim_type": c.claim_type, "statement": c.statement,
                    "subject_candidate_id": c.subject_candidate_id,
                    "object_candidate_id": c.object_candidate_id,
                    "review_status": c.review_status,
                    "evidence": claim_ev_by_claim.get(c.id, []),
                }
                for c in claims
            ],
        },
    }
