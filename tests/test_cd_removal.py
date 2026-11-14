"""Cd 移除项计算测试（阶段 6，v2 基线）。

守门点：
- 籽粒公式数值（0.1 mg/kg × f11=800 → 0.6 g/ha/a）
- 秸秆公式与分母非正跳过计数、f11 比例关系
- 写回必须显式给 year（v2 唯一键含年度）
- 只写 ``grain_removal``/``straw_removal`` 两列并递增 ``input_revision``
- 同地块样点多年度只写指定年度；legacy_v1 行跳过；多来源歧义拒绝写回
- write_back=false 只算不写；无作物结果时不写回、不重算
- 统计/点位/导出/HTTP 端点

说明：作物结果表的来源维度由 ``parcel_id`` 的 ``SGD_`` 前缀判定，因此隔离测试里的
地块编号统一使用 ``SGD_`` 前缀。公式部分不依赖数据库；写回部分需要 PostgreSQL
（``CD_MIGRATION_TEST_DB``），未配置时自动 skip。
"""
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.domain.other_models import cd_removal  # noqa: E402


# ----------------------------- 纯公式（无数据库） -----------------------------


def test_grain_formula():
    crop, grain, straw, reason = cd_removal._evaluate(math.log(0.1), 800.0)
    assert reason is None
    assert crop == pytest.approx(0.1)
    # 0.1 × 800 × 0.5 × 15 / 1000
    assert grain == pytest.approx(0.6)
    expected_straw = (0.1 / (0.1 * 0.76 - 0.0034)) * 800 * 0.0075
    assert straw == pytest.approx(expected_straw)


def test_f11_scaling():
    _c1, g1, s1, _ = cd_removal._evaluate(math.log(0.2), 800.0)
    _c2, g2, s2, _ = cd_removal._evaluate(math.log(0.2), 1600.0)
    assert g2 == pytest.approx(g1 * 2)
    assert s2 == pytest.approx(s1 * 2)


def test_invalid_denominator_skipped():
    # crop ≤ 0.0034/0.76 时分母非正
    crop, grain, straw, reason = cd_removal._evaluate(math.log(0.003), 800.0)
    assert reason == "invalid_denominator"
    assert crop == pytest.approx(0.003)
    assert grain is not None
    assert straw is None


def test_invalid_value_returns_no_components():
    _c, grain, straw, reason = cd_removal._evaluate(float("inf"), 800.0)
    assert (grain, straw, reason) == (None, None, "invalid_value")


def test_f11_and_year_validation():
    assert cd_removal._check_f11(None) == cd_removal.DEFAULT_F11
    assert cd_removal._check_f11("900") == 900.0
    for bad in (0, -1, "abc", float("nan"), 200000):
        with pytest.raises(cd_removal.CdRemovalError):
            cd_removal._check_f11(bad)
    assert cd_removal._check_year(None) is None
    assert cd_removal._check_year("2024") == 2024
    for bad in ("abc", 0, 10000, True):
        with pytest.raises(cd_removal.CdRemovalError):
            cd_removal._check_year(bad)


# ----------------------------- v2 写回（需要 PostgreSQL） -----------------------------

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

    schema = "cd_removal_test_" + uuid.uuid4().hex
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
        from framework.models.user import db

        app = Flask(__name__)
        app.config["SQLALCHEMY_DATABASE_URI"] = url.render_as_string(hide_password=False)
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.config["TESTING"] = True
        app.config["JWT_SECRET_KEY"] = "cd-removal-secret-32-bytes-min"
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


V2_HEADER = (
    "source,accounting_year,parcel_id,sample_id,initial_cd,atmospheric_deposition,"
    "irrigation_input,agro_chemicals_input,enterprise_input,groundwater_leaching,"
    "surface_runoff,grain_removal,straw_removal,bulk_density_g_cm3,soil_depth_m,"
    "contract_version,provenance"
)


def _import_v2(rows):
    """rows: [(source, year, parcel, sample, initial, leaching, runoff, grain, straw, bulk)]"""
    from framework.domain.other_models import cd_flux_v2 as flux

    lines = [
        f"{s},{y},{p},{sid},{initial},0,0,0,0,{leach},{runoff},{grain},{straw},{bulk},0.2,"
        "cd_flux_mass_balance_v2,{}"
        for s, y, p, sid, initial, leach, runoff, grain, straw, bulk in rows
    ]
    return flux.import_csv((V2_HEADER + "\n" + "\n".join(lines)).encode())


