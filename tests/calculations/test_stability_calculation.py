# tests/calculations/test_stability_calculation.py
"""Model-1 耕地质量稳定性与退化风险评价 — 9 模块单元测试。

覆盖 framework/domain/calculations/stability_calculation.py 的 9 个计算模块
以及 framework.models.thematic_model.ParcelHistorySnapshot ORM 模型。
"""
import pytest

from framework.domain.calculations.stability_calculation import (
    calculate_boundary_safety,
    calculate_support_balance,
    calculate_key_criticality,
    calculate_neighborhood_consistency,
    calculate_history_trend,
    calculate_downgrade_risk,
    calculate_factor_degradation,
    calculate_degradation_clustering,
    calculate_persistent_low_quality,
    calculate_stability,
)
from framework.models.thematic_model import ParcelHistorySnapshot
from framework.models.user import db


# ----------------------------------------------------------------------
# 模块 1: 等级边界安全度
# ----------------------------------------------------------------------
def test_boundary_safety_in_range():
    """模块1: 边界安全度 ∈ [0, 1]."""
    result = calculate_boundary_safety(
        zhqz=0.75, grade=5, qmin=0.6, qmax=0.9)
    assert 0.0 <= result["SAFE_ABS"] <= 1.0


def test_boundary_safety_invalid_range():
    """模块1: qmax <= qmin 时降级返回 None."""
    result = calculate_boundary_safety(zhqz=0.75, grade=5, qmin=0.9, qmax=0.6)
    assert result["SAFE_ABS"] is None
    assert result["reason"] == "invalid_range"


def test_boundary_safety_clipped_to_zero():
    """模块1: 原始值 < 0 时被裁剪到 0."""
    # zhqz 很低、grade 很小时 raw 应为负
    result = calculate_boundary_safety(
        zhqz=0.1, grade=1, qmin=0.0, qmax=1.0)
    assert result["SAFE_ABS"] == 0.0


# ----------------------------------------------------------------------
# 模块 2: 指标支撑均衡度
# ----------------------------------------------------------------------
def test_support_balance_in_range():
    """模块2: 支撑均衡度 ∈ [0, 1]."""
    memberships = [0.8, 0.7, 0.9, 0.6, 0.8, 0.85, 0.7, 1.0, 0.8, 0.6, 0.5, 0.4]
    weights = [0.07, 0.10, 0.06, 0.07, 0.05, 0.06, 0.06, 0.09, 0.11, 0.14, 0.13, 0.08]
    result = calculate_support_balance(memberships, weights)
    assert 0.0 <= result["BAL_ABS"] <= 1.0


def test_support_balance_zero_weights():
    """模块2: 权重和 <= 0 时降级返回 None."""
    result = calculate_support_balance([0.5, 0.6], [0.0, 0.0])
    assert result["BAL_ABS"] is None
    assert result["reason"] == "zero_weights"


# ----------------------------------------------------------------------
# 模块 3: 关键指标临界度
# ----------------------------------------------------------------------
def test_key_criticality_returns_factor():
    """模块3: 关键指标临界度返回 KEY_FAC."""
    memberships = [0.8, 0.7, 0.9, 0.6, 0.8, 0.85, 0.7, 1.0, 0.8, 0.6, 0.5, 0.4]
    weights = [0.07, 0.10, 0.06, 0.07, 0.05, 0.06, 0.06, 0.09, 0.11, 0.14, 0.13, 0.08]
    indicators = ["SJD", "YJZ", "YXL", "SXJ", "TRRZ", "YXTCHD", "GCHD",
                 "GCZD", "GGNL", "PSNL", "DXBW", "ZDGX"]
    result = calculate_key_criticality(memberships, weights, indicators)
    assert result["KEY_FAC"] in indicators
    assert 0.0 <= result["KEY_ABS"] <= 1.0


def test_key_criticality_picks_lowest_membership():
    """模块3: KEY_FAC 应为隶属度最低的指标."""
    memberships = [0.8, 0.7, 0.9, 0.6, 0.8, 0.85, 0.7, 1.0, 0.8, 0.6, 0.5, 0.4]
    weights = [0.07, 0.10, 0.06, 0.07, 0.05, 0.06, 0.06, 0.09, 0.11, 0.14, 0.13, 0.08]
    indicators = ["SJD", "YJZ", "YXL", "SXJ", "TRRZ", "YXTCHD", "GCHD",
                 "GCZD", "GGNL", "PSNL", "DXBW", "ZDGX"]
    result = calculate_key_criticality(memberships, weights, indicators)
    # 最低隶属度是 0.4 → indicators[11] = "ZDGX"
    assert result["KEY_FAC"] == "ZDGX"
    assert result["KEY_ABS"] == pytest.approx(0.6)


# ----------------------------------------------------------------------
# 模块 4: 空间邻域一致性
# ----------------------------------------------------------------------
def test_neighborhood_consistency_empty():
    """模块4: 无邻域时返回 null."""
    result = calculate_neighborhood_consistency([], "5")
    assert result["NEI_ABS"] is None
    assert result["reason"] == "no_neighbors"


