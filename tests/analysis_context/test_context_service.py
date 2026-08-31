import pytest
from flask import Flask

from framework.analysis_context.contracts import AnalysisObject
from framework.analysis_context.errors import AnalysisContextConflict, AnalysisObjectInvalid
from framework.analysis_context.service import AnalysisContextService
from framework.models import Conversation, ParcelInfo, SpatialRegionCatalog, db


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Conversation(user_id=7, title="A"),
            Conversation(user_id=7, title="B"),
            Conversation(user_id=8, title="other"),
            ParcelInfo(parcel_id="P001", legacy_parcel_code="A0001", area_code="440281"),
            ParcelInfo(parcel_id="P002", legacy_parcel_code="A0002", area_code="440281"),
            SpatialRegionCatalog(object_type="county", object_id="440281", display_name="乐昌市", area_code="440281", source="seed", enabled=True),
        ])
        db.session.commit()
        yield app
        db.session.remove()


def _conversations():
    return Conversation.query.order_by(Conversation.id).all()


def _set_body(parcel_id="P001", expected_version=0):
    return {"analysis_context": {
        "action": "set", "expected_version": expected_version,
        "object": {"type": "parcel", "id": parcel_id},
    }}


def test_set_then_inherit_clear_and_conversation_isolation(app):
    with app.app_context():
        a, b, _ = _conversations()
        service = AnalysisContextService()
        set_result = service.resolve(a, user_id=7, body=_set_body())
        assert set_result.context.version == 1
        assert set_result.context.object.id == "P001"
        assert service.resolve(a, user_id=7, body={}).context.object.id == "P001"
        assert service.resolve(b, user_id=7, body={}).context.object is None
        cleared = service.resolve(a, user_id=7, body={
            "analysis_context": {"action": "clear", "expected_version": 1}
        })
        assert cleared.context.version == 2 and cleared.context.object is None
        assert a.analysis_object is None and a.context_version == 2


def test_stale_set_returns_latest_without_mutation(app):
    with app.app_context():
        conversation = _conversations()[0]
        service = AnalysisContextService()
        service.resolve(conversation, user_id=7, body=_set_body())
        before = (conversation.analysis_object, conversation.context_version)
        with pytest.raises(AnalysisContextConflict) as exc:
            service.resolve(conversation, user_id=7, body=_set_body("P002", expected_version=0))
        assert exc.value.details["latest_version"] == 1
        db.session.refresh(conversation)
        assert (conversation.analysis_object, conversation.context_version) == before


def test_scenario_does_not_read_or_mutate_conversation(app):
    with app.app_context():
        conversation = _conversations()[0]
        service = AnalysisContextService()
        service.resolve(conversation, user_id=7, body=_set_body())
        before = (conversation.analysis_object, conversation.context_version)
        result = service.resolve(conversation, user_id=7, body={
            "calculation_mode": "scenario", "SJD": 5.1, "JHX": 1.2,
        })
        assert result.context.to_dict() == {"mode": "scenario", "version": None, "object": None}
        assert result.scenario_inputs == {"SJD": 5.1, "JHX": 1.2}
        assert (conversation.analysis_object, conversation.context_version) == before


@pytest.mark.parametrize("body", [
    {"calculation_mode": "unknown"},
    {"analysis_context": {"action": "unknown"}},
    {"analysis_context": {"action": "set", "expected_version": 0}},
    {"analysis_context": {"object": {"type": "parcel", "id": "P001"}, "expected_version": 0}},
    {"analysis_context": {"action": "set", "object": {"type": "parcel", "id": "P001"}}},
    {"analysis_context": {"action": "clear"}},
])
def test_invalid_controls_do_not_mutate(app, body):
    with app.app_context():
        conversation = _conversations()[0]
        before = (conversation.analysis_object, conversation.context_version)
        with pytest.raises(AnalysisObjectInvalid):
            AnalysisContextService().resolve(conversation, user_id=7, body=body)
        assert (conversation.analysis_object, conversation.context_version) == before


def test_cross_user_cannot_read_or_update(app):
    with app.app_context():
        conversation = _conversations()[0]
        with pytest.raises(AnalysisObjectInvalid, match="无权"):
            AnalysisContextService().resolve(conversation, user_id=8, body=_set_body())
        assert conversation.context_version == 0 and conversation.analysis_object is None


def test_failed_object_resolution_leaves_context_unchanged(app):
    with app.app_context():
        conversation = _conversations()[0]
        before = (conversation.analysis_object, conversation.context_version)
        with pytest.raises(AnalysisObjectInvalid):
            AnalysisContextService().resolve(conversation, user_id=7, body=_set_body("missing"))
        assert (conversation.analysis_object, conversation.context_version) == before


def test_legacy_field_implicitly_sets_and_returns_deprecation(app):
    with app.app_context():
        conversation = _conversations()[0]
        result = AnalysisContextService().resolve(
            conversation, user_id=7, body={"parcel_code": "A0001"}
        )
        assert result.context.version == 1
        assert result.context.object.id == "P001"
        assert result.validated_identifiers["parcel_id"] == "P001"
        assert result.deprecations == ("parcel_code",)


def test_corrupt_inherited_json_is_rejected(app):
    with app.app_context():
        conversation = _conversations()[0]
        conversation.analysis_object = {"type": "parcel", "id": "P001"}
        db.session.commit()
        with pytest.raises(AnalysisObjectInvalid, match="损坏"):
            AnalysisContextService().resolve(conversation, user_id=7, body={})
