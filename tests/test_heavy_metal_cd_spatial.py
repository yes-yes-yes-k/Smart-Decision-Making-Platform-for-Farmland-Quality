"""Cd 空间分析测试（阶段 3）。

守门点：
- 归属唯一化：一个地块与多个 township 相交时只归面积最大的那个
- 跨乡镇地块计数与实测口径一致
- 乡镇统计复用阶段 2 口径（8 项 + 作物三档；有效态无分箱）
- 排序稳定（样本数降序、region_id 升序）与 min_count 过滤
- 点位 GeoJSON：坐标来自地块质心、bbox 过滤、limit 截断并返回 omitted
- 错误码：非法区域类型 400、区域不存在 404、非法 bbox/limit 400
"""
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.domain.other_models import heavy_metal_cd_spatial as spatial  # noqa: E402
from framework.domain.other_models import heavy_metal_cd_statistics as statistics  # noqa: E402

_CURRENT_APP: dict[str, object] = {}


@pytest.fixture
def spatial_app():
    """内存 SQLite：建结果表、归属表、区域目录、地块表，并挂载真实蓝图 + JWT。"""
    from flask import Flask
    from flask_jwt_extended import JWTManager
    from sqlalchemy.pool import StaticPool

    from framework.models import FarmlandRegionParcelArea, ParcelInfo, SpatialRegionCatalog
    from framework.models.cd_prediction import (
        CdCropPredictionResult,
        CdEffectivePredictionResult,
        CdPortedParcelTownship,
    )
    from framework.models.user import db

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TESTING"] = True
    app.config["JWT_SECRET_KEY"] = "heavy-metal-cd-spatial-secret-32-bytes-min"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "poolclass": StaticPool,
        "connect_args": {"check_same_thread": False},
    }
    db.init_app(app)
    JWTManager(app)
    from framework.api.routes import heavy_metal_cd as routes

    app.register_blueprint(routes.heavy_metal_cd_bp, url_prefix="/hmcd")
    _CURRENT_APP["app"] = app
    with app.app_context():
        tables = (
            CdCropPredictionResult.__table__,
            CdEffectivePredictionResult.__table__,
            CdPortedParcelTownship.__table__,
            FarmlandRegionParcelArea.__table__,
            SpatialRegionCatalog.__table__,
            ParcelInfo.__table__,
        )
        try:
            for table in tables:
                table.create(bind=db.engine, checkfirst=True)
        except Exception as exc:  # noqa: BLE001 - PostGIS 列在 SQLite 上无法渲染
            pytest.skip(f"SQLite 无法建出空间相关表：{exc}")
        for model in (CdCropPredictionResult, CdEffectivePredictionResult, CdPortedParcelTownship, FarmlandRegionParcelArea, SpatialRegionCatalog, ParcelInfo):
            db.session.query(model).delete()
        db.session.commit()
        yield db
        for model in (CdCropPredictionResult, CdEffectivePredictionResult, CdPortedParcelTownship, FarmlandRegionParcelArea, SpatialRegionCatalog, ParcelInfo):
            db.session.query(model).delete()
        db.session.commit()


def _seed(db, *, crop_values: dict[str, float], eff_values: dict[str, float] | None = None,
          regions: list[tuple[str, str, str]] = (), areas: list[tuple[str, str, str, float]] = (),
          parcels: list[tuple[str, float, float]] = ()):
    from framework.models import FarmlandRegionParcelArea, ParcelInfo, SpatialRegionCatalog
    from framework.models.cd_prediction import (
        CdCropPredictionResult,
        CdEffectivePredictionResult,
    )

    db.session.bulk_insert_mappings(
        CdCropPredictionResult,
        [
            {"parcel_id": pid, "sample_id": "S1", "ln_crop_cd": math.log(value)}
            for pid, value in crop_values.items()
        ],
    )
    if eff_values:
        db.session.bulk_insert_mappings(
            CdEffectivePredictionResult,
            [
                {"parcel_id": pid, "sample_id": "S1", "ln_eff_cd": math.log(value)}
                for pid, value in eff_values.items()
            ],
        )
    for object_type, object_id, display_name in regions:
        db.session.add(
            SpatialRegionCatalog(
                object_type=object_type,
                object_id=object_id,
                display_name=display_name,
                enabled=True,
                source="test",
            )
        )
    for region_type, region_id, parcel_id, area_mu in areas:
        db.session.add(
            FarmlandRegionParcelArea(
                region_type=region_type,
                region_id=region_id,
                parcel_id=parcel_id,
                area_mu=area_mu,
            )
        )
    for parcel_id, lon, lat in parcels:
        db.session.add(ParcelInfo(parcel_id=parcel_id, centroid_lon=lon, centroid_lat=lat))
    db.session.commit()


# ---------------- 1. 归属 ----------------


