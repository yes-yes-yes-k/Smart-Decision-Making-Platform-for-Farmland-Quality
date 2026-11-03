"""Cd 统计服务与 HTTP 端点测试（阶段 2）。

守门点：
- 8 项基础统计与原系统算法一致（总体标准差、下标直取分位数、round 6）
- 作物 Cd 三档分布：边界值归属、负值计入超标并单独计数
- 空数据返回结构化空态（has_data=false），不是异常
- 明细分页、CSV（UTF-8 BOM + 固定列序 + 超限拒绝）
- area_code 过滤真正生效（JOIN parcel_info）
- HTTP：全部端点要求认证；参数非法 400；CSV 超限 413
"""
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.domain.other_models import heavy_metal_cd_statistics as stats  # noqa: E402

# ---------------- 1. 纯算法 ----------------


def test_basic_statistics_matches_hand_calc():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = stats.basic_statistics(values)
    assert result["数据点总数"] == 5
    assert result["均值"] == 3.0
    assert result["中位数"] == 3.0
    assert result["最小值"] == 1.0
    assert result["最大值"] == 5.0
    # 下标直取：int(5*0.25)=1 -> 2.0；int(5*0.75)=3 -> 4.0（不是线性插值的 2.0/4.0 巧合相同）
    assert result["25%分位数"] == 2.0
    assert result["75%分位数"] == 4.0


def test_standard_deviation_is_population_not_sample():
    """总体标准差（除以 n）：[1,2,3,4] -> sqrt(1.25)=1.118034，样本标准差会是 1.290994。"""
    result = stats.basic_statistics([1.0, 2.0, 3.0, 4.0])
    assert result["标准差"] == pytest.approx(1.118034, abs=1e-6)
    assert result["标准差"] != pytest.approx(1.290994, abs=1e-6)


def test_quantile_is_index_based_not_linear():
    """下标直取与 numpy 线性插值在非整除样本上会不同，必须复现下标法。"""
    values = [float(i) for i in range(1, 11)]  # 1..10
    result = stats.basic_statistics(values)
    # int(10*0.25)=2 -> sorted[2] = 3.0（numpy 线性插值给 3.25）
    assert result["25%分位数"] == 3.0
    # int(10*0.75)=7 -> sorted[7] = 8.0（numpy 给 7.75）
    assert result["75%分位数"] == 8.0


def test_empty_statistics_is_null_not_zero():
    result = stats.basic_statistics([])
    assert result["数据点总数"] == 0
    assert all(result[key] is None for key in stats.BASIC_STAT_KEYS if key != "数据点总数")


def test_distribution_bands_and_negative_values():
    values = [0.1, 0.25, 0.35, -0.5]
    dist = stats.crop_cd_distribution(values)
    counts = {row["区间说明"]: row["数据点数量"] for row in dist["表格数据"]}
    assert counts == {"安全区间": 1, "预警区间": 1, "超标区间": 2}
    assert dist["invalid_count"] == 1
    assert dist["总数据点数"] == 4
    assert dist["汇总"]["安全区间占比"] == "25.0%"
    assert dist["threshold_note"]


def test_distribution_boundaries():
    """0.2 属预警、0.3 属超标、0.1999 属安全。"""
    dist = stats.crop_cd_distribution([0.2, 0.3, 0.1999])
    counts = {row["区间说明"]: row["数据点数量"] for row in dist["表格数据"]}
    assert counts == {"安全区间": 1, "预警区间": 1, "超标区间": 1}
    assert dist["invalid_count"] == 0


def test_distribution_empty_is_zeroed():
    dist = stats.crop_cd_distribution([])
    assert dist["总数据点数"] == 0
    assert all(row["数据点数量"] == 0 and row["占比"] == 0 for row in dist["表格数据"])


# ---------------- 2. 服务层（内存 SQLite 真实执行查询） ----------------


@pytest.fixture
def cd_app():
    from flask import Flask
    from sqlalchemy.pool import StaticPool

    from framework.models.user import db
    from framework.models.cd_prediction import (
        CdCropPredictionResult,
        CdEffectivePredictionResult,
    )

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "poolclass": StaticPool,
        "connect_args": {"check_same_thread": False},
    }
    db.init_app(app)
    with app.app_context():
        CdCropPredictionResult.__table__.create(bind=db.engine, checkfirst=True)
        CdEffectivePredictionResult.__table__.create(bind=db.engine, checkfirst=True)
        db.session.query(CdCropPredictionResult).delete()
        db.session.query(CdEffectivePredictionResult).delete()
        db.session.commit()
        yield db
        db.session.query(CdCropPredictionResult).delete()
        db.session.query(CdEffectivePredictionResult).delete()
        db.session.commit()


