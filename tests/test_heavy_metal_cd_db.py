"""Cd 数据库后端（阶段 1）测试。

覆盖 openspec change ``add-heavy-metal-cd-database-backend`` 的守门点：

1. 输入映射只启用已确认字段，交换态不得当全量（纯逻辑）
2. 完整特征行通道的缺项识别（纯逻辑）
3. 预检失败整批拒绝，结果表零写入（PG）
4. 重跑幂等：行数不变、值为最新（PG）
5. 地块级覆盖：同地块多样点时旧行全部被替换（PG）
6. 读取还原：exp(ln) 一致，单位为 mg/kg、unit_status 保持 unverified（PG）
7. 单位标注：模型清单与预测结果都带 unit / unit_basis（纯逻辑）
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import PG_AVAILABLE  # noqa: E402

from framework.domain.other_models.heavy_metal_cd import (  # noqa: E402
    ARTIFACT_ROOT,
    _API_FIELDS,
    available_models,
    predict,
)
from framework.domain.other_models.heavy_metal_cd_db import (  # noqa: E402
    CONFIRMED_INDICATOR_MAP,
    FORBIDDEN_SOURCES,
    CdDatabaseError,
    build_inputs_from_row,
    map_indicators,
    read_results,
    run,
)

if PG_AVAILABLE:
    from framework.api.app import create_app  # noqa: E402

from flask import Flask  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from framework.models.user import db  # noqa: E402
from framework.models.cd_prediction import (  # noqa: E402
    CdCropPredictionResult,
    CdEffectivePredictionResult,
)


def _mean_row(model_id: str, parcel_id: str = "P0001", sample_id: str = "S0001") -> dict:
    """构造一行"输入 = 训练均值"的完整特征行（预测值可复现基准）。"""
    mean = np.load(str(next((ARTIFACT_ROOT / model_id).glob("*_mean.npy"))))
    row: dict = {"parcel_id": parcel_id, "sample_id": sample_id}
    for name, value in zip(_API_FIELDS[model_id], mean):
        row[name] = float(value)
    return row


# ---------------- 1. 纯逻辑：映射与单位 ----------------


def test_map_indicators_only_confirmed_fields():
    """只映射已确认的一对一字段；交换态不得当全量。"""
    indicators = {
        "available_potassium": 120.0,
        "available_phosphorus": 25.0,
        "total_n": 1.4,
        "exchangeable_ca": 900.0,
        "exchangeable_mg": 200.0,
        "soil_texture": "壤土",
    }
    result = map_indicators(indicators, "effective_cd")
    assert result["status"] == "need_input"
    assert set(result["data"]) == {"available_potassium", "available_phosphorus", "total_nitrogen"}
    assert "total_calcium" in result["missing_fields"]
    assert "total_magnesium" in result["missing_fields"]
    assert not set(FORBIDDEN_SOURCES) & {CONFIRMED_INDICATOR_MAP.get(f) for f in result["data"]}


def test_map_indicators_provenance_and_granularity():
    result = map_indicators(
        {"available_potassium": 100.0, "provenance": {"available_potassium": "measured"}},
        "crop_cd",
    )
    assert result["provenance"]["available_potassium"] == "measured"
    assert result["sample_granularity"] == "parcel"


def test_build_inputs_from_row_detects_missing():
    row = _mean_row("crop_cd")
    assert build_inputs_from_row(row, "crop_cd")["status"] == "ready"
    row.pop("solution")
    built = build_inputs_from_row(row, "crop_cd")
    assert built["status"] == "need_input"
    assert built["missing_fields"] == ["solution"]


def test_unknown_model_rejected():
    with pytest.raises(CdDatabaseError):
        map_indicators({}, "not_a_model")


def test_unit_labels_present():
    """模型清单与预测结果都必须带 unit=mg/kg、unit_basis 非空，unit_status 仍为 unverified。"""
    for item in available_models():
        assert item["unit"] == "mg/kg"
        assert item["unit_basis"]
        assert item["unit_status"] == "unverified"
    result = predict("crop_cd", _mean_row("crop_cd"))
    assert result["unit"] == "mg/kg"
    assert result["unit_basis"]
    assert result["unit_status"] == "unverified"
    assert result["log_prediction"] == pytest.approx(math.log(result["prediction"]), abs=1e-9)


# ---------------- 2. PG 集成 ----------------


@pytest.fixture
def cd_app():
    """写库测试的 app 上下文。

    PG 测试库可用时用真实 PostgreSQL；不可用时退化为内存 SQLite（StaticPool，
    保证同一内存库跨 session 可见）。两种后端都会真实执行
    ``DELETE ... IN (...)`` 与 ``bulk_insert_mappings``，因此写库路径一定被跑到，
    而不是以 skip 掩盖。
    """
    if PG_AVAILABLE:
        app = create_app("default")
        backend = "postgresql"
    else:
        app = Flask(__name__)
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        }
        db.init_app(app)
        backend = "sqlite"
    with app.app_context():
        CdCropPredictionResult.__table__.create(bind=db.engine, checkfirst=True)
        CdEffectivePredictionResult.__table__.create(bind=db.engine, checkfirst=True)
        db.session.query(CdCropPredictionResult).delete()
        db.session.query(CdEffectivePredictionResult).delete()
        db.session.commit()
        print(f"[cd_db] backend={backend}")
        yield app
        db.session.query(CdCropPredictionResult).delete()
        db.session.query(CdEffectivePredictionResult).delete()
        db.session.commit()


def test_incomplete_batch_writes_nothing(cd_app):
    """预检有缺项 → 整批拒绝、结果表零写入（也不以降级值入库）。"""
    good = _mean_row("crop_cd", "P0002", "S0002")
    bad = _mean_row("crop_cd", "P0003", "S0003")
    bad.pop("solution")
    report = run("crop_cd", rows=[good, bad], apply=True)
    assert report["status"] == "rejected"
    assert report["applied"] is False
    assert report["stored"] == 0
    assert [r["parcel_id"] for r in report["rejected"]] == ["P0003"]
    assert "solution" in report["rejected"][0]["missing_fields"]
    assert db.session.query(CdCropPredictionResult).count() == 0


def test_rerun_is_idempotent(cd_app):
    """同一地块重跑：行数不变，ln 值为第二次结果。"""
    row1 = _mean_row("crop_cd", "P0010", "S0010")
    first = run("crop_cd", rows=[row1], apply=True)
    assert first["status"] == "ok" and first["stored"] == 1
    ln_first = db.session.query(CdCropPredictionResult).one().ln_crop_cd

    row2 = dict(row1)
    row2["total_nitrogen"] = float(row1["total_nitrogen"]) * 2
    second = run("crop_cd", rows=[row2], apply=True)
    assert second["status"] == "ok"
    assert db.session.query(CdCropPredictionResult).count() == 1
    ln_second = db.session.query(CdCropPredictionResult).one().ln_crop_cd
    assert ln_second != ln_first


def test_parcel_level_replacement(cd_app):
    """同 parcel 多样点：后续只提交一个样点时，该地块旧样点行全部被替换。"""
    rows = [
        _mean_row("crop_cd", "P0020", "S0020a"),
        _mean_row("crop_cd", "P0020", "S0020b"),
    ]
    run("crop_cd", rows=rows, apply=True)
    assert db.session.query(CdCropPredictionResult).count() == 2

    run("crop_cd", rows=[_mean_row("crop_cd", "P0020", "S0020c")], apply=True)
    remaining = db.session.query(CdCropPredictionResult).all()
    assert len(remaining) == 1
    assert remaining[0].sample_id == "S0020c"


def test_read_results_restores_exp(cd_app):
    row = _mean_row("crop_cd", "P0030", "S0030")
    run("crop_cd", rows=[row], apply=True)
    stored = db.session.query(CdCropPredictionResult).one()
    payload = read_results("crop_cd", ["P0030"])
    assert len(payload) == 1
    item = payload[0]
    assert item["unit"] == "mg/kg"
    assert item["unit_status"] == "unverified"
    assert item["value"] == pytest.approx(math.exp(stored.ln_crop_cd), rel=1e-12)
    assert item["ln_crop_cd"] == pytest.approx(stored.ln_crop_cd, abs=1e-12)


def test_dry_run_does_not_write(cd_app):
    report = run("effective_cd", rows=[_mean_row("effective_cd", "P0040", "S0040")], apply=False)
    assert report["status"] == "ok"
    assert report["applied"] is False and report["stored"] == 0
    assert db.session.query(CdEffectivePredictionResult).count() == 0


def test_input_source_must_be_exclusive():
    with pytest.raises(CdDatabaseError):
        run("crop_cd", rows=[], parcel_ids=["P1"])
    with pytest.raises(CdDatabaseError):
        run("crop_cd")
