import pytest
from flask import Flask

from framework.analysis_context import (
    AnalysisObjectInvalid,
    LegacyAnalysisContextAdapter,
    LegacyIdentifierAmbiguity,
)
from framework.models import ParcelInfo, SpatialRegionCatalog, db


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.add_all([
            ParcelInfo(parcel_id="P001", legacy_parcel_code="A0001", area_code="440281"),
            ParcelInfo(parcel_id="P002", legacy_parcel_code="A0002", area_code="440282"),
            SpatialRegionCatalog(object_type="county", object_id="440281", display_name="乐昌市", area_code="440281", source="seed", enabled=True),
            SpatialRegionCatalog(object_type="county", object_id="440282", display_name="南雄市", area_code="440282", source="seed", enabled=True),
        ])
        db.session.commit()
        yield app
        db.session.remove()


def test_legacy_two_ids_must_map_to_same_parcel(app):
    with app.app_context():
        result = LegacyAnalysisContextAdapter().resolve(
            {"parcel_id": "P001", "parcel_code": "A0001"}, user_id=7
        )
        assert result.object.id == "P001"
        assert result.validated_identifiers == {"parcel_id": "P001", "parcel_code": "A0001"}
        assert set(result.deprecations) == {"parcel_id", "parcel_code"}


def test_unmapped_pair_is_legacy_identifier_ambiguity(app):
    with app.app_context(), pytest.raises(LegacyIdentifierAmbiguity):
        LegacyAnalysisContextAdapter().resolve(
            {"parcel_id": "P001", "parcel_code": "UNKNOWN"}, user_id=7
        )


def test_two_ids_mapping_to_different_rows_is_ambiguity(app):
    with app.app_context(), pytest.raises(LegacyIdentifierAmbiguity):
        LegacyAnalysisContextAdapter().resolve(
            {"parcel_id": "P001", "parcel_code": "A0002"}, user_id=7
        )


def test_new_object_conflicting_with_legacy_id_is_422(app):
    with app.app_context(), pytest.raises(AnalysisObjectInvalid, match="冲突"):
        LegacyAnalysisContextAdapter().resolve({
            "analysis_context": {
                "action": "set",
                "object": {"type": "parcel", "id": "P001", "display_name": "客户端伪造名称"},
            },
            "parcel_id": "P002",
        }, user_id=7)


def test_client_display_fields_are_never_trusted(app):
    with app.app_context():
        result = LegacyAnalysisContextAdapter().resolve({
            "analysis_context": {
                "action": "set",
                "object": {
                    "type": "parcel", "id": "P001", "display_name": "伪造",
                    "area_code": "wrong", "source": "client",
                },
            },
        }, user_id=7)
        assert result.object.display_name == "乐昌市 地块 P001"
        assert result.object.area_code == "440281"
        assert result.object.source == "parcel_info"


def test_area_code_must_resolve_to_one_enabled_object(app):
    with app.app_context():
        db.session.add(SpatialRegionCatalog(
            object_type="zone", object_id="Z1", display_name="片区", area_code="440281",
            source="seed", enabled=True,
        ))
        db.session.commit()
        with pytest.raises(LegacyIdentifierAmbiguity):
            LegacyAnalysisContextAdapter().resolve({"area_code": "440281"}, user_id=7)
