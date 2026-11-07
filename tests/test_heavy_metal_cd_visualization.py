"""Cd 可视化测试（阶段 4）。

守门点：
- 参数校验（模型/区域/插值/分辨率）返回机器可读错误码
- 结果表 + 地块质心 → 栅格 → 分级地图 + 直方图 + meta.json 全链路
- 作物三档图例（threshold）；有效态分位数图例（quantile）
- 插值默认关闭、开启后 meta 标注且仍回扣掩膜
- 单值栅格不因密度估计失败而报错
- 空数据 / 模板范围外无数据 → 错误码，不产出空图
- 区域过滤只统计归属该区域的地块
- 产物列表与下载路径校验（非法 ID/kind、越界）
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.domain.other_models import heavy_metal_cd_visualization as visualization  # noqa: E402


@pytest.fixture
def viz_app(tmp_path, monkeypatch):
    """内存 SQLite：结果表 + 地块表 + 区域目录；产物目录指向 tmp_path。"""
    from flask import Flask
    from flask_jwt_extended import JWTManager
    from sqlalchemy.pool import StaticPool

    from framework.models import ParcelInfo, SpatialRegionCatalog
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
    app.config["JWT_SECRET_KEY"] = "heavy-metal-cd-viz-secret-32-bytes-min"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "poolclass": StaticPool,
        "connect_args": {"check_same_thread": False},
    }
    db.init_app(app)
    JWTManager(app)

    monkeypatch.setattr(visualization, "VISUALIZATION_ROOT", tmp_path / "cd_visualization")

    with app.app_context():
        for table in (
            CdCropPredictionResult.__table__,
            CdEffectivePredictionResult.__table__,
            CdPortedParcelTownship.__table__,
            SpatialRegionCatalog.__table__,
            ParcelInfo.__table__,
        ):
            table.create(bind=db.engine, checkfirst=True)
        for model in (
            CdCropPredictionResult,
            CdEffectivePredictionResult,
            CdPortedParcelTownship,
            SpatialRegionCatalog,
            ParcelInfo,
        ):
            db.session.query(model).delete()
        db.session.commit()
        yield db
        for model in (
            CdCropPredictionResult,
            CdEffectivePredictionResult,
            CdPortedParcelTownship,
            SpatialRegionCatalog,
            ParcelInfo,
        ):
            db.session.query(model).delete()
        db.session.commit()


def _seed(db, parcels, crop_values, eff_values=None, townships=()):
    """parcels: [(parcel_id, lon, lat)]；crop_values: {parcel_id: mg/kg}。"""
    from framework.models import ParcelInfo, SpatialRegionCatalog
    from framework.models.cd_prediction import (
        CdCropPredictionResult,
        CdEffectivePredictionResult,
    )

    db.session.bulk_insert_mappings(
        ParcelInfo,
        [
            {"parcel_id": pid, "centroid_lon": lon, "centroid_lat": lat}
            for pid, lon, lat in parcels
        ],
    )
    db.session.bulk_insert_mappings(
        CdCropPredictionResult,
        [
            {"parcel_id": pid, "sample_id": pid, "ln_crop_cd": float(np.log(value))}
            for pid, value in crop_values.items()
        ],
    )
    if eff_values:
        db.session.bulk_insert_mappings(
            CdEffectivePredictionResult,
            [
                {"parcel_id": pid, "sample_id": pid, "ln_eff_cd": float(np.log(value))}
                for pid, value in eff_values.items()
            ],
        )
    for object_id, name in townships:
        db.session.bulk_insert_mappings(
            SpatialRegionCatalog,
            [
                {
                    "object_type": "township",
                    "object_id": object_id,
                    "display_name": name,
                    "source": "test",
                    "enabled": True,
                }
            ],
        )
    db.session.commit()


# 模板范围 112.85–114.74E / 23.89–25.53N，取范围内的四个点
_INSIDE = [
    ("P1", 113.30, 25.10),
    ("P2", 113.35, 25.12),
    ("P3", 113.40, 25.08),
    ("P4", 113.36, 25.15),
]


def test_parameter_validation(viz_app):
    with pytest.raises(visualization.CdVisualizationError) as exc:
        visualization.generate("unknown_model")
    assert exc.value.code == "unknown_model"

    with pytest.raises(visualization.CdVisualizationError) as exc:
        visualization.generate("crop_cd", region_type="township")
    assert exc.value.code == "invalid_region"

    with pytest.raises(visualization.CdVisualizationError) as exc:
        visualization.generate("crop_cd", region_type="not_a_type", region_id="x")
    assert exc.value.code == "invalid_region_type"

    with pytest.raises(visualization.CdVisualizationError) as exc:
        visualization.generate("crop_cd", interpolation_method="spline")
    assert exc.value.code == "invalid_interpolation_method"

    with pytest.raises(visualization.CdVisualizationError) as exc:
        visualization.generate("crop_cd", resolution_factor=0.1)
    assert exc.value.code == "invalid_resolution_factor"


def test_generate_crop_map_and_meta(viz_app):
    _seed(viz_app, _INSIDE, {p[0]: 0.1 + 0.1 * i for i, p in enumerate(_INSIDE)})
    meta = visualization.generate("crop_cd", resolution_factor=1)

    assert meta["model_id"] == "crop_cd"
    assert meta["legend"]["mode"] == "threshold"
    assert meta["legend"]["bounds"][:3] == [0.0, 0.2, 0.3]
    assert meta["interpolated"] is False
    assert meta["boundary_source"] == "convex_hull"
    assert meta["data"]["row_count"] == 4
    assert meta["data"]["unit"] == "mg/kg"
    assert meta["statistics"]["valid_pixels"] > 0

    out_dir = visualization.VISUALIZATION_ROOT / "crop_cd" / meta["artifact_id"]
    assert (out_dir / "map.jpg").exists()
    assert (out_dir / "histogram.jpg").exists()
    saved = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    assert saved["artifact_id"] == meta["artifact_id"]


def test_generate_with_interpolation(viz_app):
    _seed(viz_app, _INSIDE, {p[0]: 0.05 + 0.08 * i for i, p in enumerate(_INSIDE)})
    meta = visualization.generate(
        "crop_cd", resolution_factor=2, enable_interpolation=True, interpolation_method="linear"
    )
    assert meta["interpolated"] is True
    assert meta["request"]["interpolation_method"] == "linear"
    out_dir = visualization.VISUALIZATION_ROOT / "crop_cd" / meta["artifact_id"]
    assert (out_dir / "map.jpg").exists()


def test_single_value_histogram(viz_app):
    _seed(viz_app, _INSIDE, {p[0]: 0.25 for p in _INSIDE})
    meta = visualization.generate("crop_cd", resolution_factor=1)
    out_dir = visualization.VISUALIZATION_ROOT / "crop_cd" / meta["artifact_id"]
    assert (out_dir / "histogram.jpg").exists()


def test_empty_data(viz_app):
    with pytest.raises(visualization.CdVisualizationError) as exc:
        visualization.generate("crop_cd", resolution_factor=1)
    assert exc.value.code == "no_data"


def test_out_of_template(viz_app):
    # 全部点在模板范围（110E, 20N）之外
    _seed(viz_app, [("X1", 110.0, 20.0), ("X2", 110.1, 20.1)], {"X1": 0.1, "X2": 0.2})
    with pytest.raises(visualization.CdVisualizationError) as exc:
        visualization.generate("crop_cd", resolution_factor=1)
    assert exc.value.code == "no_data_in_template"


def test_region_filter(viz_app):
    """区域过滤：township=T1 的地块（P1/P2）与 township=T2 的地块（P3/P4）。"""
    from framework.models import FarmlandRegionParcelArea
    from framework.models.user import db

    FarmlandRegionParcelArea.__table__.create(bind=db.engine, checkfirst=True)
    db.session.query(FarmlandRegionParcelArea).delete()
    db.session.bulk_insert_mappings(
        FarmlandRegionParcelArea,
        [
            {"parcel_id": "P1", "region_type": "township", "region_id": "T1", "area_mu": 10.0},
            {"parcel_id": "P2", "region_type": "township", "region_id": "T1", "area_mu": 8.0},
            {"parcel_id": "P3", "region_type": "township", "region_id": "T2", "area_mu": 9.0},
            {"parcel_id": "P4", "region_type": "township", "region_id": "T2", "area_mu": 7.0},
        ],
    )
    db.session.commit()
    _seed(
        viz_app,
        _INSIDE,
        {p[0]: 0.1 + 0.1 * i for i, p in enumerate(_INSIDE)},
        townships=[("T1", "乡一"), ("T2", "乡二")],
    )
    meta = visualization.generate(
        "crop_cd", region_type="township", region_id="T1", resolution_factor=1
    )
    assert meta["data"]["row_count"] == 2
    assert meta["request"]["region_type"] == "township"
    assert meta["request"]["region_id"] == "T1"


def test_artifact_path_validation(viz_app):
    _seed(viz_app, _INSIDE, {p[0]: 0.2 for p in _INSIDE})
    meta = visualization.generate("crop_cd", resolution_factor=1)

    path, mime = visualization.artifact_path(meta["artifact_id"], "map")
    assert path.exists() and mime == "image/jpeg"

    with pytest.raises(visualization.CdVisualizationError) as exc:
        visualization.artifact_path("../etc/passwd", "map")
    assert exc.value.code == "invalid_artifact_id"

    with pytest.raises(visualization.CdVisualizationError) as exc:
        visualization.artifact_path(meta["artifact_id"], "shell")
    assert exc.value.code == "invalid_kind"

    with pytest.raises(visualization.CdVisualizationError) as exc:
        visualization.artifact_path("0" * 32, "map")
    assert exc.value.code == "artifact_not_found"


def test_list_artifacts(viz_app):
    _seed(viz_app, _INSIDE, {p[0]: 0.1 + 0.1 * i for i, p in enumerate(_INSIDE)})
    first = visualization.generate("crop_cd", resolution_factor=1)

    payload = visualization.list_artifacts(model_id="crop_cd")
    assert payload["count"] == 1
    assert payload["items"][0]["artifact_id"] == first["artifact_id"]

    filtered = visualization.list_artifacts(model_id="crop_cd", region_type="township")
    assert filtered["count"] == 0

    with pytest.raises(visualization.CdVisualizationError) as exc:
        visualization.list_artifacts(limit=0)
    assert exc.value.code == "invalid_limit"