def _seed_crop(db, values):
    from framework.models import CdCropPredictionResult

    db.session.bulk_insert_mappings(
        CdCropPredictionResult,
        [{"parcel_id": pid, "sample_id": pid, "ln_crop_cd": math.log(v)} for pid, v in values.items()],
    )
    db.session.commit()


def test_write_back_requires_year(app_db):
    db, _app = app_db
    _seed_crop(db, {"SGD_p1": 0.1})
    _import_v2([("ported", 2024, "SGD_p1", "SGD_p1", 600, 0, 0, 0, 0, 1.3)])
    with pytest.raises(cd_removal.CdRemovalError) as exc:
        cd_removal.calculate(source="all")
    assert exc.value.code == "year_required"


def test_write_back_updates_two_columns_and_bumps_revision(app_db):
    db, _app = app_db
    _seed_crop(db, {"SGD_p1": 0.1, "SGD_p2": 0.2})
    _import_v2(
        [
            ("ported", 2024, "SGD_p1", "SGD_p1", 600, 5, 2, 0, 0, 1.3),
            ("ported", 2024, "SGD_p2", "SGD_p2", 400, 1, 1, 0, 0, 1.0),
        ]
    )
    from sqlalchemy import text

    before = {
        r[0]: r[1]
        for r in db.session.execute(
            text("SELECT parcel_id, input_revision FROM cd_flux_input_v2 ORDER BY parcel_id")
        ).all()
    }
    result = cd_removal.calculate(source="all", year=2024)
    assert result["crop_rows"] == 2
    assert result["updated_inputs"] == 2
    assert result["legacy_input_skipped"] == 0
    assert result["recalculated"]["has_data"] is True

    rows = db.session.execute(
        text(
            "SELECT parcel_id, grain_removal, straw_removal, input_revision, "
            "groundwater_leaching, surface_runoff FROM cd_flux_input_v2 ORDER BY parcel_id"
        )
    ).all()
    assert rows[0][1] == pytest.approx(0.6)
    assert rows[0][2] == pytest.approx((0.1 / (0.1 * 0.76 - 0.0034)) * 800 * 0.0075)
    # 只递增修订，其他列保持原值
    assert rows[0][3] == before["SGD_p1"] + 1
    assert rows[0][4] == pytest.approx(5)
    assert rows[0][5] == pytest.approx(2)
    # 写回后重算，为两个当前修订各写一行输出
    count = db.session.execute(text("SELECT count(*) FROM cd_flux_output_v2")).scalar()
    assert count == 2


def test_write_back_isolates_accounting_year(app_db):
    db, _app = app_db
    _seed_crop(db, {"SGD_p1": 0.1})
    _import_v2(
        [
            ("ported", 2023, "SGD_p1", "SGD_p1", 500, 1, 1, 0, 0, 1.2),
            ("ported", 2024, "SGD_p1", "SGD_p1", 600, 0, 0, 0, 0, 1.3),
        ]
    )
    from sqlalchemy import text

    result = cd_removal.calculate(source="all", year=2024)
    assert result["updated_inputs"] == 1
    rows = dict(
        (r[0], (r[1], r[2]))
        for r in db.session.execute(
            text("SELECT accounting_year, grain_removal, input_revision FROM cd_flux_input_v2")
        ).all()
    )
    assert rows[2024] == (pytest.approx(0.6), 2)  # 被写回并递增
    assert rows[2023] == (pytest.approx(0.0), 1)  # 未动（导入时 grain 填 0）


def test_legacy_rows_skipped(app_db):
    db, _app = app_db
    _seed_crop(db, {"SGD_p9": 0.1})
    from framework.domain.other_models import cd_flux

    header = ",".join(cd_flux.REQUIRED_COLUMNS)
    line = ",".join(["SGD_p9", "SGD_p9", "600", "1", "1", "1", "0", "0", "0", "0"])
    from framework.domain.other_models import cd_flux_v2 as flux

    flux.import_csv((header + "\n" + line).encode(), legacy=True)
    result = cd_removal.calculate(source="all", year=2024)
    assert result["updated_inputs"] == 0
    assert result["missing_input_rows"] == 1
    assert result["legacy_input_skipped"] == 1