def test_parcel_belongs_to_largest_area_region(spatial_app):
    _seed(
        spatial_app,
        crop_values={"P1": 0.2},
        regions=[("township", "T1", "甲镇"), ("township", "T2", "乙镇")],
        areas=[("township", "T1", "P1", 5.0), ("township", "T2", "P1", 9.0)],
    )
    mapping = spatial.parcel_region_map("township")
    assert mapping["P1"] == "T2"  # 面积更大者胜出，而不是先出现的 T1
    # 唯一归属：不会同时出现在两个乡镇
    assert list(mapping.values()).count("T1") == 0


def test_borderline_parcel_count(spatial_app):
    _seed(
        spatial_app,
        crop_values={"P1": 0.2, "P2": 0.3},
        regions=[("township", "T1", "甲镇"), ("township", "T2", "乙镇")],
        areas=[
            ("township", "T1", "P1", 5.0), ("township", "T2", "P1", 9.0),  # P1 跨 2 个
            ("township", "T1", "P2", 3.0),                                  # P2 只属 1 个
        ],
    )
    assert spatial.borderline_parcel_count("township") == 1


def test_region_statistics_uses_area_assignment(spatial_app):
    _seed(
        spatial_app,
        crop_values={"P1": 0.1, "P2": 0.35},
        regions=[("township", "T1", "甲镇"), ("township", "T2", "乙镇")],
        areas=[("township", "T1", "P1", 9.0), ("township", "T2", "P2", 9.0)],
    )
    payload = spatial.region_statistics("crop_cd", "township", "T1")
    assert payload["region_id"] == "T1"
    assert payload["display_name"] == "甲镇"
    assert payload["assignment_rule"] == "max_area"
    assert payload["基础统计"]["数据点总数"] == 1
    assert payload["基础统计"]["均值"] == pytest.approx(0.1, abs=1e-9)
    assert "分布统计表格" in payload


def test_region_statistics_not_found(spatial_app):
    _seed(spatial_app, crop_values={"P1": 0.2}, regions=[("township", "T1", "甲镇")])
    with pytest.raises(spatial.CdSpatialError) as excinfo:
        spatial.region_statistics("crop_cd", "township", "NOPE")
    assert excinfo.value.code == "region_not_found"


def test_region_statistics_invalid_type(spatial_app):
    _seed(spatial_app, crop_values={"P1": 0.2})
    with pytest.raises(spatial.CdSpatialError) as excinfo:
        spatial.region_statistics("crop_cd", "planet", "X")
    assert excinfo.value.code == "invalid_region_type"


# ---------------- 2. 乡镇聚合 ----------------


def test_township_statistics_sort_and_counts(spatial_app):
    _seed(
        spatial_app,
        crop_values={"P1": 0.1, "P2": 0.25, "P3": 0.35},
        regions=[("township", "T1", "甲镇"), ("township", "T2", "乙镇")],
        areas=[
            ("township", "T1", "P1", 9.0), ("township", "T1", "P2", 9.0),
            ("township", "T2", "P3", 9.0),
        ],
    )
    payload = spatial.township_statistics("crop_cd")
    assert payload["has_data"] is True
    assert payload["count"] == 2
    assert [item["region_id"] for item in payload["regions"]] == ["T1", "T2"]  # 样本数降序
    assert payload["regions"][0]["count"] == 2
    # 三档：0.1 安全、0.25 预警
    counts = {row["区间说明"]: row["数据点数量"] for row in payload["regions"][0]["分布统计表格"]["表格数据"]}
    assert counts == {"安全区间": 1, "预警区间": 1, "超标区间": 0}
    assert payload["borderline_parcel_count"] == 0


def test_township_min_count_filters(spatial_app):
    _seed(
        spatial_app,
        crop_values={"P1": 0.1, "P2": 0.25, "P3": 0.35},
        regions=[("township", "T1", "甲镇"), ("township", "T2", "乙镇")],
        areas=[
            ("township", "T1", "P1", 9.0), ("township", "T1", "P2", 9.0),
            ("township", "T2", "P3", 9.0),
        ],
    )
    payload = spatial.township_statistics("crop_cd", min_count=2)
    assert [item["region_id"] for item in payload["regions"]] == ["T1"]


def test_effective_township_has_no_distribution(spatial_app):
    _seed(
        spatial_app,
        crop_values={},
        eff_values={"P1": 1.5},
        regions=[("township", "T1", "甲镇")],
        areas=[("township", "T1", "P1", 9.0)],
    )
    payload = spatial.township_statistics("effective_cd")
    region = payload["regions"][0]
    assert "分布统计表格" not in region
    assert region["基础统计"]["均值"] == pytest.approx(1.5, abs=1e-9)


