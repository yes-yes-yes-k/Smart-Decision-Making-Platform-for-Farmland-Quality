# tests/calculations/test_organic_matter_calculation.py
"""Model-5 有机质培肥 — RF 模型预测 Dose 的单元测试.

覆盖:
1. 降级规则返回正值 (degrade_to_rules)
2. RF 模型文件不存在时降级到规则, simulated=True
3. RF 模型可用时返回模型预测值, simulated=False
4. 特征映射: indicators dict → [pH, SOMbe, AK, AP, TN] 顺序传入 rf.predict
"""
from unittest import mock

from framework.domain.calculations.organic_matter_calculation import (
    predict_dose,
    degrade_to_rules,
)


def test_degrade_to_rules_returns_dose():
    """降级规则返回推荐施用量."""
    indicators = {"pH": 5.5, "SOMbe": 22.0, "AK": 90.0, "AP": 12.0, "TN": 1.5}
    dose = degrade_to_rules(indicators)
    assert dose > 0


def test_predict_dose_degrades_when_model_missing():
    """RF 模型文件不存在时降级到规则."""
    indicators = {"pH": 5.5, "SOMbe": 22.0, "AK": 90.0, "AP": 12.0, "TN": 1.5}
    with mock.patch(
        "framework.domain.calculations.organic_matter_calculation.os.path.exists",
        return_value=False,
    ):
        dose, simulated = predict_dose(indicators, "upland")
    assert dose > 0
    assert simulated is True


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
    ):
        dose, simulated = predict_dose(indicators, "upland")
    assert dose == 150.0
    assert simulated is False


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
    ):
        predict_dose(indicators, "paddy")
    # 验证 rf.predict 被调用一次, 入参为 [[pH, SOMbe, AK, AP, TN]]
    fake_rf.predict.assert_called_once_with([[6.0, 25.0, 110.0, 15.0, 2.0]])
