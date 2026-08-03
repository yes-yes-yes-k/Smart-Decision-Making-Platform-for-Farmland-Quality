"""测试 model_6_execution ML 预测引擎。

单元测试全部使用 monkeypatch mock sklearn/joblib/模型文件，CI 零依赖。
集成测试使用真实模型文件，通过 skipif 在 sklearn/模型不可用时跳过。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ---- 测试用 mock 数据 ----

class FakeModel:
    """模拟 sklearn ExtraTreesRegressor 的 predict 行为"""
    def predict(self, df):
        return [42.0]


FAKE_SOC_META = {
    "model_type": "ExtraTreesRegressor",
    "model_version": "ETR_v1_20260713",
    "feature_names": ["pH", "SOCbe", "TN ", "TP ", "TK ", "AP", "AK", "Gap", "Dose", "Fertilizer type"],
    "feature_means": {
        "pH": 7.0, "SOCbe": 12.0, "TN ": 0.8, "TP ": 0.5, "TK ": 30.0,
        "AP": 50.0, "AK": 100.0, "Gap": 10.0, "Dose": 100.0, "Fertilizer type": 1.5,
    },
    "metrics": {"cv_r2": 0.89, "cv_rmse": 2.15, "test_r2": 0.91, "test_rmse": 2.24},
}

FAKE_DOSE_META = {
    "model_type": "ExtraTreesRegressor",
    "model_version": "ETR_v1_20260713",
    "feature_names": ["pH", "SOCbe", "TN ", "TP ", "TK ", "AP", "AK", "Gap", "Fertilizer type"],
    "feature_means": {
        "pH": 7.0, "SOCbe": 12.0, "TN ": 0.8, "TP ": 0.5, "TK ": 30.0,
        "AP": 50.0, "AK": 100.0, "Gap": 10.0, "Fertilizer type": 1.5,
    },
    "metrics": {"cv_r2": 0.43, "cv_rmse": 55.0, "test_r2": 0.47, "test_rmse": 50.0},
}

FULL_VALID_INPUT = {
    "pH": 6.5, "SOCbe": 15.0, "TN": 1.2, "TP": 0.8, "TK": 25.0,
    "AP": 30.0, "AK": 80.0, "Gap": 5.0, "Dose": 200.0, "Fertilizer type": 1,
}


def _setup_mock_models(monkeypatch):
    """将 model_6 模块的状态变量设置为 mock 值，模拟模型已加载"""
    from framework.domain.other_models import model_6
    monkeypatch.setattr(model_6, "_SKLEARN_AVAILABLE", True)
    monkeypatch.setattr(model_6, "_SOC_MODEL", FakeModel())
    monkeypatch.setattr(model_6, "_DOSE_MODEL", FakeModel())
    monkeypatch.setattr(model_6, "_SOC_META", FAKE_SOC_META)
    monkeypatch.setattr(model_6, "_DOSE_META", FAKE_DOSE_META)
    monkeypatch.setattr(model_6, "_SOC_LOAD_FAILED", False)
    monkeypatch.setattr(model_6, "_DOSE_LOAD_FAILED", False)


# ---- 单元测试 ----

class TestModel6Execution:
    def test_success_full_features(self, monkeypatch):
        """完整 10 特征 → status=success"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"
        assert result["soc_prediction"] == 42.0
        assert result["dose_prediction"] == 42.0
        assert result["soc_confidence"] == 0.91
        assert result["dose_confidence"] == 0.47
        assert "dose_warning" in result
        assert result["imputation_applied"] is False
        assert result["imputed_features"] == []
        assert result["model_version"] == "ETR_v1_20260713"

    def test_success_partial_features_imputation(self, monkeypatch):
        """部分特征缺失 → imputation_applied=true, imputed_features 非空"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        partial = {"pH": 6.5, "SOCbe": 15.0, "TN": 1.2}
        result = model_6_execution(partial)
        assert result["status"] == "success"
        assert result["imputation_applied"] is True
        assert len(result["imputed_features"]) > 0

    def test_fallback_sklearn_missing(self, monkeypatch):
        """sklearn 不可用 → status=fallback, fallback_reason=sklearn_missing"""
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SKLEARN_AVAILABLE", False)
        result = model_6.model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "fallback"
        assert result["fallback_reason"] == "sklearn_missing"
        assert result["soc_confidence"] == 0.3
        assert result["dose_confidence"] == 0.3

    def test_fallback_model_file_missing(self, monkeypatch):
        """模型文件缺失 → status=fallback, fallback_reason=model_file_missing"""
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SKLEARN_AVAILABLE", True)
        monkeypatch.setattr(model_6, "_SOC_MODEL", None)
        monkeypatch.setattr(model_6, "_DOSE_MODEL", None)
        monkeypatch.setattr(model_6, "_SOC_META", None)
        monkeypatch.setattr(model_6, "_DOSE_META", None)
        monkeypatch.setattr(model_6, "_SOC_LOAD_FAILED", True)
        monkeypatch.setattr(model_6, "_DOSE_LOAD_FAILED", True)
        result = model_6.model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "fallback"
        assert result["fallback_reason"] == "model_file_missing"
        assert result["soc_confidence"] == 0.3

    def test_rejected_out_of_range_ph(self, monkeypatch):
        """pH=99 → status=rejected, out_of_range_features 包含 pH"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        bad_input = dict(FULL_VALID_INPUT, pH=99.0)
        result = model_6_execution(bad_input)
        assert result["status"] == "rejected"
        assert result["reason"] == "input_out_of_range"
        assert result["soc_prediction"] is None
        assert result["dose_prediction"] is None
        oor_features = [f["feature"] for f in result["out_of_range_features"]]
        assert "pH" in oor_features

    def test_rejected_fertilizer_type_invalid(self, monkeypatch):
        """Fertilizer type=3 → status=rejected"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        bad_input = dict(FULL_VALID_INPUT, **{"Fertilizer type": 3})
        result = model_6_execution(bad_input)
        assert result["status"] == "rejected"
        oor_features = [f["feature"] for f in result["out_of_range_features"]]
        assert "Fertilizer type" in oor_features

    def test_empty_input_uses_all_means(self, monkeypatch):
        """空字典 → 全部特征用均值填充，imputed_features 非空"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution({})
        assert result["status"] == "success"
        assert result["imputation_applied"] is True
        # SOC 10 特征全部填充
        assert len(result["imputed_features"]) >= 10

    def test_none_input_coerced_to_empty(self, monkeypatch):
        """None 输入 → coerce 为 {} 后走空字典路径"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(None)
        assert result["status"] == "success"
        assert result["imputation_applied"] is True

    def test_string_numeric_coercion(self, monkeypatch):
        """'1.5' 字符串 → float 转换成功，正常预测"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        str_input = {k: str(v) for k, v in FULL_VALID_INPUT.items()}
        result = model_6_execution(str_input)
        assert result["status"] == "success"
        assert result["imputation_applied"] is False

    def test_string_non_numeric_uses_mean(self, monkeypatch):
        """'abc' 字符串 → 转换失败，用均值填充"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        bad_str_input = dict(FULL_VALID_INPUT, pH="abc")
        result = model_6_execution(bad_str_input)
        assert result["status"] == "success"
        assert result["imputation_applied"] is True
        assert "pH" in result["imputed_features"]

    def test_feature_name_with_trailing_space(self, monkeypatch):
        """用户传 'TN'，模型 feature_names 含 'TN ' → 正确匹配"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"
        # TN 未被填充说明正确匹配了 'TN ' → 'TN'
        assert "TN" not in result["imputed_features"]

    def test_unexpected_error_fallback(self, monkeypatch):
        """model.predict 抛异常 → status=fallback, fallback_reason=unexpected_error"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models import model_6

        class CrashModel:
            def predict(self, df):
                raise RuntimeError("predict crashed")
        monkeypatch.setattr(model_6, "_SOC_MODEL", CrashModel())
        result = model_6.model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "fallback"
        assert result["fallback_reason"] == "unexpected_error"

    def test_backward_compat_import(self):
        """__init__.py 的 from .model_6 import model_6_execution 仍可用"""
        from framework.domain.other_models import model_6_execution
        assert callable(model_6_execution)


# ---- 集成测试（真实模型，可跳过）----

def _check_integration_available():
    try:
        from framework.domain.other_models import model_6
        return (
            model_6._SKLEARN_AVAILABLE
            and model_6._ensure_models_loaded()
        )
    except Exception:
        return False


@pytest.mark.skipif(
    not _check_integration_available(),
    reason="sklearn 或模型文件不可用"
)
class TestModel6Integration:
    def test_real_soc_prediction_in_range(self):
        """真实预测：典型土壤样本 → SOC 在 0-50 g/kg 合理范围"""
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"
        assert 0.0 <= result["soc_prediction"] <= 50.0

    def test_real_dose_prediction_in_range(self):
        """真实预测：Dose 在 0-1000 t/ha 合理范围"""
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"
        assert 0.0 <= result["dose_prediction"] <= 1000.0

    def test_real_model_files_exist(self):
        """验证 .joblib 与 metadata.json 文件存在且可加载"""
        from framework.domain.other_models.model_6 import (
            _SOC_MODEL_PATH, _SOC_META_PATH, _DOSE_MODEL_PATH, _DOSE_META_PATH
        )
        assert _SOC_MODEL_PATH.exists()
        assert _SOC_META_PATH.exists()
        assert _DOSE_MODEL_PATH.exists()
        assert _DOSE_META_PATH.exists()


# ---- Task 4: 区域路由基础设施测试 ----

class TestNormalizeInput:
    def test_sombe_mapped_to_socbe(self):
        from framework.domain.other_models.model_6 import _normalize_input
        result = _normalize_input({"SOMbe": 15.0, "pH": 6.5})
        assert "SOCbe" in result
        assert "SOMbe" not in result
        assert result["SOCbe"] == 15.0
        assert result["pH"] == 6.5

    def test_sombe_with_trailing_space_stripped_then_mapped(self):
        from framework.domain.other_models.model_6 import _normalize_input
        result = _normalize_input({"SOMbe ": 15.0, "TN ": 1.2})
        assert "SOCbe" in result
        assert "SOMbe" not in result
        assert "TN" in result  # strip 尾随空格
        assert result["TN"] == 1.2

    def test_none_values_filtered(self):
        from framework.domain.other_models.model_6 import _normalize_input
        result = _normalize_input({"pH": None, "SOCbe": 12.0})
        assert "pH" not in result
        assert result["SOCbe"] == 12.0

    def test_none_input_returns_empty(self):
        from framework.domain.other_models.model_6 import _normalize_input
        assert _normalize_input(None) == {}

    def test_socbe_unchanged(self):
        from framework.domain.other_models.model_6 import _normalize_input
        result = _normalize_input({"SOCbe": 12.0})
        assert result == {"SOCbe": 12.0}


class TestShaoguanAreaCodes:
    def test_lechang_is_shaoguan(self):
        from framework.domain.other_models.model_6 import SHAOGUAN_AREA_CODES
        assert "lechang" in SHAOGUAN_AREA_CODES

    def test_other_codes_not_in_set(self):
        from framework.domain.other_models.model_6 import SHAOGUAN_AREA_CODES
        assert "other" not in SHAOGUAN_AREA_CODES
        assert "guangzhou" not in SHAOGUAN_AREA_CODES


class TestEnsureSgModelLoaded:
    def test_upland_load_success(self, monkeypatch):
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SG_UPLAND_MODEL", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_META", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_LOAD_FAILED", False)

        fake_meta = {"feature_names": ["pH"], "metrics": {"test_r2": 0.6}, "feature_means": {"pH": 7.0}}
        def fake_load(mp, mt):
            return FakeModel(), fake_meta
        monkeypatch.setattr(model_6, "_load_model_and_meta", fake_load)

        ok = model_6._ensure_sg_model_loaded("upland")
        assert ok is True
        assert model_6._SG_UPLAND_MODEL is not None
        assert model_6._SG_UPLAND_META == fake_meta

    def test_paddy_load_success(self, monkeypatch):
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SG_PADDY_MODEL", None)
        monkeypatch.setattr(model_6, "_SG_PADDY_META", None)
        monkeypatch.setattr(model_6, "_SG_PADDY_LOAD_FAILED", False)

        fake_meta = {"feature_names": ["pH"], "metrics": {"test_r2": 0.55}, "feature_means": {"pH": 7.0}}
        def fake_load(mp, mt):
            return FakeModel(), fake_meta
        monkeypatch.setattr(model_6, "_load_model_and_meta", fake_load)

        ok = model_6._ensure_sg_model_loaded("paddy")
        assert ok is True
        assert model_6._SG_PADDY_MODEL is not None

    def test_load_failure_sets_flag(self, monkeypatch):
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SG_UPLAND_MODEL", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_META", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_LOAD_FAILED", False)

        def boom(mp, mt):
            raise FileNotFoundError("missing")
        monkeypatch.setattr(model_6, "_load_model_and_meta", boom)

        ok = model_6._ensure_sg_model_loaded("upland")
        assert ok is False
        assert model_6._SG_UPLAND_LOAD_FAILED is True

    def test_invalid_land_type_routes_to_upland(self, monkeypatch):
        """land_type 非法值（如 'foo'）应走 upland 分支"""
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SG_UPLAND_MODEL", FakeModel())
        monkeypatch.setattr(model_6, "_SG_UPLAND_META", {"feature_names": [], "metrics": {"test_r2": 0.5}, "feature_means": {}})
        monkeypatch.setattr(model_6, "_SG_UPLAND_LOAD_FAILED", False)

        ok = model_6._ensure_sg_model_loaded("foo")
        assert ok is True  # 走 upland 已加载


# ---- Task 5: SG 区域路由测试用 mock 数据 ----

FAKE_SG_UPLAND_META = {
    "model_type": "RandomForestRegressor",
    "land_type": "upland",
    "region": "shaoguan",
    "model_version": "SG_RF_v1_20260731",
    "feature_names": ["pH", "SOCbe", "TN", "TP", "TK", "AP", "AK", "Gap", "Fertilizer type"],
    "feature_means": {
        "pH": 7.0, "SOCbe": 12.0, "TN": 0.8, "TP": 0.5, "TK": 30.0,
        "AP": 50.0, "AK": 100.0, "Gap": 10.0, "Fertilizer type": 1.5,
    },
    "metrics": {"cv_r2": 0.55, "cv_rmse": 40.0, "test_r2": 0.62, "test_rmse": 38.0},
    "training_samples": 185,
}

FAKE_SG_PADDY_META = {
    "model_type": "RandomForestRegressor",
    "land_type": "paddy",
    "region": "shaoguan",
    "model_version": "SG_RF_v1_20260731",
    "feature_names": ["pH", "SOCbe", "TN", "TP", "TK", "AP", "AK", "Gap", "Fertilizer type"],
    "feature_means": {
        "pH": 6.5, "SOCbe": 14.0, "TN": 1.0, "TP": 0.6, "TK": 28.0,
        "AP": 45.0, "AK": 90.0, "Gap": 8.0, "Fertilizer type": 1.5,
    },
    "metrics": {"cv_r2": 0.40, "cv_rmse": 45.0, "test_r2": 0.48, "test_rmse": 42.0},
    "training_samples": 25,  # <30 触发低置信度提示
}


def _setup_mock_sg_models(monkeypatch):
    """将 SG 模型状态设为 mock 值，模拟 SG 模型已加载。需配合 _setup_mock_models 使用。"""
    from framework.domain.other_models import model_6
    monkeypatch.setattr(model_6, "_SG_UPLAND_MODEL", FakeModel())
    monkeypatch.setattr(model_6, "_SG_PADDY_MODEL", FakeModel())
    monkeypatch.setattr(model_6, "_SG_UPLAND_META", FAKE_SG_UPLAND_META)
    monkeypatch.setattr(model_6, "_SG_PADDY_META", FAKE_SG_PADDY_META)
    monkeypatch.setattr(model_6, "_SG_UPLAND_LOAD_FAILED", False)
    monkeypatch.setattr(model_6, "_SG_PADDY_LOAD_FAILED", False)


# ---- Task 5: model_6_execution 区域路由测试 ----

class TestModel6ShaoguanRouting:
    def test_non_shaoguan_uses_global_etr(self, monkeypatch):
        """area_code='other' → Dose+SOC 走全局 ETR（回归测试，行为不变）"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="other")
        result = model_6_execution(inp)
        assert result["status"] == "success"
        assert result["dose_prediction"] == 42.0  # FakeModel 返回 42
        assert result["soc_prediction"] == 42.0
        assert result["dose_confidence"] == 0.47  # FAKE_DOSE_META test_r2
        assert "韶关" not in result["dose_warning"]

    def test_non_shaoguan_default_area_code(self, monkeypatch):
        """不传 area_code → 空字符串 → 不命中 → 全局 ETR"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"
        assert "韶关" not in result["dose_warning"]

    def test_shaoguan_upland_uses_sg_rf(self, monkeypatch):
        """area_code='lechang', land_type='upland' → Dose 走 SG upland RF, SOC 走 ETR"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="upland")
        assert result["status"] == "success"
        assert result["dose_prediction"] == 42.0  # SG FakeModel 也返回 42
        assert result["soc_prediction"] == 42.0
        assert result["dose_confidence"] == 0.62  # FAKE_SG_UPLAND_META test_r2
        assert "韶关" in result["dose_warning"]
        assert "旱地" in result["dose_warning"]
        assert "0.62" in result["dose_warning"]

    def test_shaoguan_paddy_uses_sg_rf(self, monkeypatch):
        """area_code='lechang', land_type='paddy' → Dose 走 SG paddy RF"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="paddy")
        assert result["status"] == "success"
        assert result["dose_confidence"] == 0.48  # FAKE_SG_PADDY_META test_r2
        assert "韶关" in result["dose_warning"]
        assert "水田" in result["dose_warning"]
        assert "0.48" in result["dose_warning"]

    def test_shaoguan_soc_always_global_etr(self, monkeypatch):
        """韶关区域 SOC 仍走全局 ETR（soc_confidence 用 ETR test_r2=0.91）"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="upland")
        assert result["soc_confidence"] == 0.91  # FAKE_SOC_META test_r2，非 SG

    def test_shaoguan_area_code_case_insensitive(self, monkeypatch):
        """area_code='LeChang' → .lower() → 命中韶关"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="LeChang")
        result = model_6_execution(inp, land_type="upland")
        assert result["status"] == "success"
        assert "韶关" in result["dose_warning"]

    def test_land_type_default_upland(self, monkeypatch):
        """未传 land_type → 默认 upland"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp)  # 不传 land_type
        assert result["status"] == "success"
        assert "旱地" in result["dose_warning"]  # 默认 upland

    def test_land_type_invalid_defaults_upland_with_warning(self, monkeypatch):
        """land_type='foo' → 默认 upland + dose_warning 含未识别提示"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="foo")
        assert result["status"] == "success"
        assert "旱地" in result["dose_warning"]
        assert "foo" in result["dose_warning"] or "未识别" in result["dose_warning"]

    def test_sombe_input_mapped_to_socbe(self, monkeypatch):
        """输入含 SOMbe → _normalize_input 映射为 SOCbe → 不被当缺失填充"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        # 用 SOMbe 替换 SOCbe，area_code 非韶关走全局 ETR
        inp = {k: v for k, v in FULL_VALID_INPUT.items() if k != "SOCbe"}
        inp["SOMbe"] = 15.0
        inp["area_code"] = "other"
        result = model_6_execution(inp)
        assert result["status"] == "success"
        # SOCbe 应被正确识别，不进 imputed_features
        assert "SOCbe" not in result["imputed_features"]

    def test_shaoguan_paddy_low_sample_warning(self, monkeypatch):
        """水田 training_samples<30 → dose_warning 含低置信度提示"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="paddy")
        assert "样本" in result["dose_warning"] or "置信度" in result["dose_warning"]

    def test_shaoguan_model_missing_fallback(self, monkeypatch):
        """SG 模型文件缺失 → fallback, fallback_reason=model_file_missing"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models import model_6
        monkeypatch.setattr(model_6, "_SG_UPLAND_MODEL", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_META", None)
        monkeypatch.setattr(model_6, "_SG_UPLAND_LOAD_FAILED", True)
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6.model_6_execution(inp, land_type="upland")
        assert result["status"] == "fallback"
        assert result["fallback_reason"] == "model_file_missing"

    def test_backward_compat_no_land_type_param(self, monkeypatch):
        """旧调用方不传 land_type → 默认 upland，签名向后兼容"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        result = model_6_execution(FULL_VALID_INPUT)
        assert result["status"] == "success"

    def test_shaoguan_land_type_not_specified_warning(self, monkeypatch):
        """spec L82-83: 韶关区域 land_type 未传 → dose_warning 追加'未指定 land_type'提示"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp)  # 不传 land_type → None
        assert result["status"] == "success"
        assert result["dose_confidence"] == 0.62  # 走 upland SG RF
        assert "未指定 land_type" in result["dose_warning"]
        assert "旱地" in result["dose_warning"]

    def test_non_shaoguan_ignores_invalid_land_type(self, monkeypatch):
        """spec L71: 非韶关区域 SHALL 忽略 land_type（非法值不产生提示）"""
        _setup_mock_models(monkeypatch)
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="other")
        result = model_6_execution(inp, land_type="foo")
        assert result["status"] == "success"
        assert "韶关" not in result["dose_warning"]
        assert "land_type" not in result["dose_warning"]
        assert "未识别" not in result["dose_warning"]