def _insert(db, model_id: str, rows: list[tuple[str, str, float]]):
    from framework.models.cd_prediction import (
        CdCropPredictionResult,
        CdEffectivePredictionResult,
    )

    table = CdCropPredictionResult if model_id == "crop_cd" else CdEffectivePredictionResult
    column = "ln_crop_cd" if model_id == "crop_cd" else "ln_eff_cd"
    db.session.bulk_insert_mappings(
        table,
        [
            {"parcel_id": parcel_id, "sample_id": sample_id, column: log_value}
            for parcel_id, sample_id, log_value in rows
        ],
    )
    db.session.commit()


def test_empty_table_returns_has_data_false(cd_app):
    payload = stats.crop_cd_statistics()
    assert payload["has_data"] is False
    assert payload["基础统计"]["数据点总数"] == 0
    assert payload["基础统计"]["均值"] is None
    assert payload["分布统计表格"]["总数据点数"] == 0
    assert payload["statistics_scope"] == "crop_cd_distribution"
    assert payload["queried_at_is"] == "query_time"
    # 空数据时有效态统计同样不报错
    assert stats.effective_cd_statistics()["has_data"] is False


def test_crop_statistics_values_are_exp_restored(cd_app):
    logs = [math.log(0.1), math.log(0.25), math.log(0.35)]
    _insert(cd_app, "crop_cd", [(f"P{i}", "S1", v) for i, v in enumerate(logs)])
    payload = stats.crop_cd_statistics()
    assert payload["has_data"] is True
    assert payload["基础统计"]["数据点总数"] == 3
    assert payload["基础统计"]["最小值"] == pytest.approx(0.1, abs=1e-6)
    assert payload["基础统计"]["最大值"] == pytest.approx(0.35, abs=1e-6)
    counts = {row["区间说明"]: row["数据点数量"] for row in payload["分布统计表格"]["表格数据"]}
    assert counts == {"安全区间": 1, "预警区间": 1, "超标区间": 1}


def test_effective_statistics_has_no_distribution(cd_app):
    _insert(cd_app, "effective_cd", [("P1", "S1", math.log(1.5))])
    payload = stats.effective_cd_statistics()
    assert payload["has_data"] is True
    assert "分布统计表格" not in payload
    assert payload["statistics_scope"] == "effective_cd_basic"
    assert payload["基础统计"]["均值"] == pytest.approx(1.5, abs=1e-6)


def test_combined_marks_missing_side(cd_app):
    _insert(cd_app, "crop_cd", [("P1", "S1", math.log(0.2))])
    payload = stats.combined_statistics()
    assert payload["数据完整性"]["有作物Cd数据"] is True
    assert payload["数据完整性"]["有有效态Cd数据"] is False
    assert payload["数据完整性"]["数据完整"] is False
    assert "对比分析" not in payload


def test_list_results_pagination_and_order(cd_app):
    _insert(
        cd_app,
        "crop_cd",
        [("P2", "S1", math.log(0.3)), ("P1", "S2", math.log(0.1)), ("P1", "S1", math.log(0.2))],
    )
    page = stats.list_results("crop_cd", limit=2, offset=0)
    assert page["count"] == 2
    assert [(i["parcel_id"], i["sample_id"]) for i in page["items"]] == [("P1", "S1"), ("P1", "S2")]
    assert page["items"][0]["value"] == pytest.approx(0.2, abs=1e-9)
    assert page["items"][0]["unit"] == "mg/kg"
    assert page["items"][0]["unit_status"] == "unverified"


def test_list_results_rejects_bad_paging(cd_app):
    with pytest.raises(stats.CdStatisticsError):
        stats.list_results("crop_cd", limit=0)
    with pytest.raises(stats.CdStatisticsError):
        stats.list_results("crop_cd", limit=5000)
    with pytest.raises(stats.CdStatisticsError):
        stats.list_results("crop_cd", offset=-1)
    with pytest.raises(stats.CdStatisticsError):
        stats.list_results("nope")


def test_export_csv_bom_columns_and_rows(cd_app):
    _insert(cd_app, "crop_cd", [("P1", "S1", math.log(0.2)), ("P2", "S1", math.log(0.4))])
    payload, total = stats.export_csv("crop_cd")
    assert total == 2
    assert payload.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    text = payload.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line]
    assert lines[0] == "parcel_id,sample_id,ln_value,value,unit,unit_status"
    assert len(lines) == 3
    assert lines[1].startswith("P1,S1,")
    assert lines[1].endswith(",mg/kg,unverified")


def test_export_csv_over_limit_raises(cd_app):
    _insert(cd_app, "crop_cd", [(f"P{i}", "S1", math.log(0.2)) for i in range(3)])
    with pytest.raises(stats.CdStatisticsError) as excinfo:
        stats.export_csv("crop_cd", max_rows=2)
    assert str(excinfo.value.code).startswith("export_exceeds_limit")