def test_neighborhood_consistency_all_consistent():
    """模块4: 所有邻域等级数值 >= 自身等级数值 → NEI_ABS = 1.0.

    按计划实现: 邻域等级 >= 自身等级（数值比较，等级数值越大表示质量越差）
    表示邻域质量等于或差于自身，与自身处于一致的退化区间。
    """
    # 自身等级 5；邻域等级 6、7（数值更大 = 质量更差或相等）→ 一致
    neighbors = [
        {"parcel_id": "P-002", "quality_grade": "6"},
        {"parcel_id": "P-003", "quality_grade": "7"},
    ]
    result = calculate_neighborhood_consistency(neighbors, "5")
    assert result["NEI_ABS"] == 1.0
    assert result["neighbor_count"] == 2


def test_neighborhood_consistency_none_consistent():
    """模块4: 所有邻域等级数值 < 自身等级数值 → NEI_ABS = 0.0."""
    # 自身等级 5；邻域等级 3、4（数值更小 = 质量更好）→ 不一致
    neighbors = [
        {"parcel_id": "P-002", "quality_grade": "3"},
        {"parcel_id": "P-003", "quality_grade": "4"},
    ]
    result = calculate_neighborhood_consistency(neighbors, "5")
    assert result["NEI_ABS"] == 0.0
    assert result["neighbor_count"] == 2


# ----------------------------------------------------------------------
# 模块 5: 历史变化趋势
# ----------------------------------------------------------------------
def test_history_trend_insufficient():
    """模块5: 历史期数 < 2 时降级."""
    history = [{"survey_year": 2024, "composite_index": 0.7}]
    result = calculate_history_trend(history)
    assert result["H_ABS"] is None
    assert result["reason"] == "insufficient_history"


def test_history_trend_in_range():
    """模块5: 多期数据时 H_ABS ∈ [0, 1]."""
    history = [
        {"survey_year": 2018, "composite_index": 0.70},
        {"survey_year": 2021, "composite_index": 0.73},
        {"survey_year": 2024, "composite_index": 0.75},
    ]
    result = calculate_history_trend(history)
    assert 0.0 <= result["H_ABS"] <= 1.0


# ----------------------------------------------------------------------
# 模块 6: 掉级风险
# ----------------------------------------------------------------------
def test_downgrade_risk_insufficient():
    """模块6: 历史期数 < 2 时降级."""
    result = calculate_downgrade_risk([{"survey_year": 2024, "quality_grade": "5"}])
    assert result["DOWNGRADE_ABS"] is None
    assert result["reason"] == "insufficient_history"


def test_downgrade_risk_no_drop():
    """模块6: 等级持续改善（数值减小）→ 风险 = 0."""
    history = [
        {"survey_year": 2018, "quality_grade": "6"},
        {"survey_year": 2021, "quality_grade": "5"},
        {"survey_year": 2024, "quality_grade": "4"},
    ]
    result = calculate_downgrade_risk(history)
    assert result["DOWNGRADE_ABS"] == 0.0


def test_downgrade_risk_all_dropped():
    """模块6: 等级持续下降 → 风险 = 1.0."""
    history = [
        {"survey_year": 2018, "quality_grade": "4"},
        {"survey_year": 2021, "quality_grade": "5"},
        {"survey_year": 2024, "quality_grade": "6"},
    ]
    result = calculate_downgrade_risk(history)
    assert result["DOWNGRADE_ABS"] == 1.0


# ----------------------------------------------------------------------
# 模块 7: 关键因子退化风险
# ----------------------------------------------------------------------
def test_factor_degradation_insufficient():
    """模块7: 历史期数 < 2 时降级."""
    result = calculate_factor_degradation([{"survey_year": 2024, "composite_index": 0.7}])
    assert result["DEGRADE_ABS"] is None
    assert result["reason"] == "insufficient_history"


def test_factor_degradation_improving():
    """模块7: 指数上升 → 无退化 = 0.0."""
    history = [
        {"survey_year": 2018, "composite_index": 0.70},
        {"survey_year": 2021, "composite_index": 0.73},
        {"survey_year": 2024, "composite_index": 0.75},
    ]
    result = calculate_factor_degradation(history)
    assert result["DEGRADE_ABS"] == 0.0


def test_factor_degradation_decline():
    """模块7: 指数下降 → 退化风险 ∈ (0, 1]."""
    history = [
        {"survey_year": 2018, "composite_index": 0.80},
        {"survey_year": 2021, "composite_index": 0.75},
        {"survey_year": 2024, "composite_index": 0.70},
    ]
    result = calculate_factor_degradation(history)
    assert 0.0 < result["DEGRADE_ABS"] <= 1.0


# ----------------------------------------------------------------------
# 模块 8: 退化空间集聚风险
# ----------------------------------------------------------------------
def test_degradation_clustering_empty():
    """模块8: 无邻域时降级."""
    result = calculate_degradation_clustering([])
    assert result["CLUSTER_ABS"] is None
    assert result["reason"] == "no_neighbors"


