"""Persist an owned, completed Cd result exactly once."""

from sqlalchemy.exc import IntegrityError

from framework.models import Conversation, Message, db
from framework.models.cd_trial import CdTrial


def save_trial(user_id: int, conversation_id: int, message_id: int) -> int | None:
    message = (
        Message.query.join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Message.id == message_id, Message.conversation_id == conversation_id,
                Message.role == "assistant", Conversation.user_id == user_id)
        .one_or_none()
    )
    if message is None:
        return None
    snapshot = message.analysis_context_snapshot or {}
    draft = snapshot.get("cd_draft")
    result = snapshot.get("cd_trial_result")
    if not draft or not result or result.get("status") not in {"success", "degraded"}:
        return None

    key = {"user_id": user_id, "conversation_id": conversation_id, "result_revision": draft["revision"]}
    try:
        record = CdTrial(**key, payload={"schema_version":2,"calculation_type":draft.get('calculation_type','prediction'),
                                        "scope_and_inputs": draft, "result": result})
        db.session.add(record)
        db.session.flush()
        record_id = record.id
        db.session.commit()
        return record_id
    except IntegrityError:
        db.session.rollback()
        existing = CdTrial.query.filter_by(**key).one_or_none()
        if existing is None:
            raise
        return existing.id
    except Exception:
        db.session.rollback()
        raise
