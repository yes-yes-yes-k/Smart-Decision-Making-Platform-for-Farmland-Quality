"""未来 Cd 情景预测测试（阶段 7，v2 基线）。

守门点：
- 公式数值：(Initial + Net×years)/(2000×bulk_density)，**不读 soil_depth_m**
- 多年份分组、年份越界、负净通量不截断
- 回退计数（bulk_density / initial_cd）
- 统计口径：样本标准差 ddof=1、线性插值分位数
- v2 取数：只取当前修订、跳过 legacy_v1 行
- 空数据、点位、导出、HTTP 端点

公式部分不依赖数据库；取数/写回部分需要 PostgreSQL（``CD_MIGRATION_TEST_DB``），
未配置时自动 skip。
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.domain.other_models import cd_projection  # noqa: E402


# ----------------------------- 纯公式（无数据库） -----------------------------


def test_formula_matches_legacy_expression():
    rows = [(f"p{i}", f"s{i}", 600.0, 1.3, 10.0, None, None) for i in range(3)]
    preds, fallback = cd_projection.project_values(rows, 10)
    assert fallback["skipped"] == 0
    # (600 + 10×10) / (2000 × 1.3)
    assert preds[0][4] == pytest.approx(700 / (2000 * 1.3))
    assert cd_projection.SOIL_MASS_KG_HA == 2000.0


def test_soil_depth_is_not_part_of_formula():
    """用户拍板：严格照抄原系统，土重固定 2000×容重，不读 soil_depth_m。

    project_values 的入参里没有 soil_depth_m，同容重同净通量必须得到同一结果。
    """
    rows = [("p", "s", 600.0, 1.3, 10.0, 1.0, 2.0)]
    preds, _ = cd_projection.project_values(rows, 5)
    assert preds[0][4] == pytest.approx((600 + 50) / 2600)
    assert "soil_depth_m" not in cd_projection.FORMULA
    assert "不读 soil_depth_m" in cd_projection.SOIL_MASS_NOTE


def test_multi_year_scaling():
    rows = [("p", "s", 600.0, 1.2, 10.0, None, None)]
    for years in (1, 10, 50):
        preds, _ = cd_projection.project_values(rows, years)
        assert preds[0][4] == pytest.approx((600 + 10 * years) / 2400)


def test_negative_net_not_clamped():
    rows = [("p", "s", 600.0, 1.2, -50.0, None, None)]
    preds, _ = cd_projection.project_values(rows, 2)
    assert preds[0][4] == pytest.approx((600 - 100) / 2400)


def test_fallback_counts_and_skip():
    rows = [
        ("a", "a", None, None, 10.0, None, None),   # initial_cd / bulk 双回退
        ("b", "b", 600.0, 1.2, None, None, None),   # 无净通量 → 跳过
        ("c", "c", 600.0, 0.0, 10.0, None, None),   # 土重 0 → 0
    ]
    preds, fallback = cd_projection.project_values(rows, 10)
    assert fallback == {
        "bulk_density_g_cm3": 1,
        "initial_cd": 1,
        "non_positive_soil_mass": 1,
        "skipped": 1,
    }
    values = {p[0]: p[4] for p in preds}
    assert values["a"] == pytest.approx((0 + 100) / 2000)
    assert values["c"] == 0.0
    assert "b" not in values


def test_stats_use_sample_std_and_linear_quantile():
    stats = cd_projection._stats([1.0, 2.0, 3.0, 4.0])
    assert stats["count"] == 4
    assert stats["mean"] == pytest.approx(2.5)
    # 样本标准差 ddof=1 = 1.2909944...
    assert stats["std"] == pytest.approx(1.2909944487358056)
    assert stats["median"] == pytest.approx(2.5)
    assert stats["percentile_25"] == pytest.approx(1.75)
    assert stats["percentile_75"] == pytest.approx(3.25)
    assert cd_projection._stats([]) == {"has_data": False, "count": 0}


def test_year_and_accounting_year_bounds():
    assert cd_projection._check_years(10) == [10]
    assert cd_projection._check_years([10, 5, 10]) == [5, 10]
    for bad in (0, 101, -1, "abc", None):
        with pytest.raises(cd_projection.CdProjectionError):
            cd_projection._check_years(bad)
    assert cd_projection._check_accounting_year(None) is None
    assert cd_projection._check_accounting_year("2024") == 2024
    for bad in ("abc", 0, 10000, True):
        with pytest.raises(cd_projection.CdProjectionError):
            cd_projection._check_accounting_year(bad)


def test_end_cd_distribution_thresholds():
    dist = cd_projection._end_cd_distribution([0.1, 0.4, 0.9])
    assert dist["安全区间 (< 0.3 mg/kg)"]["数量"] == 1
    assert dist["预警区间 (0.3-0.6 mg/kg)"]["数量"] == 1
    assert dist["超标区间 (≥ 0.6 mg/kg)"]["数量"] == 1


# ----------------------------- v2 取数（需要 PostgreSQL） -----------------------------

V2_SQL = open(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts/sql/cd_flux_v2.sql"),
    encoding="utf-8",
).read()


@pytest.fixture
def app_db(monkeypatch, tmp_path):
    database = os.getenv("CD_MIGRATION_TEST_DB")
    if not database:
        pytest.skip("PostgreSQL integration environment not enabled (set CD_MIGRATION_TEST_DB)")
    from dotenv import load_dotenv
    from flask import Flask
    from flask_jwt_extended import JWTManager
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL

    load_dotenv(os.environ["CD_MIGRATION_ENV_FILE"])
    url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=database,
    )
    import uuid

    schema = "cd_proj_test_" + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        # 在临时 schema 内复制真实表的列定义（含 PostGIS 类型），不复制索引；
        # 测试连接只使用临时 schema，绝不写 public。
        for table in ("parcel_info", "cd_crop_prediction_result", "cd_ported_parcel_township"):
            conn.execute(
                text(
                    f'CREATE TABLE "{schema}".{table} '
                    f"(LIKE public.{table} INCLUDING DEFAULTS INCLUDING CONSTRAINTS)"
                )
            )
    try:
        from framework.models import (
            CdCropPredictionResult,
            FarmlandRegionParcelArea,
            ParcelInfo,
            SpatialRegionCatalog,
        )
        from framework.models.user import db

        app = Flask(__name__)
        app.config["SQLALCHEMY_DATABASE_URI"] = url.render_as_string(hide_password=False)
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.config["TESTING"] = True
        app.config["JWT_SECRET_KEY"] = "cd-projection-secret-32-bytes-min"
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"options": f"-c search_path={schema}"}
        }
        db.init_app(app)
        JWTManager(app)
        from framework.api.routes.cd_flux import cd_flux_bp

        app.register_blueprint(cd_flux_bp, url_prefix="/api/v1/cd-flux")
        from framework.domain.other_models import heavy_metal_cd_visualization as viz

        monkeypatch.setattr(viz, "VISUALIZATION_ROOT", tmp_path / "cd_visualization")

        with app.app_context():
            with db.engine.begin() as conn:
                raw = conn.connection.cursor()
                raw.execute(V2_SQL)
                raw.close()
            yield db, app
            db.session.remove()
            db.engine.dispose()
    finally:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def _seed_v2(db, rows, year=2024, source="ported"):
    """rows: [(parcel_id, initial_cd, bulk_density, net_cd)]，写 v2 输入并算输出。

    v2 的 number() 拒绝负数，因此净通量的正负用「输入列」与「输出列」分开表达：
    net ≥ 0 走 atmospheric_deposition，net < 0 走 surface_runoff。
    """
    from framework.domain.other_models import cd_flux_v2 as flux

    lines = []
    for pid, initial, bulk, net in rows:
        deposition = net if net >= 0 else 0
        runoff = 0 if net >= 0 else -net
        lines.append(
            f"{source},{year},{pid},{pid},{initial},{deposition},0,0,0,0,{runoff},0,0,{bulk},0.2,"
            "cd_flux_mass_balance_v2,{}"
        )
    header = (
        "source,accounting_year,parcel_id,sample_id,initial_cd,atmospheric_deposition,"
        "irrigation_input,agro_chemicals_input,enterprise_input,groundwater_leaching,"
        "surface_runoff,grain_removal,straw_removal,bulk_density_g_cm3,soil_depth_m,"
        "contract_version,provenance"
    )
    flux.import_csv((header + "\n" + "\n".join(lines)).encode())
    flux.calculate(year=year)


def test_base_rows_read_current_revision_only(app_db):
    db, _app = app_db
    from sqlalchemy import text

    from framework.models import ParcelInfo

    db.session.bulk_insert_mappings(
        ParcelInfo,
        [{"parcel_id": "p1", "centroid_lon": 113.0, "centroid_lat": 25.0}],
    )
    db.session.commit()
    _seed_v2(db, [("p1", 600.0, 1.3, 10.0)])
    rows = cd_projection._base_rows(region_type=None, region_id=None, source="ported")
    assert len(rows) == 1
    pid, sid, initial, bulk, net, lon, lat = rows[0]
    assert (pid, sid) == ("p1", "p1")
    assert initial == pytest.approx(600.0)
    assert bulk == pytest.approx(1.3)
    # _seed_v2 把净通量写成 atmospheric_deposition（正 net）或 surface_runoff（负 net）
    assert net == pytest.approx(10.0)
    assert lat is not None or lon is not None


def test_projection_statistics_and_http(app_db):
    db, app = app_db
    from flask_jwt_extended import create_access_token
    from sqlalchemy import text

    from framework.models import ParcelInfo

    db.session.bulk_insert_mappings(
        ParcelInfo,
        [
            {"parcel_id": "p1", "centroid_lon": 113.0, "centroid_lat": 25.0},
            {"parcel_id": "p2", "centroid_lon": 113.5, "centroid_lat": 25.5},
        ],
    )
    db.session.commit()
    _seed_v2(db, [("p1", 600.0, 1.3, 10.0), ("p2", 400.0, 1.0, -2.0)])

    stats = cd_projection.statistics(10, source="ported")
    assert stats["has_data"] is True
    assert stats["count"] == 2
    assert stats["accounting_year"] is None

    points = cd_projection.points_geojson(10, source="ported")
    assert points["count"] == 2
    assert points["coordinate_source"] == "parcel_centroid"

    text_out, count = cd_projection.export_csv(10, source="ported")
    assert count == 2
    assert text_out.startswith("parcel_id,sample_id,future_cd,years,unit")

    multi = cd_projection.predict([5, 10], source="ported")
    assert set(multi["scenarios"]) == {"5", "10"}
    assert multi["scenarios"]["5"]["mean"] < multi["scenarios"]["10"]["mean"]

    client = app.test_client()
    assert client.get("/api/v1/cd-flux/v2/projection/statistics?years=10").status_code == 401
    with app.app_context():
        token = create_access_token(identity="1")
    headers = {"Authorization": "Bearer " + token}
    assert (
        client.post("/api/v1/cd-flux/v2/projection", headers=headers, json={"years": 10, "source": "ported"}).status_code
        == 200
    )
    assert (
        client.get("/api/v1/cd-flux/v2/projection/statistics?years=10&source=ported", headers=headers).status_code
        == 200
    )
    assert client.get("/api/v1/cd-flux/v2/projection/export.csv?years=10&source=ported", headers=headers).status_code == 200
    assert (
        client.get(
            "/api/v1/cd-flux/v2/projection/statistics?years=10&accounting_year=abc", headers=headers
        ).status_code
        == 400
    )


def test_legacy_rows_are_ignored(app_db):
    db, _app = app_db
    from framework.domain.other_models import cd_flux

    old_header = ",".join(cd_flux.REQUIRED_COLUMNS)
    old_line = ",".join(["p9", "p9", "600", "1", "1", "1", "0", "0", "0", "0"])
    from framework.domain.other_models import cd_flux_v2 as flux

    flux.import_csv((old_header + "\n" + old_line).encode(), legacy=True)
    flux.calculate()
    rows = cd_projection._base_rows(region_type=None, region_id=None, source="all")
    assert rows == []


def test_year_filter_isolates_rows(app_db):
    db, _app = app_db
    from framework.models import ParcelInfo

    db.session.bulk_insert_mappings(
        ParcelInfo, [{"parcel_id": "p1", "centroid_lon": 113.0, "centroid_lat": 25.0}]
    )
    db.session.commit()
    _seed_v2(db, [("p1", 600.0, 1.3, 10.0)], year=2023)
    _seed_v2(db, [("p1", 700.0, 1.3, 10.0)], year=2024)

    all_rows = cd_projection._base_rows(region_type=None, region_id=None, source="ported")
    assert len(all_rows) == 2
    only_2024 = cd_projection._base_rows(
        region_type=None, region_id=None, source="ported", accounting_year=2024
    )
    assert len(only_2024) == 1
    assert only_2024[0][2] == pytest.approx(700.0)
