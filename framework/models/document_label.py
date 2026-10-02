from __future__ import annotations

from datetime import datetime, UTC

from .user import db


class DocumentLabel(db.Model):
    __tablename__ = "kb_document_label"
    __table_args__ = (
        db.UniqueConstraint("document_id", "label_code", name="uq_kb_document_label"),
    )

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    SOURCE_MANUAL = "manual"
    SOURCE_AUTOMATIC = "automatic"
    SOURCE_MIGRATION = "migration"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    document_id = db.Column(
        db.Integer,
        db.ForeignKey("kb_document.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label_code = db.Column(db.String(80), nullable=False, index=True)
    label_level = db.Column(db.String(20), nullable=False)
    parent_code = db.Column(db.String(40), nullable=True)
    review_status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING, index=True)
    confidence = db.Column(db.Float, nullable=True)
    evidence = db.Column(db.JSON, nullable=True)
    assignment_source = db.Column(db.String(20), nullable=False, default=SOURCE_AUTOMATIC)
    create_by = db.Column(db.Integer, nullable=True)
    review_by = db.Column(db.Integer, nullable=True)
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp())
    review_time = db.Column(db.DateTime, nullable=True)

    def approve(self, reviewer_id: int) -> None:
        self.review_status = self.STATUS_APPROVED
        self.review_by = reviewer_id
        self.review_time = datetime.now(UTC)

    def reject(self, reviewer_id: int) -> None:
        self.review_status = self.STATUS_REJECTED
        self.review_by = reviewer_id
        self.review_time = datetime.now(UTC)

    def to_dict(self):
        return {
            "id": self.id,
            "document_id": self.document_id,
            "label_code": self.label_code,
            "label_level": self.label_level,
            "parent_code": self.parent_code,
            "review_status": self.review_status,
            "confidence": self.confidence,
            "evidence": self.evidence or [],
            "assignment_source": self.assignment_source,
            "create_by": self.create_by,
            "review_by": self.review_by,
            "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S") if self.create_time else None,
            "review_time": self.review_time.strftime("%Y-%m-%d %H:%M:%S") if self.review_time else None,
        }
