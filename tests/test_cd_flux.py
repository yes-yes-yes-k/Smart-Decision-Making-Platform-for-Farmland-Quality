"""Cd 通量核算测试（阶段 5）。

守门点：
- CSV 导入：必需列校验、同键覆盖、非法行跳过
- 计算：In/Out/Net/End 公式、bd020_90/initial_cd 回退计数、重复计算幂等
- 分布：end_cd 三档、net_cd 互斥（占比和 ≤100%）、in/out 相对分级标注
- 点位 GeoJSON、明细分页、CSV 导出与超限报错
- 区域过滤、空数据语义
"""
from __future__ import annotations

import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.domain.other_models import cd_flux  # noqa: E402


@pytest.fixture
def flux_app(tmp_path, monkeypatch):
    from flask import Flask
    from flask_jwt_extended import JWTManager
    from sqlalchemy.pool import StaticPool

    from framework.models import (
        CdFluxInput,
        CdFluxOutput,
        CdPortedParcelTownship,
        FarmlandRegionParcelArea,
        ParcelInfo,
        SpatialRegionCatalog,
    )
    from framework.models.user import db

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TESTING"] = True
    app.config["JWT_SECRET_KEY"] = "cd-flux-secret-32-bytes-min"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "poolclass": StaticPool,
        "connect_args": {"check_same_thread": False},
    }
    db.init_app(app)
    JWTManager(app)

    from framework.domain.other_models import heavy_metal_cd_visualization as viz

    monkeypatch.setattr(viz, "VISUALIZATION_ROOT", tmp_path / "cd_visualization")

    with app.app_context():
        for table in (
            CdFluxInput.__table__,
            CdFluxOutput.__table__,
            CdPortedParcelTownship.__table__,
            ParcelInfo.__table__,
            SpatialRegionCatalog.__table__,
            FarmlandRegionParcelArea.__table__,
        ):
            table.create(bind=db.engine, checkfirst=True)
        for model in (
            CdFluxInput,
            CdFluxOutput,
            CdPortedParcelTownship,
            ParcelInfo,
            SpatialRegionCatalog,
            FarmlandRegionParcelArea,
        ):
            db.session.query(model).delete()
        db.session.commit()
        yield db
        for model in (
            CdFluxInput,
            CdFluxOutput,
            CdPortedParcelTownship,
            ParcelInfo,
            SpatialRegionCatalog,
            FarmlandRegionParcelArea,
        ):
            db.session.query(model).delete()
        db.session.commit()


_HEADER = "parcel_id,sample_id,initial_cd,DQCJ_Cd,GGS_Cd,NCP_Cd,DX_Cd,DB_Cd,ZL_Cd,JG_Cd,bd020_90\n"


def _csv(*rows: str) -> bytes:
    return (_HEADER + "\n".join(rows) + "\n").encode("utf-8")


def _seed_parcels(db, items):
    from framework.models import ParcelInfo

    db.session.bulk_insert_mappings(
        ParcelInfo,
        [{"parcel_id": pid, "centroid_lon": lon, "centroid_lat": lat} for pid, lon, lat in items],
    )
    db.session.commit()


def test_import_and_overwrite(flux_app):
    db = flux_app
    first = cd_flux.import_csv(_csv("P1,S1,2000,1.0,2.0,3.0,0.023,0.368,0,0,1.2", "P2,S2,2000,0.5,0.5,0.5,0.023,0.368,0,0,1.0"))
    assert first["inserted"] == 2 and first["updated"] == 0

    second = cd_flux.import_csv(_csv("P1,S1,2100,1.5,2.5,3.5,0.023,0.368,0,0,1.3"))
    assert second["inserted"] == 0 and second["updated"] == 1

    from framework.models import CdFluxInput

    row = db.session.query(CdFluxInput).filter_by(parcel_id="P1", sample_id="S1").one()
    assert row.initial_cd == 2100 and row.atmospheric_deposition == 1.5 and row.bd020_90 == 1.3


def test_import_missing_columns(flux_app):
    bad = b"parcel_id,sample_id,initial_cd\nP1,S1,2000\n"
    with pytest.raises(cd_flux.CdFluxError) as exc:
        cd_flux.import_csv(bad)
    assert exc.value.code.startswith("missing_columns")


def test_calculate_formula_and_fallback(flux_app):
    db = flux_app
    # P1 完整；P2 缺 bd020_90 与 initial_cd（回退计数）
    cd_flux.import_csv(_csv("P1,S1,2000,1.0,2.0,3.0,0.023,0.368,0,0,1.0", "P2,S2,,0.5,0.5,0.5,0.023,0.368,0,0,"))
    result = cd_flux.calculate()
    assert result["has_data"] is True
    assert result["input_rows"] == 2
    assert result["inserted"] == 2
    assert result["fallback"]["bd020_90"] == 1
    assert result["fallback"]["initial_cd"] == 1

    from framework.models import CdFluxOutput

    row = db.session.query(CdFluxOutput).filter_by(parcel_id="P1", sample_id="S1").one()
    assert row.in_cd == pytest.approx(6.0)
    assert row.out_cd == pytest.approx(0.023 + 0.368)
    assert row.net_cd == pytest.approx(6.0 - 0.391)
    assert row.end_cd == pytest.approx((2000 + 5.609) / (2000 * 1.0))

    row2 = db.session.query(CdFluxOutput).filter_by(parcel_id="P2", sample_id="S2").one()
    assert row2.end_cd == pytest.approx((0 + 1.109) / (2000 * 1.0))


