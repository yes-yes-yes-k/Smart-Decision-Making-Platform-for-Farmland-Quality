"""Heavy-metal Cd (AcidMap) local torch port tests.

守门点：
- 特征顺序 / scaler 维数 / 特殊特征索引（crop solution=13, eff Cdsolution=20）
- 基准预测（输入=训练均值）：crop_cd 0.266523、effective_cd 0.423962
- 缺失 solution/Cdsolution 走训练中位数降级；缺失其他字段/非法输入不调用模型
- 地块预填只映射已确认字段，逐字段 provenance，缺项进 missing_fields
"""
import json

import numpy as np
import pytest

from framework.domain.other_models.heavy_metal_cd import (
    ARTIFACT_ROOT,
    _API_FIELDS,
    _MODEL_COLUMNS,
    _SPECIAL_FEATURE,
    available_models,
    load_model,
    predict,
    prefill_from_parcel,
)

CROP_FIELDS = _API_FIELDS["crop_cd"]
EFF_FIELDS = _API_FIELDS["effective_cd"]


def _mean_inputs(model_id: str) -> dict:
    """输入 = 训练均值（标准化后全 0），用于基准预测复现。"""
    mean = np.load(str(ARTIFACT_ROOT / model_id / next(
        p.name for p in (ARTIFACT_ROOT / model_id).glob("*mean*.npy")
    ))).astype(float)
    fields = _API_FIELDS[model_id]
    assert len(mean) == len(fields), (mean.shape, len(fields))
    return {f: float(v) for f, v in zip(fields, mean)}


def test_manifest_lists_both_models():
    models = available_models()
    ids = {m["model_id"] for m in models}
    assert ids == {"crop_cd", "effective_cd"}
    by_id = {m["model_id"]: m for m in models}
    assert by_id["crop_cd"]["features"] == 14
    assert by_id["effective_cd"]["features"] == 21
    assert by_id["crop_cd"]["special_feature_index"] == 13
    assert by_id["effective_cd"]["special_feature_index"] == 20
    assert all(m["unit_status"] == "unverified" for m in models)


def test_feature_order_matches_model_columns():
    """对外可读字段顺序必须与模型内部列序（scaler 数组顺序）一一对应。"""
    for mid in ("crop_cd", "effective_cd"):
        assert len(_API_FIELDS[mid]) == len(_MODEL_COLUMNS[mid])
        # 特殊特征在两项常量中位置一致
        special, idx = _SPECIAL_FEATURE[mid]
        assert _API_FIELDS[mid][idx] == special
        assert special == _MODEL_COLUMNS[mid][idx].lower() or special in (
            "solution", "cdsolution",
        )


def test_feature_count_matches_scaler_dimension():
    """每个模型的检测特征数与 scaler mean/scale 维度一致（资产维度断言）。"""
    for mid in ("crop_cd", "effective_cd"):
        for suffix in ("_mean.npy", "_scale.npy"):
            path = next(p for p in (ARTIFACT_ROOT / mid).glob(f"*{suffix}"))
            arr = np.load(str(path))
            assert arr.shape[0] == len(_API_FIELDS[mid]), (mid, suffix, arr.shape)


@pytest.mark.parametrize(
    "model_id,expected",
    [("crop_cd", 0.266523), ("effective_cd", 0.423962)],
)
def test_baseline_prediction_means_input(model_id, expected):
    """输入=训练均值时必须复现审计基准 0.266523 / 0.423962。"""
    result = predict(model_id, _mean_inputs(model_id))
    assert result["status"] == "success"
    assert result["unit_status"] == "unverified"
    assert result["prediction"] == pytest.approx(expected, abs=1e-5)


def test_special_feature_missing_uses_median_and_degrades():
    """crop_cd 缺 solution → 用训练中位数 -2.1266 并强制 degraded。"""
    data = _mean_inputs("crop_cd")
    data.pop("solution")
    result = predict("crop_cd", data)
    assert result["status"] == "degraded"
    assert "solution" in result["assumed_fields"]
    assumed = result["assumed_fields"]["solution"]
    assert assumed["basis"] == "training_median"
    assert assumed["value"] == pytest.approx(-2.1266, abs=1e-4)
    assert assumed["n"] == 40100
    assert result["special_feature"]["assumed"] is True