# ---- Task 6: FertilityMLAgent 透传测试 ----

class TestFertilityMLAgentPassthrough:
    def test_execute_passes_land_type_to_model_6(self, monkeypatch):
        """execute(task) 应从 task['land_type'] 提取并传给 model_6_execution"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent

        captured = {}
        def spy_model_6(inp, land_type="upland"):
            captured["land_type"] = land_type
            captured["area_code"] = inp.get("area_code")
            return {
                "status": "success",
                "soc_prediction": 42.0, "soc_confidence": 0.91,
                "dose_prediction": 42.0, "dose_confidence": 0.62,
                "dose_warning": "韶关旱地 RF 模型 R²=0.62",
                "imputed_features": [], "imputation_applied": False,
                "model_version": "ETR_v1_20260713",
            }
        monkeypatch.setattr(
            "framework.agents.specialized.fertility_ml_agent.model_6_execution",
            spy_model_6,
        )

        agent = FertilityMLAgent()
        task = dict(FULL_VALID_INPUT, area_code="lechang", land_type="upland")
        agent.execute(task)
        assert captured["land_type"] == "upland"
        assert captured["area_code"] == "lechang"

    def test_execute_default_land_type_when_missing(self, monkeypatch):
        """task 不含 land_type → 传 None 给 model_6（由 model 默认 upland 并追加提示）"""
        _setup_mock_models(monkeypatch)
        from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent

        captured = {}
        def spy_model_6(inp, land_type="upland"):
            captured["land_type"] = land_type
            return {"status": "success", "soc_prediction": 1.0, "soc_confidence": 0.5,
                    "dose_prediction": 1.0, "dose_confidence": 0.5, "dose_warning": "x",
                    "imputed_features": [], "imputation_applied": False, "model_version": "v"}
        monkeypatch.setattr(
            "framework.agents.specialized.fertility_ml_agent.model_6_execution",
            spy_model_6,
        )

        agent = FertilityMLAgent()
        agent.execute({"pH": 6.5})
        assert captured["land_type"] is None

    def test_answer_question_enriches_task_with_context_area_code(self, monkeypatch):
        """answer_question 应从 context 顶层提取 area_code/land_type 注入 task"""
        _setup_mock_models(monkeypatch)
        _setup_mock_sg_models(monkeypatch)
        from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent

        captured = {}
        def spy_model_6(inp, land_type="upland"):
            captured["area_code"] = inp.get("area_code")
            captured["land_type"] = land_type
            return {"status": "success", "soc_prediction": 1.0, "soc_confidence": 0.5,
                    "dose_prediction": 1.0, "dose_confidence": 0.5, "dose_warning": "x",
                    "imputed_features": [], "imputation_applied": False, "model_version": "v"}
        monkeypatch.setattr(
            "framework.agents.specialized.fertility_ml_agent.model_6_execution",
            spy_model_6,
        )

        agent = FertilityMLAgent()
        # context 顶层有 area_code/land_type，data 里没有
        context = {"area_code": "lechang", "land_type": "paddy", "data": {"pH": 6.5}}
        agent.answer_question("施肥量多少", context)
        assert captured["area_code"] == "lechang"
        assert captured["land_type"] == "paddy"

    def test_answer_question_task_data_takes_precedence(self, monkeypatch):
        """context['data'] 内的 area_code 优先于 context 顶层"""
        _setup_mock_models(monkeypatch)
        from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent

        captured = {}
        def spy_model_6(inp, land_type="upland"):
            captured["area_code"] = inp.get("area_code")
            return {"status": "success", "soc_prediction": 1.0, "soc_confidence": 0.5,
                    "dose_prediction": 1.0, "dose_confidence": 0.5, "dose_warning": "x",
                    "imputed_features": [], "imputation_applied": False, "model_version": "v"}
        monkeypatch.setattr(
            "framework.agents.specialized.fertility_ml_agent.model_6_execution",
            spy_model_6,
        )

        agent = FertilityMLAgent()
        context = {
            "area_code": "other",
            "data": {"pH": 6.5, "area_code": "lechang"},  # data 内优先
        }
        agent.answer_question("施肥量", context)
        assert captured["area_code"] == "lechang"


# ---- Task 7: nodes.execute_models 透传 land_type 测试 ----

class TestExecuteModelsLandTypePassthrough:
    def test_execute_models_passes_land_type_to_agent_context(self, monkeypatch):
        """execute_models 应将 request['land_type'] 透传到 agent_manager.process 的 context 顶层"""
        from framework.agents import nodes
        from framework.agents import manager as manager_mod

        captured = {}
        def fake_process(question, context):
            captured["context"] = context
            return {"status": "ok", "data": {"summary": "", "details": {}, "agents_invoked": [], "recommendations": []}}
        # agent_manager 在 execute_models 内部通过 from framework.agents.manager import agent_manager 引入
        monkeypatch.setattr(manager_mod, "agent_manager", type("M", (), {"process": staticmethod(fake_process)})())

        state = {
            "request": {
                "question": "施肥量多少",
                "area_code": "lechang",
                "land_type": "paddy",
            },
            "data": {},
            "question_type": 1,
        }
        nodes.execute_models(state)
        assert captured["context"]["land_type"] == "paddy"
        assert captured["context"]["area_code"] == "lechang"

    def test_execute_models_without_land_type_omits_key(self, monkeypatch):
        """request 不含 land_type → context 不含 land_type（agent 侧默认 upland）"""
        from framework.agents import nodes
        from framework.agents import manager as manager_mod

        captured = {}
        def fake_process(question, context):
            captured["context"] = context
            return {"status": "ok", "data": {"summary": "", "details": {}, "agents_invoked": [], "recommendations": []}}
        monkeypatch.setattr(manager_mod, "agent_manager", type("M", (), {"process": staticmethod(fake_process)})())

        state = {
            "request": {"question": "施肥量", "area_code": "lechang"},
            "data": {},
            "question_type": 1,
        }
        nodes.execute_models(state)
        assert "land_type" not in captured["context"]


# ---- Task 8: SG 真实模型集成测试（模型不可用时跳过）----

def _check_sg_integration_available():
    try:
        from framework.domain.other_models import model_6
        return (
            model_6._SKLEARN_AVAILABLE
            and model_6._ensure_models_loaded()
            and model_6._ensure_sg_model_loaded("upland")
            and model_6._ensure_sg_model_loaded("paddy")
        )
    except Exception:
        return False


@pytest.mark.skipif(
    not _check_sg_integration_available(),
    reason="sklearn 或 SG 模型文件不可用"
)
class TestModel6ShaoguanIntegration:
    def test_real_sg_upland_dose_in_range(self):
        """真实 SG 旱地预测：Dose 在 0-1000 合理范围"""
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="upland")
        assert result["status"] == "success"
        assert 0.0 <= result["dose_prediction"] <= 1000.0
        assert "韶关" in result["dose_warning"]
        assert "旱地" in result["dose_warning"]

    def test_real_sg_paddy_dose_in_range(self):
        """真实 SG 水田预测：Dose 在 0-1000 合理范围"""
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="paddy")
        assert result["status"] == "success"
        assert 0.0 <= result["dose_prediction"] <= 1000.0
        assert "韶关" in result["dose_warning"]
        assert "水田" in result["dose_warning"]

    def test_real_sg_soc_uses_global_etr(self):
        """真实 SG 区域 SOC 仍走全局 ETR（soc_confidence 用 ETR test_r2）"""
        from framework.domain.other_models.model_6 import model_6_execution
        from framework.domain.other_models.model_6 import _SOC_META
        inp = dict(FULL_VALID_INPUT, area_code="lechang")
        result = model_6_execution(inp, land_type="upland")
        assert result["status"] == "success"
        assert result["soc_confidence"] == round(_SOC_META["metrics"]["test_r2"], 2)

    def test_real_sg_model_files_exist(self):
        """验证 SG .joblib 与 metadata.json 文件存在"""
        from framework.domain.other_models.model_6 import (
            _SG_UPLAND_MODEL_PATH, _SG_UPLAND_META_PATH,
            _SG_PADDY_MODEL_PATH, _SG_PADDY_META_PATH,
        )
        assert _SG_UPLAND_MODEL_PATH.exists()
        assert _SG_UPLAND_META_PATH.exists()
        assert _SG_PADDY_MODEL_PATH.exists()
        assert _SG_PADDY_META_PATH.exists()

    def test_real_non_shaoguan_unchanged(self):
        """真实非韶关预测：Dose 走全局 ETR，dose_warning 不含韶关"""
        from framework.domain.other_models.model_6 import model_6_execution
        inp = dict(FULL_VALID_INPUT, area_code="other")
        result = model_6_execution(inp)
        assert result["status"] == "success"
        assert "韶关" not in result["dose_warning"]
