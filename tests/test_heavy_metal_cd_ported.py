"""移植数据集（阶段 D1）测试。

守门点：
- 命名空间前缀与自有限隔离
- 列映射的 AvaP/AvaK 交叉（按名字直觉取数会偏）
- `source` 过滤与 source_breakdown
- 移植数据的乡镇归属走独立表（不回退到面积表）
- 回滚只删 SGD_ 前缀
"""
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.domain.other_models import heavy_metal_cd_ported as ported  # noqa: E402
from framework.domain.other_models import heavy_metal_cd_spatial as spatial  # noqa: E402
from framework.domain.other_models import heavy_metal_cd_statistics as statistics  # noqa: E402


@pytest.fixture
def ported_app():
    from flask import Flask
    from sqlalchemy.pool import StaticPool

    from framework.models import (
        CdPortedParcelTownship,
        FarmlandRegionParcelArea,
        ParcelInfo,
        SpatialRegionCatalog,
    )
    from framework.models.cd_prediction import (
        CdCropPredictionResult,
        CdEffectivePredictionResult,
    )
    from framework.models.user import db

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "poolclass": StaticPool,
        "connect_args": {"check_same_thread": False},
    }
    db.init_app(app)
    with app.app_context():
        models = (
            CdCropPredictionResult,
            CdEffectivePredictionResult,
            CdPortedParcelTownship,
            SpatialRegionCatalog,
            FarmlandRegionParcelArea,
            ParcelInfo,
        )
        for model in models:
            model.__table__.create(bind=db.engine, checkfirst=True)
        for model in models:
            db.session.query(model).delete()
        db.session.commit()
        yield db
        for model in models:
            db.session.query(model).delete()
        db.session.commit()


def _seed(db, values: dict[str, float]):
    from framework.models.cd_prediction import CdCropPredictionResult

    db.session.bulk_insert_mappings(
        CdCropPredictionResult,
        [
            {"parcel_id": pid, "sample_id": f"{pid}_S0", "ln_crop_cd": math.log(value)}
            for pid, value in values.items()
        ],
    )
    db.session.commit()


# ---------------- 1. 纯逻辑 ----------------


def test_namespace_prefix():
    assert ported.ported_parcel_id(7) == "SGD_7"
    assert ported.ported_sample_id(7, 0) == "SGD_7_0"
    assert not ported.ported_parcel_id(7).replace("SGD_", "").startswith("SGD")


def test_column_map_crosses_avap_avak():
    """作物 Cd 的 AvaP/AvaK 在 ORM 与 DB 列名间是交叉的（按名字直取会偏 +0.38）。"""
    crop = ported.DB_FEATURE_COLUMNS["crop_cd"]
    assert crop["available_phosphorus"] == "AvaK_IDW"
    assert crop["available_potassium"] == "AvaP_IDW"
    # 有效态不交叉
    eff = ported.DB_FEATURE_COLUMNS["effective_cd"]
    assert eff["available_potassium"] == "AvaK_IDW"
    assert eff["available_phosphorus"] == "AvaP_IDW"


def test_feature_columns_cover_all_model_fields():
    from framework.domain.other_models.heavy_metal_cd import _API_FIELDS

    for model_id, fields in _API_FIELDS.items():
        assert set(ported.DB_FEATURE_COLUMNS[model_id]) == set(fields), model_id


# ---------------- 2. source 维度 ----------------


def test_invalid_source_raises(ported_app):
    with pytest.raises(statistics.CdStatisticsError) as excinfo:
        statistics.normalize_source("somewhere")
    assert excinfo.value.code == "invalid_source"


