"""Persist v2 research-extraction bundles as pending KG candidates.

This module is the write side of R2.6. It takes a compiled
``research_contract_v2.compile_bundle`` payload and writes every study,
entity, relation, evidence span, and direction claim into the relational
candidate tables. All rows are ``review_status='pending'`` — nothing is
published. Re-writing the same bundle for the same job is idempotent:
existing candidates for the job are replaced.
"""
from __future__ import annotations

from typing import Any, Mapping

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

BACKEND_NAME = "research-extraction-v2"
EXTRACTOR_VERSION = "task-evidence-extraction-v2"


def _span_fields(span: Mapping[str, Any]) -> dict[str, Any]:
    """Project a v2 span dict onto the kg_*_evidence column shape."""
    return {
        "document_id": span["document_id"],
        "content_sha256": span["document_sha256"],
        "chunk_index": span["chunk_index"],
        "page": span["page"],
        "span_start": span["start"],
        "span_end": span["end"],
        "quote": span["quote"],
        "quote_sha256": span["quote_sha256"],
    }


def _resolve_or_create_job(bundle: Mapping[str, Any]) -> KnowledgeGraphExtractionJob:
    """Find the extraction job by its idempotency key or create a new one.

    Re-writing the same bundle replaces all existing candidates for the job
    so that corrected extractions do not leave stale rows behind.
    """
    source = bundle["source"]
    provenance = bundle["provenance"]
    config_digest = provenance["configuration_sha256"]

    job = db.session.query(KnowledgeGraphExtractionJob).filter_by(
        document_id=source["document_id"],
        content_sha256=source["document_sha256"],
        schema_version=bundle["schema_version"],
        backend_name=BACKEND_NAME,
        extractor_version=EXTRACTOR_VERSION,
    ).first()

    if job is None:
        job = KnowledgeGraphExtractionJob(
            document_id=source["document_id"],
            content_sha256=source["document_sha256"],
            schema_version=bundle["schema_version"],
            backend_name=BACKEND_NAME,
            extractor_version=EXTRACTOR_VERSION,
            backend_config_digest=config_digest,
            state="succeeded",
            result_digest=bundle.get("identity"),
            raw_output_fingerprint=bundle.get("identity"),
        )
        db.session.add(job)
        db.session.flush()
    else:
        # Idempotent rewrite: clear previous candidates, keep the job row.
        job.backend_config_digest = config_digest
        job.result_digest = bundle.get("identity")
        job.raw_output_fingerprint = bundle.get("identity")
        job.state = "succeeded"
        _delete_job_candidates(job.id)
        db.session.flush()
    return job


def _delete_job_candidates(job_id: int) -> None:
    """Cascade-delete every candidate attached to ``job_id``."""
    # Evidence and claims first (FK constraints), then relations, entities, studies.
    db.session.query(KnowledgeGraphClaimEvidence).filter(
        KnowledgeGraphClaimEvidence.claim_candidate_id.in_(
            db.session.query(KnowledgeGraphClaimCandidate.id).filter_by(job_id=job_id)
        )
    ).delete(synchronize_session=False)
    db.session.query(KnowledgeGraphCandidateEvidence).filter(
        KnowledgeGraphCandidateEvidence.relation_candidate_id.in_(
            db.session.query(KnowledgeGraphRelationCandidate.id).filter_by(job_id=job_id)
        )
    ).delete(synchronize_session=False)
    db.session.query(KnowledgeGraphClaimCandidate).filter_by(job_id=job_id).delete(synchronize_session=False)
    db.session.query(KnowledgeGraphRelationCandidate).filter_by(job_id=job_id).delete(synchronize_session=False)
    db.session.query(KnowledgeGraphEntityCandidate).filter_by(job_id=job_id).delete(synchronize_session=False)
    db.session.query(KnowledgeGraphStudyCandidate).filter_by(job_id=job_id).delete(synchronize_session=False)