def test_write_back_false_and_missing_rows(app_db):
    db, _app = app_db
    _seed_crop(db, {"SGD_p1": 0.1, "SGD_absent": 0.1})
    _import_v2([("ported", 2024, "SGD_p1", "SGD_p1", 600, 0, 0, 0, 0, 1.3)])
    from sqlalchemy import text

    result = cd_removal.calculate(source="all", year=2024, write_back=False)
    assert result["updated_inputs"] == 0
    assert result["recalculate_reason"] == "write_back_disabled"
    assert db.session.execute(text("SELECT grain_removal FROM cd_flux_input_v2")).scalar() == 0.0

    result = cd_removal.calculate(source="all", year=2024)
    assert result["updated_inputs"] == 1
    assert result["missing_input_rows"] == 1
    assert result["missing_input_preview"]["preview"][0]["parcel_id"] == "SGD_absent"


def test_ambiguous_multi_source_refused(app_db):
    db, _app = app_db
    _seed_crop(db, {"SGD_p1": 0.1})
    # 同一 parcel/sample/年份 但两个来源：写回会批量命中，必须拒绝
    _import_v2(
        [
            ("ported", 2024, "SGD_p1", "SGD_p1", 600, 0, 0, 0, 0, 1.3),
            ("native", 2024, "SGD_p1", "SGD_p1", 600, 0, 0, 0, 0, 1.3),
        ]
    )
    result = cd_removal.calculate(source="all", year=2024)
    assert result["updated_inputs"] == 0
    assert result["ambiguous_input_rows"] == 1


def test_no_crop_data(app_db):
    db, _app = app_db
    result = cd_removal.calculate(source="all", year=2024)
    assert result["has_data"] is False
    assert result["recalculate_reason"] == "no_data"


def test_statistics_points_export_and_http(app_db):
    db, app = app_db
    _seed_crop(db, {"SGD_p1": 0.1, "SGD_p2": 0.2})
    _import_v2(
        [
            ("ported", 2024, "SGD_p1", "SGD_p1", 600, 5, 2, 0, 0, 1.3),
            ("ported", 2024, "SGD_p2", "SGD_p2", 400, 1, 1, 0, 0, 1.0),
        ]
    )
    from framework.models import ParcelInfo

    db.session.bulk_insert_mappings(
        ParcelInfo,
        [
            {"parcel_id": "SGD_p1", "centroid_lon": 113.0, "centroid_lat": 25.0},
            {"parcel_id": "SGD_p2", "centroid_lon": 113.5, "centroid_lat": 25.5},
        ],
    )
    db.session.commit()

    grain = cd_removal.statistics("grain", source="all", year=2024)
    assert grain["count"] == 2
    assert grain["基础统计"]["均值"] == pytest.approx(0.9)  # (0.6 + 1.2) / 2
    # 输入类字段走 v2 表
    leaching = cd_removal.statistics("leaching", source="all", year=2024)
    assert leaching["count"] == 2
    assert leaching["基础统计"]["均值"] == pytest.approx(3.0)

    points = cd_removal.points_geojson("grain", source="all", year=2024)
    assert points["count"] == 2

    text_out, count = cd_removal.export_csv("grain", source="all", year=2024)
    assert count == 2 and text_out.startswith("parcel_id,sample_id,grain,unit")

    from flask_jwt_extended import create_access_token

    client = app.test_client()
    assert client.get("/api/v1/cd-flux/v2/removal/statistics?field=grain&year=2024").status_code == 401
    with app.app_context():
        token = create_access_token(identity="1")
    headers = {"Authorization": "Bearer " + token}
    assert (
        client.post(
            "/api/v1/cd-flux/v2/removal/calculate",
            headers=headers,
            json={"source": "all", "year": 2024},
        ).status_code
        == 200
    )
    # 缺 year 的写回请求必须是 400
    assert (
        client.post(
            "/api/v1/cd-flux/v2/removal/calculate", headers=headers, json={"source": "ported"}
        ).status_code
        == 400
    )
    assert (
        client.get(
            "/api/v1/cd-flux/v2/removal/statistics?field=grain&year=2024&source=ported", headers=headers
        ).status_code
        == 200
    )
    assert (
        client.get("/api/v1/cd-flux/v2/removal/export.csv?field=grain&year=2024", headers=headers).status_code
        == 200
    )
