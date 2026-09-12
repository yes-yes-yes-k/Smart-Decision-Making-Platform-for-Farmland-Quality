"""输入来源标注与回填识别（change: add-input-provenance-and-report-number-audit）行为测试。"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from framework.agents.specialized.acidification_agent import _imputed_model4_inputs
from framework.domain.provenance import (
    BACKFILLED_FIELDS,
    DEFAULT_FIELDS,
    MEASURED_FIELDS,
    PROVENANCE_KEY,
    SOURCE_DEFAULT,
    SOURCE_MEASURED,
    SOURCE_REGION_MEAN_BACKFILL,
    SOURCE_MANIFEST,
    declared_source,
    imputed_feature_names,
    imputed_fields,
    is_imputed,
    manifest_for,
    provenance_map,
    source_of,
)

MODEL_ARTIFACTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "model_artifacts",
)
DOSE_FEATURES = {"pH": 5.3, "SOMbe": 29.3, "AK": 45.5, "AP": 35.5, "TN": 1.4055}


# ---------------------------------------------------------------- 来源标记读取

def test_provenance_map_tolerates_missing_and_bad_shapes():
    assert provenance_map(None) == {}
    assert provenance_map({}) == {}
    assert provenance_map({PROVENANCE_KEY: "not-a-map"}) == {}
    assert provenance_map({PROVENANCE_KEY: {"total_n": "region_mean_backfill"}}) == {
        "total_n": "region_mean_backfill"
    }


def test_source_and_imputed_judgement():
    indicators = {
        "soil_ph": 5.3,
        "total_n": 1.4055,
        PROVENANCE_KEY: {
            "soil_ph": SOURCE_MEASURED,
            "total_n": SOURCE_REGION_MEAN_BACKFILL,
            "target_ph": SOURCE_DEFAULT,
        },
    }
    assert source_of(indicators, "total_n") == SOURCE_REGION_MEAN_BACKFILL
    assert is_imputed(indicators, "total_n") is True
    assert is_imputed(indicators, "target_ph") is True
    assert is_imputed(indicators, "soil_ph") is False
    # 未标注字段视为来源未知，不得当作实测值
    assert source_of(indicators, "organic_matter") is None
    assert is_imputed(indicators, "organic_matter") is False
    assert imputed_fields(indicators) == ["target_ph", "total_n"]


def test_imputed_feature_names_maps_source_fields_to_features():
    indicators = {
        "total_nitrogen": 1.4055,
        PROVENANCE_KEY: {"total_nitrogen": SOURCE_REGION_MEAN_BACKFILL},
    }
    from framework.domain.provenance import MODEL5_FEATURE_SOURCES

    assert imputed_feature_names(indicators, MODEL5_FEATURE_SOURCES) == ["TN"]


def test_model5_feature_sources_match_accessor():
    """MODEL5_FEATURE_SOURCES 必须与实际取数字段一致（防止字段名漂移）。"""
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor
    from framework.domain.provenance import MODEL5_FEATURE_SOURCES

    probe = {
        "soil_ph": 1.1, "organic_matter": 2.2, "available_potassium": 3.3,
        "available_phosphorus": 4.4, "total_nitrogen": 5.5, "total_n": 6.6,
    }
    mapped = ParcelDataAccessor()._map_indicators_to_inputs(probe, "model-5")
    for feature, source_field in MODEL5_FEATURE_SOURCES.items():
        assert mapped[feature] == probe[source_field], (
            f"{feature} 的实际取数字段与 MODEL5_FEATURE_SOURCES 不一致"
        )


# ---------------------------------------------------------------- 来源台账

def test_manifest_groups_match_write_paths():
    """台账必须与已知写路径一致：回填字段、默认字段、实测字段各归其位。"""
    assert SOURCE_MANIFEST == {
        **{field: SOURCE_MEASURED for field in MEASURED_FIELDS},
        **{field: SOURCE_REGION_MEAN_BACKFILL for field in BACKFILLED_FIELDS},
        **{field: SOURCE_DEFAULT for field in DEFAULT_FIELDS},
    }
    # link_soil_indicators.py 写入的三个 Model-4/5 关键字段必须在回填组
    for field in ("exchangeable_hydrogen", "exchangeable_aluminum", "total_n"):
        assert declared_source(field) == SOURCE_REGION_MEAN_BACKFILL
    # 导入脚本写死的两个字段必须在默认组
    for field in ("target_ph", "fertilizer_type"):
        assert declared_source(field) == SOURCE_DEFAULT
    # 源 shp 逐地块映射的字段属于实测组（含在源数据中取值恒定的 plow_layer_thickness）
    for field in ("soil_ph", "organic_matter", "plow_layer_thickness", "quality_grade"):
        assert declared_source(field) == SOURCE_MEASURED
    assert declared_source("not_in_manifest") is None


def test_manifest_for_filters_unknown_fields():
    assert manifest_for() == SOURCE_MANIFEST
    assert manifest_for(["total_n", "unknown_field"]) == {
        "total_n": SOURCE_REGION_MEAN_BACKFILL
    }


def test_declared_backfill_field_is_imputed_after_marking():
    """按台账标注后，回填字段应被判定为回填输入。"""
    marked = {field: source for field, source in SOURCE_MANIFEST.items()}
    indicators = {"total_n": 1.4055, "exchangeable_aluminum": 4.0262, "soil_ph": 5.3,
                  PROVENANCE_KEY: marked}
    assert is_imputed(indicators, "total_n") is True
    assert is_imputed(indicators, "exchangeable_aluminum") is True
    assert is_imputed(indicators, "target_ph") is True
    assert is_imputed(indicators, "soil_ph") is False
    # 源数据里的常量字段按实测处理，不贴回填标签
    assert is_imputed(indicators, "plow_layer_thickness") is False
    # 台账顺序与默认（按字段名排序）两种调用得到同一集合
    assert sorted(imputed_fields(indicators, list(SOURCE_MANIFEST))) == sorted(
        imputed_fields(indicators)
    )


# ---------------------------------------------------------------- Model-5 守卫

pytestmark_sklearn = pytest.mark.skipif(
    not os.path.exists(os.path.join(MODEL_ARTIFACTS, "upland_dose_rf.joblib")),
    reason="缺少 upland Dose RF 模型文件",
)


@pytestmark_sklearn
def test_predict_dose_without_provenance_keeps_ok():
    from framework.domain.calculations.organic_matter_calculation import predict_dose

    result = predict_dose(dict(DOSE_FEATURES), "upland")
    assert result.status == "ok"
    assert result.imputed_features == ()
    assert result.dose is not None


@pytestmark_sklearn
def test_predict_dose_with_backfilled_tn_degrades_and_labels_input():
    from framework.domain.calculations.organic_matter_calculation import (
        MODEL5_INPUT_IMPUTED,
        predict_dose,
    )

    result = predict_dose(
        dict(DOSE_FEATURES),
        "upland",
        provenance={"total_nitrogen": SOURCE_REGION_MEAN_BACKFILL},
    )
    assert result.status == "degraded"
    assert result.reason == MODEL5_INPUT_IMPUTED
    assert result.imputed_features == ("TN",)
    # 允许保留预测值，但必须带来源标注
    assert result.dose is not None


@pytestmark_sklearn
def test_missing_feature_still_reports_missing_not_imputed():
    from framework.domain.calculations.organic_matter_calculation import (
        MODEL5_INPUT_MISSING,
        predict_dose,
    )

    features = dict(DOSE_FEATURES)
    features["TN"] = None
    result = predict_dose(
        features, "upland", provenance={"total_nitrogen": SOURCE_REGION_MEAN_BACKFILL}
    )
    assert result.status == "degraded"
    assert result.reason == MODEL5_INPUT_MISSING
    assert result.dose is None
    assert result.imputed_features == ()


# ---------------------------------------------------------------- Model-4 守卫

def test_model4_imputed_inputs_lists_backfilled_and_default_values():
    parcel = SimpleNamespace(
        soil_indicators={
            "exchangeable_hydrogen": 0.2949,
            "exchangeable_aluminum": 4.0262,
            "target_ph": 6.5,
            "fertilizer_type": "compound",
            PROVENANCE_KEY: {
                "exchangeable_aluminum": SOURCE_REGION_MEAN_BACKFILL,
                "target_ph": SOURCE_DEFAULT,
            },
        },
        target_ph=6.5,
        fertilizer_type="compound",
    )
    imputed = _imputed_model4_inputs(parcel, {"SJD": 5.3, "Hex": 0.2949, "Alex": 4.0262})
    assert "exchangeable_aluminum" in imputed
    assert "target_ph" in imputed
    # 未标注的交换性氢不判为回填，肥料类型有真实取值也不判为默认
    assert "exchangeable_hydrogen" not in imputed
    assert "fertilizer_type" not in imputed


def test_model4_imputed_inputs_without_parcel_marks_context_defaults():
    imputed = _imputed_model4_inputs(None, {})
    assert imputed == ["target_ph", "fertilizer_type"]


def test_model4_imputed_inputs_all_measured_returns_empty():
    parcel = SimpleNamespace(
        soil_indicators={
            "exchangeable_hydrogen": 5.0,
            "exchangeable_aluminum": 0.8,
            PROVENANCE_KEY: {
                "exchangeable_hydrogen": SOURCE_MEASURED,
                "exchangeable_aluminum": SOURCE_MEASURED,
            },
        },
        target_ph=6.0,
        fertilizer_type="urea",
    )
    assert _imputed_model4_inputs(parcel, {}) == []
