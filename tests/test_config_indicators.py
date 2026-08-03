# tests/test_config_indicators.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_jhx_jla_in_all_and_continuous_indicators():
    from ai_culti_demo.farmland_diagnosis.config import (
        ALL_INDICATORS, CONTINUOUS_INDICATORS, INDICATOR_DISPLAY_MAP,
    )
    assert "JHX" in ALL_INDICATORS and "JLA" in ALL_INDICATORS
    assert "JHX" in CONTINUOUS_INDICATORS and "JLA" in CONTINUOUS_INDICATORS
    assert INDICATOR_DISPLAY_MAP["JHX"] == "交换性氢"
    assert INDICATOR_DISPLAY_MAP["JLA"] == "交换性铝"

def test_storage_all_indicators_matches_config():
    from ai_culti_demo.farmland_diagnosis.config import ALL_INDICATORS
    from ai_culti_demo.farmland_diagnosis.storage import _ALL_INDICATORS
    assert _ALL_INDICATORS == ALL_INDICATORS
