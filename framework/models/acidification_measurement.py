"""Per-conversation acidification inputs, provenance and calculation results."""
from datetime import UTC, datetime

from .user import db


class AcidificationMeasurement(db.Model):
    __tablename__ = "kb_acidification_measurement"
    __table_args__ = (
        db.Index("idx_acidification_conversation_user", "conversation_id", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("kb_conversation.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    parcel_id = db.Column(db.String(128), nullable=False)
    mode = db.Column(db.String(20), nullable=False)
    land_type = db.Column(db.String(40), nullable=True)
    input_data = db.Column(db.JSON, nullable=False, default=dict)
    result_data = db.Column(db.JSON, nullable=True)
    source_info = db.Column(db.JSON, nullable=False, default=dict)
    status = db.Column(db.String(20), nullable=False, default="draft")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "parcel_id": self.parcel_id,
            "mode": self.mode,
            "land_type": self.land_type,
            "input_data": self.input_data or {},
            "result_data": self.result_data,
            "source_info": self.source_info or {},
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