def test_area_code_filter_joins_parcel_info(cd_app):
    """area_code 过滤必须真正参与查询（原系统该参数失效）。"""
    from framework.models import ParcelInfo
    from framework.models.user import db as _db

    try:
        ParcelInfo.__table__.create(bind=_db.engine, checkfirst=True)
    except Exception:  # noqa: BLE001 - SQLite 无法渲染 PostGIS 列时跳过
        pytest.skip("ParcelInfo 表无法在 SQLite 建出，area 过滤改由真实库验证")

    _db.session.query(ParcelInfo).delete()
    _db.session.add_all(
        [
            ParcelInfo(parcel_id="P1", area_code="440282"),
            ParcelInfo(parcel_id="P2", area_code="440283"),
        ]
    )
    _db.session.commit()
    _insert(cd_app, "crop_cd", [("P1", "S1", math.log(0.2)), ("P2", "S1", math.log(0.4))])

    filtered = stats.crop_cd_statistics("440282")
    assert filtered["has_data"] is True
    assert filtered["基础统计"]["数据点总数"] == 1
    assert filtered["area_code"] == "440282"

    other = stats.crop_cd_statistics("999999")
    assert other["has_data"] is False


# ---------------- 3. HTTP 层 ----------------


def _http_client(monkeypatch):
    from flask import Flask
    from flask_jwt_extended import JWTManager, create_access_token

    from framework.api.routes import heavy_metal_cd as routes

    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="heavy-metal-cd-test-secret-32-bytes-min")
    JWTManager(app)
    app.register_blueprint(routes.heavy_metal_cd_bp, url_prefix="/hmcd")
    with app.app_context():
        token = create_access_token(identity="7")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_http_requires_authentication(monkeypatch):
    client, _ = _http_client(monkeypatch)
    assert client.get("/hmcd/statistics/crop-cd").status_code == 401
    assert client.get("/hmcd/results?model=crop_cd").status_code == 401
    assert client.get("/hmcd/models").status_code == 401


def test_http_crop_cd_statistics_ok(monkeypatch):
    client, headers = _http_client(monkeypatch)
    monkeypatch.setattr(
        "framework.api.routes.heavy_metal_cd.statistics.crop_cd_statistics",
        lambda area_code=None, source="all": {"has_data": True, "area_code": area_code, "基础统计": {"数据点总数": 3}},
    )
    response = client.get("/hmcd/statistics/crop-cd?area_code=440282", headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["data"]["area_code"] == "440282"


def test_http_results_validation(monkeypatch):
    client, headers = _http_client(monkeypatch)
    assert client.get("/hmcd/results", headers=headers).status_code == 400
    assert client.get("/hmcd/results?model=bad", headers=headers).status_code == 400
    assert client.get("/hmcd/results?model=crop_cd&limit=abc", headers=headers).status_code == 400


def test_http_csv_over_limit_is_413(monkeypatch):
    client, headers = _http_client(monkeypatch)

    def _raise(*args, **kwargs):
        raise stats.CdStatisticsError("export_exceeds_limit:120000>100000")

    monkeypatch.setattr("framework.api.routes.heavy_metal_cd.statistics.export_csv", _raise)
    response = client.get("/hmcd/results.csv?model=crop_cd", headers=headers)
    assert response.status_code == 413
    body = response.get_json()
    assert body["reason"] == "export_exceeds_limit"
    assert body["count"] == 120000
    assert body["max_rows"] == 100000


def test_http_csv_success_sets_headers(monkeypatch):
    client, headers = _http_client(monkeypatch)
    monkeypatch.setattr(
        "framework.api.routes.heavy_metal_cd.statistics.export_csv",
        lambda model_id, area_code=None, source="all": (b"\xef\xbb\xbfa,b\n1,2\n", 1),
    )
    response = client.get("/hmcd/results.csv?model=crop_cd", headers=headers)
    assert response.status_code == 200
    assert "text/csv" in response.headers["Content-Type"]
    assert "attachment" in response.headers["Content-Disposition"]
    assert response.headers["X-Row-Count"] == "1"


def test_http_models_returns_unit_basis(monkeypatch):
    client, headers = _http_client(monkeypatch)
    response = client.get("/hmcd/models", headers=headers)
    assert response.status_code == 200
    models = response.get_json()["models"]
    assert {m["model_id"] for m in models} == {"crop_cd", "effective_cd"}
    assert all(m["unit"] == "mg/kg" and m["unit_basis"] for m in models)
    assert all(m["unit_status"] == "unverified" for m in models)