def test_degradation_clustering_no_degraded():
    """模块8: 邻域均未退化 → CLUSTER_ABS = 0.0."""
    neighbors = [
        {"parcel_id": "P-002", "quality_grade": "4"},
        {"parcel_id": "P-003", "quality_grade": "5"},
    ]
    result = calculate_degradation_clustering(neighbors)
    assert result["CLUSTER_ABS"] == 0.0


def test_degradation_clustering_all_degraded():
    """模块8: 邻域全部退化（>= 7 级）→ CLUSTER_ABS = 1.0."""
    neighbors = [
        {"parcel_id": "P-002", "quality_grade": "7"},
        {"parcel_id": "P-003", "quality_grade": "8"},
    ]
    result = calculate_degradation_clustering(neighbors)
    assert result["CLUSTER_ABS"] == 1.0


# ----------------------------------------------------------------------
# 模块 9: 持续低质风险
# ----------------------------------------------------------------------
def test_persistent_low_quality_empty():
    """模块9: 无历史数据时降级."""
    result = calculate_persistent_low_quality([])
    assert result["PERSIST_ABS"] is None
    assert result["reason"] == "insufficient_history"


def test_persistent_low_quality_no_low():
    """模块9: 历史等级均 >= 7 级以下 → PERSIST_ABS = 0.0."""
    history = [
        {"survey_year": 2018, "quality_grade": "4"},
        {"survey_year": 2021, "quality_grade": "5"},
        {"survey_year": 2024, "quality_grade": "4"},
    ]
    result = calculate_persistent_low_quality(history)
    assert result["PERSIST_ABS"] == 0.0


def test_persistent_low_quality_all_low():
    """模块9: 历史等级全部 >= 7 → PERSIST_ABS = 1.0."""
    history = [
        {"survey_year": 2018, "quality_grade": "7"},
        {"survey_year": 2021, "quality_grade": "8"},
        {"survey_year": 2024, "quality_grade": "9"},
    ]
    result = calculate_persistent_low_quality(history)
    assert result["PERSIST_ABS"] == 1.0


# ----------------------------------------------------------------------
# 完整 calculate_stability 入口
# ----------------------------------------------------------------------
def test_calculate_stability_returns_all_modules():
    """完整稳定性计算返回 9 个模块结果."""
    parcel_info = {
        "parcel_id": "P-001", "area_code": "440281",
        "indicators": {"SJD": 5.5, "YJZ": 20.0, "YXL": 15.0, "SXJ": 100.0,
                       "TRRZ": 1.2, "YXTCHD": 80.0, "GCHD": 15.0,
                       "GCZD": "RT", "GGNL": "FS", "PSNL": "CM",
                       "DXBW": "LHR", "ZDGX": "TLBC"},
        "quality_index": 0.75, "quality_grade": "5",
    }
    history = [
        {"survey_year": 2018, "composite_index": 0.70, "quality_grade": "6"},
        {"survey_year": 2021, "composite_index": 0.73, "quality_grade": "5"},
        {"survey_year": 2024, "composite_index": 0.75, "quality_grade": "5"},
    ]
    neighbors = [{"parcel_id": "P-002", "quality_grade": "4"}]
    result = calculate_stability(parcel_info, history, neighbors)
    assert "module_1" in result
    assert "module_9" in result
    assert len(result) == 9


# ----------------------------------------------------------------------
# ParcelHistorySnapshot ORM 模型
# ----------------------------------------------------------------------
def test_parcel_history_snapshot_table_name():
    """ParcelHistorySnapshot 表名为 parcel_history_snapshot."""
    assert ParcelHistorySnapshot.__tablename__ == "parcel_history_snapshot"


def test_parcel_history_snapshot_columns():
    """ParcelHistorySnapshot 含必需字段: id, parcel_id, survey_year,
    soil_indicators, quality_grade, composite_index, created_at."""
    columns = {c.name for c in ParcelHistorySnapshot.__table__.columns}
    required = {
        "id", "parcel_id", "survey_year", "soil_indicators",
        "quality_grade", "composite_index", "created_at",
    }
    assert required.issubset(columns), f"缺少字段: {required - columns}"


def test_parcel_history_snapshot_parcel_id_fk():
    """ParcelHistorySnapshot.parcel_id 应为指向 parcel_info.parcel_id 的外键."""
    from sqlalchemy import ForeignKeyConstraint
    fk_targets = set()
    for constraint in ParcelHistorySnapshot.__table__.constraints:
        if isinstance(constraint, ForeignKeyConstraint):
            for fk in constraint.elements:
                fk_targets.add(fk.target_fullname)
    assert "parcel_info.parcel_id" in fk_targets, \
        "parcel_id 应为外键 → parcel_info.parcel_id"


def test_parcel_history_snapshot_is_db_model():
    """ParcelHistorySnapshot 应是 db.Model 子类."""
    assert issubclass(ParcelHistorySnapshot, db.Model)
