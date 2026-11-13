from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from flask import Flask
import pytest
from sqlalchemy.exc import OperationalError

from framework.api.services.cd_trial import save_trial
from framework.models import CdTrial, Conversation, Message, db


def test_saved_trials_are_owned_and_idempotent(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path / 'trials.db'}"
    db.init_app(app)
    with app.app_context():
        for model in (Conversation, Message, CdTrial):
            model.__table__.create(db.engine)
        conversation = Conversation(user_id=10)
        db.session.add(conversation)
        db.session.flush()
        conversation_id = conversation.id
        for revision in (1, 2, 3):
            db.session.add(Message(
                conversation_id=conversation_id, role="assistant", content="试算",
                analysis_context_snapshot={
                    "cd_draft": {"revision": revision, "parameters": {"solution": revision},
                                 "calculation_type":"flux" if revision==2 else "prediction"},
                    "cd_trial_result": {"status": "success" if revision < 3 else "needs_scenario_inputs"},
                },
            ))
        db.session.commit()
        first, second, incomplete = [message.id for message in Message.query.order_by(Message.id)]
        assert save_trial(11, conversation_id, first) is None
        assert save_trial(10, conversation_id, incomplete) is None
        with monkeypatch.context() as patch:
            def failed_commit():
                raise OperationalError("COMMIT", None, RuntimeError("temporary failure"))

            patch.setattr(db.session, "commit", failed_commit)
            with pytest.raises(OperationalError):
                save_trial(10, conversation_id, first)
        assert CdTrial.query.count() == 0
        record = save_trial(10, conversation_id, first)
        assert save_trial(10, conversation_id, first) == record
        barrier = Barrier(2)

        def save_second():
            with app.app_context():
                barrier.wait(timeout=5)
                return save_trial(10, conversation_id, second)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_save, retry = [pool.submit(save_second) for _ in range(2)]
            assert first_save.result() == retry.result()
            assert first_save.result() != record
        assert CdTrial.query.count() == 2
