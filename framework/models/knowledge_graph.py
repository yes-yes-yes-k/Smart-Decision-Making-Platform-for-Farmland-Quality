"""Relational governance models for incremental knowledge-graph updates."""
from __future__ import annotations

from datetime import UTC, datetime

from .user import db


def scheduling_utcnow():
    return datetime.now(UTC).replace(tzinfo=None)



class KnowledgeGraphExtractionJob(db.Model):
    __tablename__ = "kg_extraction_job"
    __table_args__ = (
        db.UniqueConstraint(
            "document_id",
            "content_sha256",
            "schema_version",
            "backend_name",
            "extractor_version",
            name="uq_kg_job_idempotency",
        ),
        db.Index("idx_kg_job_document_state", "document_id", "state"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    document_id = db.Column(
        db.Integer,
        db.ForeignKey("kb_document.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_sha256 = db.Column(db.String(64), nullable=False)
    schema_version = db.Column(db.String(128), nullable=False)
    backend_name = db.Column(db.String(100), nullable=False)
    extractor_version = db.Column(db.String(100), nullable=False)
    backend_config_digest = db.Column(db.String(64), nullable=False)
    state = db.Column(db.String(30), nullable=False, default="pending")
    priority = db.Column(db.Integer, nullable=False, default=0)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=5)
    available_at = db.Column(db.DateTime, nullable=False, default=scheduling_utcnow)
    lease_owner = db.Column(db.String(128), nullable=True)
    lease_expires_at = db.Column(db.DateTime, nullable=True)
    heartbeat_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    failure_code = db.Column(db.String(80), nullable=True)
    failure_message = db.Column(db.String(1000), nullable=True)
    retryable = db.Column(db.Boolean, nullable=False, default=False)
    result_digest = db.Column(db.String(64), nullable=True)
    raw_output_fingerprint = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class KnowledgeGraphStudyCandidate(db.Model):
    """Research-record (study) candidate produced by the v2 extraction contract.

    Studies group entities and relations extracted from the same primary
    experiment or cited work. Context and attribution spans are stored in
    ``candidate_payload``; dedicated evidence rows remain attached to
    relation/claim candidates where span re-verification is required.
    """

    __tablename__ = "kg_study_candidate"
    __table_args__ = (
        db.UniqueConstraint("job_id", "candidate_key", name="uq_kg_study_candidate"),
        db.Index("idx_kg_study_pending_review", "study_kind", "id"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(
        db.Integer,
        db.ForeignKey("kg_extraction_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_key = db.Column(db.String(128), nullable=False)
    study_kind = db.Column(db.String(40), nullable=False)
    attribution_evidence_key = db.Column(db.String(128), nullable=True)
    context_evidence_count = db.Column(db.Integer, nullable=False, default=0)
    risk_level = db.Column(db.String(40), nullable=False, default="new_study")
    review_status = db.Column(db.String(30), nullable=False, default="pending")
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    candidate_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class KnowledgeGraphEntityCandidate(db.Model):
    __tablename__ = "kg_entity_candidate"
    __table_args__ = (
        db.UniqueConstraint("job_id", "candidate_key", name="uq_kg_entity_candidate"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(
        db.Integer,
        db.ForeignKey("kg_extraction_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_key = db.Column(db.String(128), nullable=False)
    entity_type = db.Column(db.String(80), nullable=False)
    mention = db.Column(db.String(1000), nullable=False)
    canonical_entity_id = db.Column(db.String(255), nullable=True)
    canonical_name = db.Column(db.String(1000), nullable=True)
    resolution_status = db.Column(db.String(40), nullable=False, default="unresolved")
    risk_level = db.Column(db.String(40), nullable=False, default="new_entity")
    review_status = db.Column(db.String(30), nullable=False, default="pending")
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    candidate_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class KnowledgeGraphRelationCandidate(db.Model):
    __tablename__ = "kg_relation_candidate"
    __table_args__ = (
        db.UniqueConstraint("job_id", "candidate_key", name="uq_kg_relation_candidate"),
        db.Index(
            "idx_kg_relation_canonical_triple",
            "relation_type", "canonical_source_id", "canonical_target_id",
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(
        db.Integer,
        db.ForeignKey("kg_extraction_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_key = db.Column(db.String(128), nullable=False)
    relation_type = db.Column(db.String(100), nullable=False)
    source_candidate_id = db.Column(
        db.Integer,
        db.ForeignKey("kg_entity_candidate.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_candidate_id = db.Column(
        db.Integer,
        db.ForeignKey("kg_entity_candidate.id", ondelete="RESTRICT"),
        nullable=False,
    )
    canonical_source_id = db.Column(db.String(255), nullable=True)
    canonical_target_id = db.Column(db.String(255), nullable=True)
    risk_level = db.Column(db.String(40), nullable=False, default="new_fact")
    validation_status = db.Column(db.String(40), nullable=False, default="pending")
    review_status = db.Column(db.String(30), nullable=False, default="pending")
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    support_document_count = db.Column(db.Integer, nullable=False, default=1)
    candidate_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class KnowledgeGraphClaimCandidate(db.Model):
    __tablename__ = "kg_claim_candidate"
    __table_args__ = (
        db.UniqueConstraint("job_id", "candidate_key", name="uq_kg_claim_candidate"),
        db.Index("idx_kg_claim_subject", "canonical_subject_id", "claim_type"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(
        db.Integer,
        db.ForeignKey("kg_extraction_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_key = db.Column(db.String(128), nullable=False)
    claim_type = db.Column(db.String(100), nullable=False)
    subject_candidate_id = db.Column(
        db.Integer,
        db.ForeignKey("kg_entity_candidate.id", ondelete="RESTRICT"),
        nullable=False,
    )
    object_candidate_id = db.Column(
        db.Integer,
        db.ForeignKey("kg_entity_candidate.id", ondelete="RESTRICT"),
        nullable=True,
    )
    canonical_subject_id = db.Column(db.String(255), nullable=True)
    canonical_object_id = db.Column(db.String(255), nullable=True)
    statement = db.Column(db.Text, nullable=False)
    risk_level = db.Column(db.String(40), nullable=False, default="new_claim")
    validation_status = db.Column(db.String(40), nullable=False, default="pending")
    review_status = db.Column(db.String(30), nullable=False, default="pending")
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    candidate_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class KnowledgeGraphCandidateEvidence(db.Model):
    __tablename__ = "kg_candidate_evidence"
    __table_args__ = (
        db.UniqueConstraint(
            "relation_candidate_id", "evidence_key", name="uq_kg_candidate_evidence",
        ),
        db.Index(
            "idx_kg_evidence_document_active",
            "document_id", "content_sha256", "is_active",
        ),
        db.Index("idx_kg_evidence_review_queue", "review_status", "id"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    relation_candidate_id = db.Column(
        db.Integer,
        db.ForeignKey("kg_relation_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_key = db.Column(db.String(128), nullable=False)
    document_id = db.Column(
        db.Integer,
        db.ForeignKey("kb_document.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_sha256 = db.Column(db.String(64), nullable=False)
    chunk_index = db.Column(db.Integer, nullable=False)
    page = db.Column(db.Integer, nullable=False)
    span_start = db.Column(db.Integer, nullable=False)
    span_end = db.Column(db.Integer, nullable=False)
    quote = db.Column(db.Text, nullable=False)
    quote_sha256 = db.Column(db.String(64), nullable=False)
    schema_version = db.Column(db.String(128), nullable=False)
    backend_name = db.Column(db.String(100), nullable=False)
    extractor_version = db.Column(db.String(100), nullable=False)
    validation_status = db.Column(db.String(40), nullable=False, default="pending")
    review_status = db.Column(db.String(30), nullable=False, default="pending")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    invalidated_at = db.Column(db.DateTime, nullable=True)
    invalidation_reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())


class KnowledgeGraphClaimEvidence(db.Model):
    __tablename__ = "kg_claim_evidence"
    __table_args__ = (
        db.UniqueConstraint(
            "claim_candidate_id", "evidence_key", name="uq_kg_claim_evidence",
        ),
        db.Index(
            "idx_kg_claim_evidence_document_active",
            "document_id", "content_sha256", "is_active",
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    claim_candidate_id = db.Column(
        db.Integer,
        db.ForeignKey("kg_claim_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_key = db.Column(db.String(128), nullable=False)
    document_id = db.Column(
        db.Integer,
        db.ForeignKey("kb_document.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_sha256 = db.Column(db.String(64), nullable=False)
    chunk_index = db.Column(db.Integer, nullable=False)
    page = db.Column(db.Integer, nullable=False)
    span_start = db.Column(db.Integer, nullable=False)
    span_end = db.Column(db.Integer, nullable=False)
    quote = db.Column(db.Text, nullable=False)
    quote_sha256 = db.Column(db.String(64), nullable=False)
    schema_version = db.Column(db.String(128), nullable=False)
    backend_name = db.Column(db.String(100), nullable=False)
    extractor_version = db.Column(db.String(100), nullable=False)
    validation_status = db.Column(db.String(40), nullable=False, default="pending")
    review_status = db.Column(db.String(30), nullable=False, default="pending")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    invalidated_at = db.Column(db.DateTime, nullable=True)
    invalidation_reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())


class KnowledgeGraphReviewDecision(db.Model):
    __tablename__ = "kg_review_decision"
    __table_args__ = (
        db.Index("idx_kg_review_subject", "subject_type", "subject_id", "created_at"),
        db.Index("idx_kg_review_actor", "reviewer_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)
    subject_type = db.Column(db.String(30), nullable=False)
    subject_id = db.Column(db.Integer, nullable=False)
    decision = db.Column(db.String(30), nullable=False)
    reason = db.Column(db.String(2000), nullable=False)
    reviewer_id = db.Column(db.Integer, nullable=False)
    schema_version = db.Column(db.String(128), nullable=False)
    backend_name = db.Column(db.String(100), nullable=False)
    extractor_version = db.Column(db.String(100), nullable=False)
    reviewed_value = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())


class KnowledgeGraphRelease(db.Model):
    __tablename__ = "kg_release"
    __table_args__ = (
        db.Index("idx_kg_release_state_created", "state", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    release_id = db.Column(db.String(128), nullable=False, unique=True)
    sequence_no = db.Column(db.Integer, nullable=False, unique=True)
    parent_release_id = db.Column(db.String(128), nullable=True)
    schema_version = db.Column(db.String(128), nullable=False)
    state = db.Column(db.String(30), nullable=False, default="draft")
    change_checksum = db.Column(db.String(64), nullable=False)
    diff_summary = db.Column(db.JSON, nullable=False)
    validation_report = db.Column(db.JSON, nullable=True)
    created_by = db.Column(db.Integer, nullable=False)
    validated_at = db.Column(db.DateTime, nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())


class KnowledgeGraphReleaseChange(db.Model):
    __tablename__ = "kg_release_change"
    __table_args__ = (
        db.UniqueConstraint("release_id", "sequence_no", name="uq_kg_release_sequence"),
        db.UniqueConstraint("release_id", "change_checksum", name="uq_kg_release_change"),
        db.Index("idx_kg_release_change_subject", "subject_type", "subject_key"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    release_id = db.Column(
        db.String(128),
        db.ForeignKey("kg_release.release_id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_no = db.Column(db.Integer, nullable=False)
    change_type = db.Column(db.String(40), nullable=False)
    subject_type = db.Column(db.String(30), nullable=False)
    subject_key = db.Column(db.String(255), nullable=False)
    change_payload = db.Column(db.JSON, nullable=False)
    change_checksum = db.Column(db.String(64), nullable=False)
    valid_from_release = db.Column(db.String(128), nullable=False)
    valid_to_release = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())


class KnowledgeGraphControl(db.Model):
    __tablename__ = "kg_control"

    control_id = db.Column(db.String(40), primary_key=True)
    active_release_id = db.Column(db.String(128), nullable=True)
    active_sequence_no = db.Column(db.Integer, nullable=True)
    updated_by = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class KnowledgeGraphRollbackAudit(db.Model):
    __tablename__ = "kg_rollback_audit"
    __table_args__ = (
        db.Index("idx_kg_rollback_created", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)
    source_release_id = db.Column(db.String(128), nullable=True)
    target_release_id = db.Column(db.String(128), nullable=False)
    operator_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(2000), nullable=False)
    duration_ms = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())


class KnowledgeGraphAuditExport(db.Model):
    __tablename__ = "kg_audit_export"
    __table_args__ = (
        db.UniqueConstraint("release_id", "format", name="uq_kg_export_release_format"),
        db.Index("idx_kg_export_state", "state", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    release_id = db.Column(db.String(128), nullable=False)
    format = db.Column(db.String(20), nullable=False)
    state = db.Column(db.String(30), nullable=False, default="pending")
    artifact_path = db.Column(db.String(1000), nullable=True)
    artifact_sha256 = db.Column(db.String(64), nullable=True)
    error_code = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    completed_at = db.Column(db.DateTime, nullable=True)


class KnowledgeGraphRelationRetirementCandidate(db.Model):
    __tablename__ = "kg_relation_retirement_candidate"
    __table_args__ = (
        db.Index("idx_kg_retirement_review", "review_status", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    relation_candidate_id = db.Column(db.Integer, nullable=False)
    relation_key = db.Column(db.String(600), nullable=False)
    relation_snapshot = db.Column(db.JSON, nullable=False)
    trigger_document_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    active_evidence_count = db.Column(db.Integer, nullable=False, default=0)
    review_status = db.Column(db.String(30), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())


class KnowledgeGraphBackfillRun(db.Model):
    __tablename__ = "kg_backfill_run"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    run_key = db.Column(db.String(128), nullable=False, unique=True)
    schema_version = db.Column(db.String(128), nullable=False)
    backend_name = db.Column(db.String(100), nullable=False)
    extractor_version = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(30), nullable=False, default="running")
    checkpoint_document_id = db.Column(db.Integer, nullable=False, default=0)
    eligible_count = db.Column(db.Integer, nullable=False, default=0)
    created_count = db.Column(db.Integer, nullable=False, default=0)
    reused_count = db.Column(db.Integer, nullable=False, default=0)
    skipped_count = db.Column(db.Integer, nullable=False, default=0)
    config_snapshot = db.Column(db.JSON, nullable=False)
    created_by = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime, nullable=False, default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class KnowledgeGraphOutboxEvent(db.Model):
    __tablename__ = "kg_outbox_event"
    __table_args__ = (
        db.Index("idx_kg_outbox_aggregate", "aggregate_type", "aggregate_id", "id"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_key = db.Column(db.String(128), nullable=False, unique=True)
    event_type = db.Column(db.String(80), nullable=False)
    aggregate_type = db.Column(db.String(80), nullable=False)
    aggregate_id = db.Column(db.String(255), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    state = db.Column(db.String(30), nullable=False, default="pending")
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    available_at = db.Column(db.DateTime, nullable=False, default=scheduling_utcnow)
    lease_owner = db.Column(db.String(128), nullable=True)
    lease_expires_at = db.Column(db.DateTime, nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    last_error_code = db.Column(db.String(80), nullable=True)
    last_error_message = db.Column(db.String(1000), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