def test_calculate_idempotent(flux_app):
    db = flux_app
    cd_flux.import_csv(_csv("P1,S1,2000,1,1,1,0.1,0.1,0,0,1.0"))
    first = cd_flux.calculate()
    second = cd_flux.calculate()

    from framework.models import CdFluxOutput

    assert db.session.query(CdFluxOutput).count() == 1
    assert first["inserted"] == 1 and second["updated"] == 1 and second["inserted"] == 0


def test_distribution_mutually_exclusive(flux_app):
    db = flux_app
    # net_cd: -10 → 负；0 → 平衡；10 → 正
    cd_flux.import_csv(
        _csv(
            "P1,S1,2000,1,1,1,0,16,0,0,1.0",   # in=3 out=16 net=-13
            "P2,S2,2000,1,1,1,0,3,0,0,1.0",    # in=3 out=3 net=0
            "P3,S3,2000,1,1,1,0,1,0,0,1.0",    # in=3 out=1 net=2
            "P4,S4,2000,1,1,1,0,0,0,0,1.0",    # in=3 out=0 net=3
            "P5,S5,2000,1,1,1,1,0,0,0,1.0",    # in=3 out=1 net=2
            "P6,S6,2000,10,10,10,0,1,0,0,1.0", # in=30 out=1 net=29
        )
    )
    cd_flux.calculate()
    stats = cd_flux.statistics("net_cd")
    dist = stats["分布统计"]
    key = [k for k in dist if k.startswith(("负", "接近", "正"))]
    total_ratio = sum(dist[k]["占比"] for k in key)
    assert total_ratio <= 100.0 + 1e-9
    assert dist["mutually_exclusive"] is True


def test_relative_distribution_flag(flux_app):
    db = flux_app
    cd_flux.import_csv(_csv("P1,S1,2000,1,1,1,1,1,0,0,1.0"))
    cd_flux.calculate()
    stats = cd_flux.statistics("in_cd")
    assert stats["分布统计"]["relative"] is True


def test_end_cd_thresholds(flux_app):
    db = flux_app
    # end_cd = (2000 + net)/2000 ≈ 1.0（安全档），造一个高值
    cd_flux.import_csv(_csv("P1,S1,2000,1,1,1,0,0,0,0,1.0", "P2,S2,0,0,0,0,0,0,0,0,0.0001"))
    cd_flux.calculate()
    stats = cd_flux.statistics("end_cd")
    dist = stats["分布统计"]
    assert dist["threshold_source"] == "GB 15618-2018"
    assert sum(v["占比"] for v in dist.values() if isinstance(v, dict)) <= 100.0 + 1e-9


def test_points_and_results(flux_app):
    db = flux_app
    _seed_parcels(db, [("P1", 113.3, 25.1), ("P2", 113.4, 25.2)])
    cd_flux.import_csv(_csv("P1,S1,2000,1,1,1,0,0,0,0,1.0", "P2,S2,2000,2,2,2,0,0,0,0,1.0"))
    cd_flux.calculate()
    points = cd_flux.points_geojson("net_cd")
    assert points["count"] == 2
    assert points["coordinate_source"] == "parcel_centroid"
    assert all("value" in f["properties"] for f in points["features"])

    rows = cd_flux.list_results("in_cd", limit=1)
    assert rows["total"] == 2 and len(rows["rows"]) == 1


def test_export_csv_and_limit(flux_app):
    db = flux_app
    cd_flux.import_csv(_csv("P1,S1,2000,1,1,1,0,0,0,0,1.0"))
    cd_flux.calculate()
    text, count = cd_flux.export_csv("in_cd")
    assert count == 1
    assert "parcel_id,sample_id,in_cd,unit" in text
    assert "g/ha/a" in text
    with pytest.raises(cd_flux.CdFluxError) as exc:
        cd_flux.export_csv("in_cd", max_rows=0)
    assert exc.value.code == "too_many_rows"


def test_empty_data(flux_app):
    result = cd_flux.calculate()
    assert result["has_data"] is False
    stats = cd_flux.statistics("in_cd")
    assert stats["has_data"] is False


def test_region_filter(flux_app):
    db = flux_app
    from framework.models import FarmlandRegionParcelArea

    db.session.bulk_insert_mappings(
        FarmlandRegionParcelArea,
        [
            {"parcel_id": "P1", "region_type": "township", "region_id": "T1", "area_mu": 10.0},
            {"parcel_id": "P2", "region_type": "township", "region_id": "T2", "area_mu": 9.0},
        ],
    )
    db.session.commit()
    from framework.models import SpatialRegionCatalog

    db.session.bulk_insert_mappings(
        SpatialRegionCatalog,
        [
            {"object_type": "township", "object_id": "T1", "display_name": "乡一", "source": "test", "enabled": True},
            {"object_type": "township", "object_id": "T2", "display_name": "乡二", "source": "test", "enabled": True},
        ],
    )
    db.session.commit()
    cd_flux.import_csv(_csv("P1,S1,2000,1,1,1,0,0,0,0,1.0", "P2,S2,2000,2,2,2,0,0,0,0,1.0"))
    cd_flux.calculate()
    stats = cd_flux.statistics("in_cd", region_type="township", region_id="T1")
    assert stats["count"] == 1