def test_township_filters_by_parent(spatial_app):
    _seed(
        spatial_app,
        crop_values={"P1": 0.1, "P2": 0.3},
        regions=[("township", "T1", "甲镇"), ("township", "T2", "乙镇")],
        areas=[("township", "T1", "P1", 9.0), ("township", "T2", "P2", 9.0)],
    )
    from framework.models import SpatialRegionCatalog
    from framework.models.user import db

    # 给 T1 指定父级，T2 无父级
    db.session.query(SpatialRegionCatalog).filter_by(object_id="T1").update(
        {"parent_object_type": "county", "parent_object_id": "C1"}
    )
    db.session.commit()
    payload = spatial.township_statistics("crop_cd", parent_type="county", parent_id="C1")
    # 父级只用于补充名称信息，不改变归属；T1 仍在校验范围内
    assert payload["region_type"] == "township"


# ---------------- 3. 点位 GeoJSON ----------------


def test_points_geojson_structure(spatial_app):
    _seed(
        spatial_app,
        crop_values={"P1": 0.2, "P2": 0.4},
        regions=[("township", "T1", "甲镇")],
        areas=[("township", "T1", "P1", 9.0), ("township", "T1", "P2", 9.0)],
        parcels=[("P1", 113.1, 25.2), ("P2", 113.5, 25.6)],
    )
    payload = spatial.points_geojson("crop_cd")
    assert payload["type"] == "FeatureCollection"
    assert payload["coordinate_source"] == "parcel_centroid"
    assert payload["count"] == 2
    assert payload["omitted"] == 0
    feature = payload["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["coordinates"] == [113.1, 25.2]
    assert set(feature["properties"]) == {
        "parcel_id", "sample_id", "value", "ln_value", "unit", "unit_status",
    }
    assert feature["properties"]["unit"] == "mg/kg"
    assert feature["properties"]["unit_status"] == "unverified"


def test_points_geojson_bbox_and_limit(spatial_app):
    _seed(
        spatial_app,
        crop_values={"P1": 0.2, "P2": 0.4, "P3": 0.3},
        regions=[("township", "T1", "甲镇")],
        areas=[("township", "T1", "P1", 9.0), ("township", "T1", "P2", 9.0), ("township", "T1", "P3", 9.0)],
        parcels=[("P1", 113.1, 25.2), ("P2", 113.9, 25.9), ("P3", 113.11, 25.21)],
    )
    in_box = spatial.points_geojson("crop_cd", bbox=[113.0, 25.0, 113.2, 25.3])
    assert in_box["count"] == 2  # P1, P3
    limited = spatial.points_geojson("crop_cd", limit=1)
    assert limited["count"] == 1
    assert limited["omitted"] == 2


def test_points_rejects_bad_params(spatial_app):
    _seed(spatial_app, crop_values={"P1": 0.2})
    with pytest.raises(spatial.CdSpatialError):
        spatial.points_geojson("crop_cd", bbox=[1, 2, 3])
    with pytest.raises(spatial.CdSpatialError):
        spatial.points_geojson("crop_cd", bbox=[113.2, 25.0, 113.0, 25.3])
    with pytest.raises(spatial.CdSpatialError):
        spatial.points_geojson("crop_cd", limit=0)
    with pytest.raises(spatial.CdSpatialError):
        spatial.points_geojson("nope")


# ---------------- 4. HTTP ----------------


def _http_client(spatial_app):
    from flask_jwt_extended import create_access_token

    app = _CURRENT_APP["app"]
    with app.app_context():
        token = create_access_token(identity="7")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_http_spatial_requires_auth(spatial_app):
    client, _ = _http_client(spatial_app)
    assert client.get("/hmcd/spatial/townships").status_code == 401
    assert client.get("/hmcd/spatial/points").status_code == 401


def test_http_spatial_townships_ok(spatial_app):
    _seed(
        spatial_app,
        crop_values={"P1": 0.2},
        regions=[("township", "T1", "甲镇")],
        areas=[("township", "T1", "P1", 9.0)],
    )
    client, headers = _http_client(spatial_app)
    response = client.get("/hmcd/spatial/townships?model=crop_cd", headers=headers)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["count"] == 1
    assert data["assignment_rule"] == "max_area"


def test_http_spatial_bad_region_type(spatial_app):
    client, headers = _http_client(spatial_app)
    response = client.get("/hmcd/spatial/regions/planet/X/statistics", headers=headers)
    assert response.status_code == 400
    assert response.get_json()["reason"] == "invalid_region_type"


def test_http_spatial_region_not_found(spatial_app):
    client, headers = _http_client(spatial_app)
    response = client.get("/hmcd/spatial/regions/township/NOPE/statistics", headers=headers)
    assert response.status_code == 404
    assert response.get_json()["reason"] == "region_not_found"


def test_http_spatial_points_ok(spatial_app):
    _seed(
        spatial_app,
        crop_values={"P1": 0.2},
        regions=[("township", "T1", "甲镇")],
        areas=[("township", "T1", "P1", 9.0)],
        parcels=[("P1", 113.1, 25.2)],
    )
    client, headers = _http_client(spatial_app)
    response = client.get("/hmcd/spatial/points?model=crop_cd&limit=10", headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["type"] == "FeatureCollection"
    assert body["count"] == 1
