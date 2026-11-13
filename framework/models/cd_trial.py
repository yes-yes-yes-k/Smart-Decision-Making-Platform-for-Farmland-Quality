"""Saved Cd conversation trials, separate from batch prediction results."""

from .user import db


class CdTrial(db.Model):
    __tablename__ = "cd_conversation_trial"
    __table_args__ = (
        db.UniqueConstraint("conversation_id", "result_revision", name="uq_cd_trial_conversation_revision"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey("kb_conversation.id", ondelete="CASCADE"), nullable=False)
    result_revision = db.Column(db.Integer, nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
