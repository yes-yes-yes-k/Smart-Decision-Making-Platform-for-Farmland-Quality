# tests/calculations/test_organic_matter_calculation.py
"""Model-5 有机质培肥 — RF 模型预测 Dose 的单元测试.

覆盖模型、依赖、输入不可用时的空值语义，以及真实 RF 路径回归。
"""
from unittest import mock

from framework.domain.calculations.organic_matter_calculation import (
    MODEL5_INPUT_MISSING,
    MODEL5_MODEL_UNAVAILABLE,
    MODEL5_PREDICTION_FAILED,
    predict_dose,
)


def test_predict_dose_rejects_missing_features_without_default_numbers():
    result = predict_dose({"pH": 5.5, "SOMbe": 22.0}, "upland")
    assert result.dose is None
    assert result.simulated is True
    assert result.reason == MODEL5_INPUT_MISSING


def test_predict_dose_degrades_when_model_missing_without_rule_value():
    indicators = {"pH": 5.5, "SOMbe": 22.0, "AK": 90.0, "AP": 12.0, "TN": 1.5}
    with mock.patch(
        "framework.domain.calculations.organic_matter_calculation.os.path.exists",
        return_value=False,
    ):
        result = predict_dose(indicators, "upland")
    assert result.dose is None
    assert result.simulated is True
    assert result.reason == MODEL5_MODEL_UNAVAILABLE


def test_predict_dose_uses_rf_when_available():
    """RF 模型可用时 simulated=False."""
    indicators = {"pH": 5.5, "SOMbe": 22.0, "AK": 90.0, "AP": 12.0, "TN": 1.5}
    fake_rf = mock.MagicMock()
    fake_rf.predict.return_value = [150.0]
    with mock.patch(
        "framework.domain.calculations.organic_matter_calculation.os.path.exists",
        return_value=True,
    ), mock.patch(
        "framework.domain.calculations.organic_matter_calculation._load_model",
        return_value=fake_rf,
    ), mock.patch(
        "framework.domain.calculations.organic_matter_calculation._artifact_version",
        return_value="upland-dose-test-v1",
    ):
        result = predict_dose(indicators, "upland")
    assert result.dose == 150.0
    assert result.simulated is False
    assert result.model_version == "upland-dose-test-v1"
    assert result.data_source == "rf_model"


def test_predict_dose_maps_indicators_to_features_in_order():
    """特征映射: indicators dict 按 [pH, SOMbe, AK, AP, TN] 顺序传入 rf.predict."""
    indicators = {"pH": 6.0, "SOMbe": 25.0, "AK": 110.0, "AP": 15.0, "TN": 2.0}
    fake_rf = mock.MagicMock()
    fake_rf.predict.return_value = [200.0]
    with mock.patch(
        "framework.domain.calculations.organic_matter_calculation.os.path.exists",
        return_value=True,
    ), mock.patch(
        "framework.domain.calculations.organic_matter_calculation._load_model",
        return_value=fake_rf,
    ), mock.patch(
        "framework.domain.calculations.organic_matter_calculation._artifact_version",
        return_value="paddy-dose-test-v1",
    ):
        predict_dose(indicators, "paddy")
    # 验证 rf.predict 被调用一次, 入参为 [[pH, SOMbe, AK, AP, TN]]
    fake_rf.predict.assert_called_once_with([[6.0, 25.0, 110.0, 15.0, 2.0]])


def test_predict_dose_prediction_exception_does_not_restore_rule_value():
    indicators = {"pH": 6.0, "SOMbe": 25.0, "AK": 110.0, "AP": 15.0, "TN": 2.0}
    fake_rf = mock.MagicMock()
    fake_rf.predict.side_effect = RuntimeError("boom")
    with mock.patch(
        "framework.domain.calculations.organic_matter_calculation.os.path.exists",
        return_value=True,
    ), mock.patch(
        "framework.domain.calculations.organic_matter_calculation._load_model",
        return_value=fake_rf,
    ):
        result = predict_dose(indicators, "paddy")
    assert result.dose is None
    assert result.reason == MODEL5_PREDICTION_FAILED
