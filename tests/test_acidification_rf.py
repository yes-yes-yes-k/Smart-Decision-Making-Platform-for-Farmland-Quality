import pytest
import warnings
from sklearn.exceptions import InconsistentVersionWarning

from framework.domain.other_models.acidification_rf import map_parcel_indicators, predict


def test_manifest_hash_is_checked(monkeypatch, tmp_path):
    from framework.domain.other_models import acidification_rf
    manifest = {"models": [{"model_id": 35, "data_type": "reflux", "land_type": "dryland", "artifact_path": "bad.pkl", "source_model_file_path": "x", "sha256": "00", "verified_at": "x", "source": "x"}]}
    monkeypatch.setattr(acidification_rf, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(acidification_rf, "ARTIFACT_ROOT", tmp_path)
    import sklearn
    manifest["models"][0].update(
        artifact_size_bytes=len(b"not-a-model"),
        serialized_with_scikit_learn=sklearn.__version__,
    )
    (tmp_path / "manifest.json").write_text(__import__("json").dumps(manifest), encoding="utf-8")
    (tmp_path / "bad.pkl").write_bytes(b"not-a-model")
    assert predict(35, {"H": 1, "Al": 2, "OM": 3, "NO3": 4, "NH4": 5, "CEC": 6})["reason"] == "model_integrity_mismatch"


@pytest.mark.parametrize("model_id", [33, 35, 38])
def test_shipped_models_load_without_sklearn_version_warning(model_id):
    from framework.domain.other_models.acidification_rf import load_model

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _, model = load_model(model_id)

    assert model.predict
    assert not [w for w in caught if issubclass(w.category, InconsistentVersionWarning)]



def test_reduce_and_reflux_online_semantics():
    reduce_result = predict(33, {"init_pH": 5, "target_pH": 6, "H": 1, "Al": 2, "OM": 3, "NO3": 4, "NH4": 5, "CEC": 6})
    assert reduce_result["status"] == "success"
    raw = reduce_result["predictions"][0]["raw_prediction"]
    assert raw > 0
    assert reduce_result["predictions"][0]["result"] == pytest.approx(raw * 25 / 15)

    reflux_result = predict(38, {"CEC": 6, "NH4": 5, "NO3": 4, "Al": 2, "FeO": 40, "OM": 3})
    assert reflux_result["status"] == "success"
    assert reflux_result["predictions"][0]["result"] >= 0
    assert reflux_result["predictions"][0]["conversion"] == "abs"


def test_paddy_model_uses_its_own_feature_set():
    """水田 reflux 的真实特征是 CEC/NH4/NO3/Al/FeO/OM：缺 FeO 必须拒绝，不能套旱地字段。"""
    from framework.domain.other_models.acidification_rf import load_model

    _, model = load_model(38)
    assert list(model.feature_names_in_) == ["CEC", "NH4", "NO3", "Al", "FeO", "OM"]

    # 只给旱地字段（含 H、无 FeO）会被判为缺列，而不是静默按错序预测
    rejected = predict(38, {"H": 1, "Al": 2, "OM": 3, "NO3": 4, "NH4": 5, "CEC": 6})
    assert rejected["status"] == "rejected"
    assert "FeO" in rejected["missing_fields"]


def test_prefill_maps_only_established_fields():
    from framework.domain.other_models.acidification_rf import prefill_from_parcel

    indicators = {
        "soil_ph": 5.3,
        "organic_matter": 30.5,
        "exchangeable_hydrogen": 0.295,
        "exchangeable_aluminum": 4.026,
        "cation_exchange_capacity": 11.18,
        "target_ph": 6.5,
        "provenance": {
            "soil_ph": "measured",
            "organic_matter": "measured",
            "exchangeable_hydrogen": "region_mean_backfill",
            "exchangeable_aluminum": "region_mean_backfill",
            "cation_exchange_capacity": "region_mean_backfill",
            "target_ph": "default",
        },
    }
    result = prefill_from_parcel(indicators, "upland")

    assert result["model_id"] == 35
    assert result["data_type"] == "reflux"
    assert result["status"] == "need_input"
    assert set(result["missing_fields"]) == {"NO3", "NH4"}
    assert result["provenance"]["OM"] == "measured"
    assert result["provenance"]["CEC"] == "region_mean_backfill"
    assert result["provenance"]["H"] == "region_mean_backfill"
    # 回填与缺失都必须显式提示，不能静默填充
    assert any("区域平均回填" in w for w in result["warnings"])
    assert any("NO3" in w for w in result["warnings"])


def test_prefill_paddy_uses_paddy_model_and_needs_feo():
    from framework.domain.other_models.acidification_rf import prefill_from_parcel

    indicators = {
        "soil_ph": 5.4, "organic_matter": 35.0,
        "exchangeable_hydrogen": 1.0, "exchangeable_aluminum": 2.0,
        "cation_exchange_capacity": 10.0,
        "provenance": {},
    }
    result = prefill_from_parcel(indicators, "paddy")

    assert result["model_id"] == 38
    assert "FeO" in result["missing_fields"]
    # 无 provenance 标注时来源必须是 unknown，不能默认成 measured
    assert result["provenance"]["OM"] == "unknown"


def test_prefill_rejects_reflux_land_type_mismatch():
    from framework.domain.other_models.acidification_rf import (
        AcidificationRFError, prefill_from_parcel,
    )

    # reflux 必须与地块土地类型匹配：水田地块不能用旱地 reflux 模型 35
    with pytest.raises(AcidificationRFError):
        prefill_from_parcel({"soil_ph": 5.4}, "paddy", model_id=35)


def test_prefill_allows_reduce_for_paddy():
    """旧系统语义：reduce 不区分土地类型，水田降酸沿用旱地 reduce 模型 33。"""
    from framework.domain.other_models.acidification_rf import prefill_from_parcel

    result = prefill_from_parcel({"soil_ph": 5.4}, "paddy", model_id=33)
    assert result["model_id"] == 33
    assert result["data_type"] == "reduce"


def test_prefill_never_invents_missing_fields():
    """缺字段时不得出现在 data 里，也不得用 0 或均值补。"""
    from framework.domain.other_models.acidification_rf import prefill_from_parcel

    result = prefill_from_parcel({"soil_ph": 5.4, "organic_matter": 20.0}, "upland")
    assert "NO3" not in result["data"] and "NH4" not in result["data"]
    assert "H" not in result["data"]  # 地块无该字段时同样不填


def test_prefill_offers_training_median_suggestions():
    """缺失字段给出建议值，但必须标明来源与单位未核验，且不写进 data。"""
    from framework.domain.other_models.acidification_rf import prefill_from_parcel

    result = prefill_from_parcel({"soil_ph": 5.4, "organic_matter": 20.0}, "upland")
    suggestions = result["suggestions"]
    assert set(suggestions) == {"NO3", "NH4"}
    no3 = suggestions["NO3"]
    assert no3["basis"] == "training_median"
    assert no3["dataset"] == "dataset_81"
    assert no3["row_count"] == 219
    assert no3["unit_status"] == "unverified"
    assert no3["value"] == pytest.approx(31.24)
    assert no3["range_p25_p75"] == [23.58, 38.685]
    # 建议值不能出现在 data 里，必须由使用者显式采用
    assert "NO3" not in result["data"]


def test_paddy_suggestions_include_feo_from_its_own_dataset():
    from framework.domain.other_models.acidification_rf import prefill_from_parcel

    result = prefill_from_parcel({"soil_ph": 5.4, "organic_matter": 20.0}, "paddy")
    assert result["suggestions"]["FeO"]["dataset"] == "dataset_94"
    assert result["suggestions"]["FeO"]["value"] == pytest.approx(39.9)


def test_adopted_suggestions_mark_result_degraded():
    from framework.domain.other_models.acidification_rf import predict

    data = {"H": 1, "Al": 2, "OM": 3, "NO3": 31.24, "NH4": 5.13, "CEC": 6}
    plain = predict(35, data)
    assert plain["status"] == "success"
    assert plain["assumed_fields"] == {}

    adopted = predict(35, data, assumptions={"NO3": "training_median", "NH4": "training_median"})
    assert adopted["status"] == "degraded"
    assert adopted["assumed_fields"] == {"NO3": "training_median", "NH4": "training_median"}


def test_assumptions_ignore_fields_not_in_model():
    from framework.domain.other_models.acidification_rf import predict

    data = {"H": 1, "Al": 2, "OM": 3, "NO3": 31.24, "NH4": 5.13, "CEC": 6}
    result = predict(35, data, assumptions={"FeO": "training_median", "junk": "x"})
    # FeO 不属于旱地模型输入，不应污染假定记录
    assert result["assumed_fields"] == {}
    assert result["status"] == "success"


def test_batch_mean_imputation_is_degraded_and_records_fields():
    result = predict(35, [
        {"H": 1, "Al": 2, "OM": 3, "NO3": 4, "NH4": 5, "CEC": 6},
        {"H": 2, "Al": 3, "OM": None, "NO3": 5, "NH4": 6, "CEC": 7},
    ])
    assert result["status"] == "degraded"
    assert result["imputed_fields"] == ["OM"]
    assert len(result["predictions"]) == 2


def test_invalid_batches_do_not_call_model(monkeypatch):
    called = False
    from framework.domain.other_models import acidification_rf
    original = acidification_rf.load_model

    def wrapped(model_id):
        nonlocal called
        called = True
        return original(model_id)

    monkeypatch.setattr(acidification_rf, "load_model", wrapped)
    assert predict(35, []) ["reason"] == "empty_batch"
    result = predict(35, [{"H": None, "Al": 2, "OM": 3, "NO3": 4, "NH4": 5, "CEC": 6}])
    assert result["reason"] == "all_column_missing"
    assert not called


@pytest.mark.parametrize("data, reason", [
    ({"H": "bad", "Al": 2, "OM": 3, "NO3": 4, "NH4": 5, "CEC": 6}, "invalid_input"),
    ({"H": 1, "h": 2, "Al": 2, "OM": 3, "NO3": 4, "NH4": 5, "CEC": 6}, "input_conflict:H"),
])
def test_invalid_values_and_conflicts_do_not_load_model(monkeypatch, data, reason):
    from framework.domain.other_models import acidification_rf
    loaded = False

    def forbidden_load(_model_id):
        nonlocal loaded
        loaded = True
        raise AssertionError("invalid input loaded a model")

    monkeypatch.setattr(acidification_rf, "load_model", forbidden_load)
    result = predict(35, data)
    assert result["reason"] == reason
    assert not loaded


def test_conflict_illegal_and_unknown_parcel_mapping():
    assert predict(35, {"H": 1, "h": 2, "Al": 2, "OM": 3, "NO3": 4, "NH4": 5, "CEC": 6})["reason"].startswith("input_conflict")
    assert predict(35, {"H": "bad", "Al": 2, "OM": 3, "NO3": 4, "NH4": 5, "CEC": 6})["reason"] == "invalid_input"
    mapping = map_parcel_indicators({"soil_ph": 5.5, "total_n": 1})
    assert mapping["status"] == "need_verification"
    assert "NH4" in mapping["unknown_fields"]