def test_effective_cd_missing_cdsolution_degrades():
    data = _mean_inputs("effective_cd")
    data.pop("cdsolution")
    result = predict("effective_cd", data)
    assert result["status"] == "degraded"
    assert "cdsolution" in result["assumed_fields"]


def test_missing_other_field_returns_need_input_without_loading_model(monkeypatch):
    """缺失普通字段 → need_input，且不加载/调用模型。"""
    calls = {"load": 0}

    def _spy_load(model_id):
        calls["load"] += 1
        raise AssertionError("模型不应被加载")

    import framework.domain.other_models.heavy_metal_cd as hcd
    monkeypatch.setattr(hcd, "load_model", _spy_load)

    data = _mean_inputs("crop_cd")
    data.pop("total_sulfur")
    result = predict("crop_cd", data)
    assert result["status"] == "need_input"
    assert "total_sulfur" in result["missing_fields"]
    assert calls["load"] == 0


def test_invalid_non_numeric_input_rejected(monkeypatch):
    import framework.domain.other_models.heavy_metal_cd as hcd
    calls = {"load": 0}

    def _spy_load(model_id):
        calls["load"] += 1
        raise AssertionError("模型不应被加载")

    monkeypatch.setattr(hcd, "load_model", _spy_load)
    data = _mean_inputs("crop_cd")
    data["solution"] = "not-a-number"
    result = predict("crop_cd", data)
    assert result["status"] == "rejected"
    assert result["reason"] == "invalid_input"
    assert calls["load"] == 0


def test_unknown_model_rejected():
    result = predict("unknown_model", {})
    assert result["status"] == "rejected"
    assert result["reason"] == "unknown_model"


def test_shipped_models_load_and_have_expected_state_dict():
    """真实资产可加载且 state_dict 含约束参数 a/b。"""
    for mid in ("crop_cd", "effective_cd"):
        record, model, _ = load_model(mid)
        assert record.model_id == mid
        state = model.state_dict()
        assert "a" in state and "b" in state
        assert "fc1.weight" in state


def test_prefill_maps_only_established_fields():
    indicators = {
        "available_potassium": 58.05,
        "available_phosphorus": 11.73,
        "total_n": 1.13,
        "provenance": {
            "available_potassium": "measured",
            "available_phosphorus": "region_mean_backfill",
            "total_n": "region_mean_backfill",
        },
    }
    result = prefill_from_parcel(indicators, "effective_cd")
    assert result["status"] == "need_input"
    assert set(result["data"].keys()) == {"available_potassium", "available_phosphorus", "total_nitrogen"}
    assert "cdsolution" in result["missing_fields"]
    assert result["provenance"]["available_potassium"] == "measured"
    assert result["provenance"]["available_phosphorus"] == "region_mean_backfill"
    assert result["is_parcel_level_assessment"] is False
    assert result["prediction_not_run"] is True


def test_prefill_unknown_source_defaults_to_unknown():
    indicators = {"total_n": 1.13}  # 无 provenance
    result = prefill_from_parcel(indicators, "crop_cd")
    assert result["provenance"]["total_nitrogen"] == "unknown"


def test_prefill_unmapped_fields_go_to_missing():
    """soil_texture 等未确认语义的字段不得映射为 Cd 特征。"""
    indicators = {"soil_texture": "粉(砂)质壤土", "exchangeable_acid_total": 1.0}
    result = prefill_from_parcel(indicators, "effective_cd")
    assert result["data"] == {}
    assert "silt_fraction" in result["missing_fields"]
    assert "exchangeable_acid_total" not in [f for f in result["data"]]


def test_manifest_hash_integrity_detection(monkeypatch, tmp_path):
    """篡改资产 → model_integrity_mismatch。"""
    import framework.domain.other_models.heavy_metal_cd as hcd

    # 拷贝一份真实 manifest 到 tmp_path 并篡改一个 hash
    manifest = json.loads((ARTIFACT_ROOT / "manifest.json").read_text(encoding="utf-8"))
    manifest["models"]["crop_cd"]["files"]["cropCdNN.pth"] = "00" * 32
    shim = tmp_path / "manifest.json"
    shim.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(hcd, "MANIFEST_PATH", shim)
    monkeypatch.setattr(hcd, "ARTIFACT_ROOT", ARTIFACT_ROOT)

    data = _mean_inputs("crop_cd")
    result = predict("crop_cd", data)
    assert result["status"] == "rejected"
    assert result["reason"] == "model_integrity_mismatch"