def write_bundle(bundle: Mapping[str, Any]) -> dict[str, int]:
    """Persist a v2 research-extraction bundle as pending candidates.

    Returns a summary dict with the row counts written per table.
    """
    job = _resolve_or_create_job(bundle)

    source = bundle["source"]
    schema_version = bundle["schema_version"]

    # --- studies ---
    study_ids: dict[str, int] = {}
    for study in bundle.get("studies", []):
        attribution = study.get("attribution")
        row = KnowledgeGraphStudyCandidate(
            job_id=job.id,
            candidate_key=study["local_id"],
            study_kind=study["kind"],
            attribution_evidence_key=attribution["id"] if attribution else None,
            context_evidence_count=len(study.get("context", [])),
            candidate_payload={
                "context": study.get("context", []),
                "attribution": attribution,
            },
            review_status="pending",
        )
        db.session.add(row)
        db.session.flush()
        study_ids[study["local_id"]] = row.id

    # --- entities ---
    entity_ids: dict[str, int] = {}
    for entity in bundle.get("entities", []):
        mention = entity["mention"]
        normalization = entity.get("normalization") or {}
        row = KnowledgeGraphEntityCandidate(
            job_id=job.id,
            candidate_key=entity["local_id"],
            entity_type=entity["entity_type"],
            mention=entity.get("surface") or mention["quote"],
            canonical_entity_id=normalization.get("canonical_id"),
            canonical_name=normalization.get("canonical_name"),
            resolution_status=normalization.get("status", "unresolved"),
            candidate_payload={
                "mention": mention,
                "study_id": entity.get("study_id"),
            },
            review_status="pending",
        )
        db.session.add(row)
        db.session.flush()
        entity_ids[entity["local_id"]] = row.id

    # --- relations + evidence ---
    relation_count = 0
    evidence_count = 0
    claim_count = 0
    claim_evidence_count = 0
    for relation in bundle.get("relations", []):
        source_id = entity_ids.get(relation["source_id"])
        target_id = entity_ids.get(relation["target_id"])
        if source_id is None or target_id is None:
            raise ValueError(
                f"relation {relation['local_id']} references unknown entity"
            )
        result_span = relation["result"]
        rel_row = KnowledgeGraphRelationCandidate(
            job_id=job.id,
            candidate_key=relation["local_id"],
            relation_type=relation["relation_type"],
            source_candidate_id=source_id,
            target_candidate_id=target_id,
            candidate_payload={
                "direction": relation["direction"],
                "qualifiers": relation.get("qualifiers", {}),
                "study_id": relation.get("study_id"),
                "result_evidence_key": result_span["id"],
            },
            review_status="pending",
        )
        db.session.add(rel_row)
        db.session.flush()
        relation_count += 1

        # Primary result evidence.
        db.session.add(KnowledgeGraphCandidateEvidence(
            relation_candidate_id=rel_row.id,
            evidence_key="result",
            schema_version=schema_version,
            backend_name=BACKEND_NAME,
            extractor_version=EXTRACTOR_VERSION,
            **_span_fields(result_span),
            review_status="pending",
            is_active=True,
        ))
        db.session.flush()
        evidence_count += 1

        # Qualifier evidence spans.
        for name, qualifier in (relation.get("qualifiers") or {}).items():
            qev = qualifier.get("evidence") if isinstance(qualifier, dict) else None
            if qev:
                db.session.add(KnowledgeGraphCandidateEvidence(
                    relation_candidate_id=rel_row.id,
                    evidence_key=f"qualifier:{name}",
                    schema_version=schema_version,
                    backend_name=BACKEND_NAME,
                    extractor_version=EXTRACTOR_VERSION,
                    **_span_fields(qev),
                    review_status="pending",
                    is_active=True,
                ))
                db.session.flush()
                evidence_count += 1

        # --- direction claim (semantic assertion) ---
        claim_row = KnowledgeGraphClaimCandidate(
            job_id=job.id,
            candidate_key=f"{relation['local_id']}:direction",
            claim_type="effect_direction",
            subject_candidate_id=source_id,
            object_candidate_id=target_id,
            statement=relation["direction"],
            candidate_payload={
                "direction": relation["direction"],
                "relation_id": relation.get("id"),
                "study_id": relation.get("study_id"),
            },
            review_status="pending",
        )
        db.session.add(claim_row)
        db.session.flush()
        claim_count += 1

        db.session.add(KnowledgeGraphClaimEvidence(
            claim_candidate_id=claim_row.id,
            evidence_key="result",
            schema_version=schema_version,
            backend_name=BACKEND_NAME,
            extractor_version=EXTRACTOR_VERSION,
            **_span_fields(result_span),
            review_status="pending",
            is_active=True,
        ))
        db.session.flush()
        claim_evidence_count += 1

    db.session.commit()
    return {
        "job": 1,
        "studies": len(study_ids),
        "entities": len(entity_ids),
        "relations": relation_count,
        "relation_evidence": evidence_count,
        "claims": claim_count,
        "claim_evidence": claim_evidence_count,
    }
