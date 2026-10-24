# tests/calculations/test_model45_integration.py
"""Model-4/5 数据库字段与数据完整性集成测试。

需要 PostgreSQL 数据库连接（conftest.PG_AVAILABLE）。
"""
import pytest
from sqlalchemy import text

try:
    from tests.conftest import PG_AVAILABLE
except ImportError:
    PG_AVAILABLE = False

pytestmark = pytest.mark.skipif(not PG_AVAILABLE, reason="PostgreSQL 不可用")


@pytest.fixture
def db_session():
    """每个测试独立 session，测试后 rollback 避免事务中止。"""
    from framework.api.app import create_app
    from framework.models.user import db
    app = create_app("default")
    with app.app_context():
        yield db
        db.session.rollback()


def _scalar(db, sql):
    """执行标量查询，失败时 rollback。"""
    try:
        return db.session.execute(text(sql)).scalar()
    except Exception:
        db.session.rollback()
        raise


# ===== 7.1 AreaCodeRegionMap 模型测试 =====

def test_area_code_region_map_table_exists(db_session):
    """area_code_region_map 表存在。"""
    result = _scalar(db_session,
        "SELECT count(*) FROM information_schema.tables WHERE table_name='area_code_region_map'")
    assert result > 0, "area_code_region_map 表不存在"


def test_area_code_region_map_has_lechang_and_xinfeng(db_session):
    """area_code_region_map 包含乐昌(440281)和新丰(440233)映射。"""
    rows = db_session.session.execute(text(
        'SELECT area_code, "primary", "secondary", ejnyq_idx '
        'FROM area_code_region_map WHERE enabled=true'
    )).fetchall()
    codes = {r[0]: {"primary": r[1], "secondary": r[2], "ejnyq_idx": r[3]} for r in rows}
    assert "440281" in codes, "缺少乐昌 440281 映射"
    assert "440233" in codes, "缺少新丰 440233 映射"
    for code in ("440281", "440233"):
        assert codes[code]["primary"] == "HN"
        assert codes[code]["secondary"] == "NL"
        assert codes[code]["ejnyq_idx"] == 3


# ===== 7.3 数据库字段完整性测试 =====

def test_third_survey_topsoils_has_model45_fields(db_session):
    """third_survey_topsoils 表包含 Model-4/5 新增字段。"""
    needed = ["exchangeable_hydrogen", "exchangeable_aluminum",
              "exchangeable_acid_total", "hydrolytic_total_acidity", "total_n"]
    for field in needed:
        exists = _scalar(db_session,
            f"SELECT count(*) FROM information_schema.columns "
            f"WHERE table_name='third_survey_topsoils' AND column_name='{field}'")
        assert exists, f"third_survey_topsoils 缺少字段 {field}"


def test_third_survey_profiles_has_model4_fields(db_session):
    """third_survey_profiles 表包含 Model-4 新增字段。"""
    needed = ["exchangeable_hydrogen", "exchangeable_aluminum", "hydrolytic_total_acidity"]
    for field in needed:
        exists = _scalar(db_session,
            f"SELECT count(*) FROM information_schema.columns "
            f"WHERE table_name='third_survey_profiles' AND column_name='{field}'")
        assert exists, f"third_survey_profiles 缺少字段 {field}"


# ===== 7.4 Model-4 数据查询测试 =====

def test_model4_profile_data_has_exchangeable_hydrogen(db_session):
    """third_survey_profiles 表有 exchangeable_hydrogen 非空数据。"""
    count = _scalar(db_session,
        "SELECT count(*) FROM third_survey_profiles WHERE exchangeable_hydrogen IS NOT NULL")
    assert count > 0, "third_survey_profiles.exchangeable_hydrogen 无非空数据"


def test_model4_profile_data_has_exchangeable_aluminum(db_session):
    """third_survey_profiles 表有 exchangeable_aluminum 非空数据。"""
    count = _scalar(db_session,
        "SELECT count(*) FROM third_survey_profiles WHERE exchangeable_aluminum IS NOT NULL")
    assert count > 0, "third_survey_profiles.exchangeable_aluminum 无非空数据"


def test_model4_parcel_indicators_has_exchangeable_hydrogen(db_session):
    """parcel_info.soil_indicators 包含 exchangeable_hydrogen 字段。"""
    count = _scalar(db_session,
        "SELECT count(*) FROM parcel_info "
        "WHERE soil_indicators->>'exchangeable_hydrogen' IS NOT NULL")
    total = _scalar(db_session, "SELECT count(*) FROM parcel_info")
    rate = count / total * 100 if total > 0 else 0
    assert rate > 90, f"exchangeable_hydrogen 非空率仅 {rate:.1f}% ({count}/{total})"


# ===== 7.5 Model-5 数据查询测试 =====

def test_model5_topsoil_data_has_total_n(db_session):
    """third_survey_topsoils 表有 total_n 非空数据。"""
    count = _scalar(db_session,
        "SELECT count(*) FROM third_survey_topsoils WHERE total_n IS NOT NULL")
    assert count > 0, "third_survey_topsoils.total_n 无非空数据"


def test_model5_parcel_indicators_has_total_n(db_session):
    """parcel_info.soil_indicators 包含 total_n 字段。"""
    count = _scalar(db_session,
        "SELECT count(*) FROM parcel_info "
        "WHERE soil_indicators->>'total_n' IS NOT NULL")
    total = _scalar(db_session, "SELECT count(*) FROM parcel_info")
    rate = count / total * 100 if total > 0 else 0
    assert rate > 90, f"total_n 非空率仅 {rate:.1f}% ({count}/{total})"


def test_model5_parcel_management_fields_are_canonical_columns(db_session):
    """管理字段只存在于 parcel_info 顶层规范列，不在指标 JSON 中重复。"""
    for field in ("target_ph", "fertilizer_type"):
        count = _scalar(db_session,
            f"SELECT count(*) FROM parcel_info "
            f"WHERE {field} IS NOT NULL")
        total = _scalar(db_session, "SELECT count(*) FROM parcel_info")
        rate = count / total * 100 if total > 0 else 0
        assert rate > 90, f"{field} 非空率仅 {rate:.1f}% ({count}/{total})"
        duplicate_count = _scalar(db_session,
            f"SELECT count(*) FROM parcel_info "
            f"WHERE soil_indicators->>'{field}' IS NOT NULL")
        assert duplicate_count == 0, f"soil_indicators 中仍存在 {field} 重复字段"


# ===== 7.2 get_region_mapping DB 集成测试 =====

def test_get_region_mapping_from_db_lechang(db_session):
    """get_region_mapping 从 DB 返回乐昌映射（缓存命中）。"""
    from framework.domain.calculations.region_mapping_service import (
        get_region_mapping, refresh_region_cache,
    )
    refresh_region_cache()  # 清空缓存强制从 DB 加载
    result = get_region_mapping("440281")
    assert result["primary"] == "HN"
    assert result["secondary"] == "NL"
    assert result["ejnyq_idx"] == 3


def test_get_region_mapping_from_db_xinfeng(db_session):
    """get_region_mapping 从 DB 返回新丰映射（440233）。"""
    from framework.domain.calculations.region_mapping_service import (
        get_region_mapping, refresh_region_cache,
    )
    refresh_region_cache()
    result = get_region_mapping("440233")
    assert result["primary"] == "HN"
    assert result["secondary"] == "NL"
    assert result["ejnyq_idx"] == 3
