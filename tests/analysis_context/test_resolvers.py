import sqlalchemy as sa
import pytest
from flask import Flask

from framework.analysis_context import (
    AnalysisObjectInvalid,
    AnalysisObjectValidationUnavailable,
    ObjectType,
    SpatialObjectResolverRegistry,
)
from framework.models import ParcelInfo, SpatialRegionCatalog, db


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def _region(kind, object_id, name, *, area_code=None, parent=None, enabled=True):
    return SpatialRegionCatalog(
        object_type=kind, object_id=object_id, display_name=name, area_code=area_code,
        parent_object_type=parent[0] if parent else None,
        parent_object_id=parent[1] if parent else None,
        source="seed", enabled=enabled,
    )


def test_parcel_resolver_builds_backend_owned_parent_path(app):
    with app.app_context():
        db.session.add_all([
            _region("province", "44", "广东省", area_code="44"),
            _region("city", "4402", "韶关市", area_code="4402", parent=("province", "44")),
            _region("county", "440281", "乐昌市", area_code="440281", parent=("city", "4402")),
            ParcelInfo(parcel_id="P001", legacy_parcel_code="A0001", area_code="440281"),
        ])
        db.session.commit()
        obj = SpatialObjectResolverRegistry().resolve(ObjectType.PARCEL, "P001", user_id=7)
        assert obj.display_name == "地块 P001"
        assert [item.type.value for item in obj.parent_path] == ["province", "city", "county"]
        assert obj.area_code == "440281"


def test_village_resolver_builds_full_administrative_path(app):
    with app.app_context():
        db.session.add_all([
            _region("province", "44", "广东省", area_code="44"),
            _region("city", "4402", "韶关市", area_code="4402", parent=("province", "44")),
            _region("county", "440281", "乐昌市", area_code="440281", parent=("city", "4402")),
            _region("township", "440281001", "乐城街道", area_code="440281001", parent=("county", "440281")),
            _region("village", "440281001208", "河南村", area_code="440281001208", parent=("township", "440281001")),
        ])
        db.session.commit()
        obj = SpatialObjectResolverRegistry().resolve(
            ObjectType.VILLAGE, "440281001208", user_id=7,
        )
        assert [item.type.value for item in obj.parent_path] == [
            "province", "city", "county", "township",
        ]


def test_disabled_region_is_invalid(app):
    with app.app_context():
        db.session.add(_region("county", "440281", "乐昌市", enabled=False))
        db.session.commit()
        with pytest.raises(AnalysisObjectInvalid):
            SpatialObjectResolverRegistry().resolve(ObjectType.COUNTY, "440281", user_id=7)


def test_parent_cycle_and_invalid_type_are_rejected(app):
    with app.app_context():
        db.session.add_all([
            _region("city", "A", "A", parent=("county", "B")),
            _region("county", "B", "B", parent=("city", "A")),
        ])
        db.session.commit()
        with pytest.raises(AnalysisObjectInvalid, match="循环"):
            SpatialObjectResolverRegistry().resolve(ObjectType.CITY, "A", user_id=7)
        db.session.query(SpatialRegionCatalog).delete()
        db.session.add(_region("county", "C", "C", parent=("bogus", "X")))
        db.session.commit()
        with pytest.raises(AnalysisObjectInvalid, match="类型非法"):
            SpatialObjectResolverRegistry().resolve(ObjectType.COUNTY, "C", user_id=7)


def test_broken_parent_chain_keeps_verified_path(app):
    with app.app_context():
        db.session.add_all([
            _region("city", "4402", "韶关市", parent=("province", "missing")),
            _region("county", "440281", "乐昌市", parent=("city", "4402")),
        ])
        db.session.commit()
        obj = SpatialObjectResolverRegistry().resolve(ObjectType.COUNTY, "440281", user_id=7)
        assert [(item.type.value, item.id) for item in obj.parent_path] == [("city", "4402")]


def test_parent_path_rejects_more_than_eight_levels(app):
    with app.app_context():
        rows = []
        for index in range(10):
            parent = ("zone", f"Z{index + 1}") if index < 9 else None
            rows.append(_region("zone", f"Z{index}", f"节点{index}", parent=parent))
        db.session.add_all(rows)
        db.session.commit()
        with pytest.raises(AnalysisObjectInvalid, match="最大深度"):
            SpatialObjectResolverRegistry().resolve(ObjectType.ZONE, "Z0", user_id=7)


def test_database_failure_is_503(app, monkeypatch):
    with app.app_context():
        resolver = SpatialObjectResolverRegistry()
        def fail(_object_id):
            raise sa.exc.OperationalError("select", {}, Exception("down"))
        monkeypatch.setattr(resolver._parcel_resolver, "resolve", fail)
        with pytest.raises(AnalysisObjectValidationUnavailable):
            resolver.resolve(ObjectType.PARCEL, "P001", user_id=7)


def test_access_policy_denial_is_invalid(app):
    class Deny:
        def can_access(self, **_kwargs):
            return False
    with app.app_context():
        db.session.add(_region("county", "440281", "乐昌市"))
        db.session.commit()
        with pytest.raises(AnalysisObjectInvalid, match="无权"):
            SpatialObjectResolverRegistry(Deny()).resolve(ObjectType.COUNTY, "440281", user_id=7)