def test_source_filter_and_breakdown(ported_app):
    _seed(ported_app, {"1": 0.1, "2": 0.2, "SGD_1": 0.3, "SGD_2": 0.4, "SGD_3": 0.5})
    breakdown = statistics.source_breakdown("crop_cd")
    assert breakdown == {"native": 2, "ported": 3}

    native_values = statistics.collect_values("crop_cd", source="native")
    ported_values = statistics.collect_values("crop_cd", source="ported")
    all_values = statistics.collect_values("crop_cd", source="all")
    assert len(native_values) == 2 and len(ported_values) == 3 and len(all_values) == 5

    payload = statistics.crop_cd_statistics(source="ported")
    assert payload["source"] == "ported"
    assert payload["基础统计"]["数据点总数"] == 3
    assert payload["source_breakdown"] == {"native": 2, "ported": 3}


def test_list_results_and_csv_respect_source(ported_app):
    _seed(ported_app, {"1": 0.1, "SGD_1": 0.4})
    page = statistics.list_results("crop_cd", source="ported")
    assert page["source"] == "ported"
    assert page["count"] == 1
    assert page["items"][0]["parcel_id"] == "SGD_1"

    payload, total = statistics.export_csv("crop_cd", source="native")
    assert total == 1
    text = payload.decode("utf-8-sig")
    assert "SGD_" not in text


# ---------------- 3. 空间归属 ----------------


def test_township_uses_ported_assignment_table(ported_app):
    from framework.models import CdPortedParcelTownship, ParcelInfo, SpatialRegionCatalog

    _seed(ported_app, {"SGD_1": 0.2, "SGD_2": 0.35})
    ported_app.session.add(
        SpatialRegionCatalog(
            object_type="township", object_id="T1", display_name="甲镇", enabled=True, source="test"
        )
    )
    ported_app.session.bulk_insert_mappings(
        ParcelInfo,
        [
            {"parcel_id": "SGD_1", "centroid_lon": 113.1, "centroid_lat": 25.2},
            {"parcel_id": "SGD_2", "centroid_lon": 113.2, "centroid_lat": 25.3},
        ],
    )
    ported_app.session.bulk_insert_mappings(
        CdPortedParcelTownship,
        [
            {"parcel_id": "SGD_1", "township_id": "T1", "township_name": "甲镇", "distance_m": 0},
            {"parcel_id": "SGD_2", "township_id": "T1", "township_name": "甲镇", "distance_m": 12.5},
        ],
    )
    ported_app.session.commit()

    payload = spatial.township_statistics("crop_cd", source="ported")
    assert payload["assignment_rule"] == "point_in_polygon"
    assert payload["ported_fallback_count"] == 1
    assert payload["count"] == 1
    region = payload["regions"][0]
    assert region["region_id"] == "T1"
    assert region["count"] == 2
    assert region["基础统计"]["数据点总数"] == 2


def test_ported_assignment_unavailable_for_non_township(ported_app):
    payload = spatial.township_statistics("crop_cd", region_type="county", source="ported")
    assert payload["ported_unavailable_for_region_type"] is True
    assert payload["count"] == 0


# ---------------- 4. 回滚 ----------------


def test_rollback_only_removes_ported(ported_app):
    from framework.models import CdPortedParcelTownship, ParcelInfo
    from framework.models.cd_prediction import CdCropPredictionResult

    _seed(ported_app, {"1": 0.1, "SGD_1": 0.4})
    ported_app.session.add_all(
        [
            ParcelInfo(parcel_id="1", centroid_lon=113.0, centroid_lat=25.0),
            ParcelInfo(parcel_id="SGD_1", centroid_lon=113.1, centroid_lat=25.1),
            CdPortedParcelTownship(parcel_id="SGD_1", township_id="T1", distance_m=0),
        ]
    )
    ported_app.session.commit()

    affected = ported.rollback()
    assert affected["cd_crop_prediction_result"] == 1
    assert affected["cd_ported_parcel_township"] == 1
    assert affected["parcel_info"] == 1
    remaining = [row.parcel_id for row in ported_app.session.query(CdCropPredictionResult).all()]
    assert remaining == ["1"]
    assert ported_app.session.query(ParcelInfo).count() == 1
