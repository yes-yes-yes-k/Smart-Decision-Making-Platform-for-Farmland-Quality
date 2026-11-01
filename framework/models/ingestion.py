from __future__ import annotations

from .user import db


class IngestionBatch(db.Model):
    __tablename__ = "kb_ingestion_batch"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_key = db.Column(db.String(128), nullable=False, unique=True, index=True)
    name = db.Column(db.String(255), nullable=False)
    source_type = db.Column(db.String(40), nullable=False, default="manifest")
    state = db.Column(db.String(40), nullable=False, default="pending", index=True)
    dry_run = db.Column(db.Boolean, nullable=False, default=False)
    requested_by = db.Column(db.Integer, nullable=False)
    manifest_hash = db.Column(db.String(64), nullable=False, index=True)
    source_artifact_id = db.Column(db.String(255), nullable=True)
    total_count = db.Column(db.Integer, nullable=False, default=0)
    completed_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    skipped_count = db.Column(db.Integer, nullable=False, default=0)
    review_count = db.Column(db.Integer, nullable=False, default=0)
    cancelled_count = db.Column(db.Integer, nullable=False, default=0)
    config_snapshot = db.Column(db.JSON, nullable=True)
    summary = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    items = db.relationship(
        "IngestionItem", backref="batch", lazy="select",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    def to_dict(self, include_items: bool = False):
        data = {
            "id": self.id,
            "batch_key": self.batch_key,
            "name": self.name,
            "source_type": self.source_type,
            "state": self.state,
            "dry_run": bool(self.dry_run),
            "requested_by": self.requested_by,
            "manifest_hash": self.manifest_hash,
            "source_artifact_id": self.source_artifact_id,
            "total_count": self.total_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "review_count": self.review_count,
            "cancelled_count": self.cancelled_count,
            "config_snapshot": self.config_snapshot or {},
            "summary": self.summary or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
        if include_items:
            data["items"] = [item.to_dict() for item in self.items]
        return data


class IngestionItem(db.Model):
    __tablename__ = "kb_ingestion_item"
    __table_args__ = (
        db.UniqueConstraint(
            "document_id", "attempt_no", name="uq_kb_ingestion_item_attempt"
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_id = db.Column(
        db.Integer, db.ForeignKey("kb_ingestion_batch.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    document_id = db.Column(
        db.Integer, db.ForeignKey("kb_document.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    attempt_no = db.Column(db.Integer, nullable=False, default=1)
    source_relative_path = db.Column(db.String(1000), nullable=True)
    source_hash = db.Column(db.String(64), nullable=True, index=True)
    idempotency_key = db.Column(db.String(128), nullable=True)
    state = db.Column(db.String(40), nullable=False, default="pending", index=True)
    stage = db.Column(db.String(40), nullable=False, default="accepted", index=True)
    progress = db.Column(db.Integer, nullable=False, default=0)
    review_status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    submitted_domain_labels = db.Column(db.JSON, nullable=True)
    approved_domain_labels = db.Column(db.JSON, nullable=True)
    reviewed_by = db.Column(db.Integer, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_note = db.Column(db.String(1000), nullable=True)
    failure_code = db.Column(db.String(80), nullable=True)
    failure_message = db.Column(db.String(1000), nullable=True)
    retryable = db.Column(db.Boolean, nullable=False, default=False)
    quality_summary = db.Column(db.JSON, nullable=True)
    config_snapshot = db.Column(db.JSON, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    document = db.relationship("Document", backref=db.backref("ingestion_items", lazy="select"))

    def to_dict(self):
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "document_id": self.document_id,
            "attempt": self.attempt_no,
            "state": self.state,
            "stage": self.stage,
            "progress": self.progress,
            "review_status": self.review_status,
            "submitted_domain_labels": self.submitted_domain_labels or [],
            "approved_domain_labels": self.approved_domain_labels or [],
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "review_note": self.review_note,
            "failure_code": self.failure_code,
            "failure_message": self.failure_message,
            "retryable": bool(self.retryable),
            "quality_summary": self.quality_summary or {},
            "config_snapshot": self.config_snapshot or {},
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
