import pytest
import numpy as np
from src.ai_culti_demo.farmland_diagnosis.config import (
    REGION_MAP, COEFFICIENTS, WEIGHTS, INDICATOR_NAME_MAP, calc_obstacle_level
)

def test_region_map():
    assert REGION_MAP['华南区'] == 'HN'
    assert REGION_MAP['长江中下游区'] == 'CJ'

def test_coefficients_exists():
    assert 'HN' in COEFFICIENTS
    assert 'CJ' in COEFFICIENTS
    assert 'PH' in COEFFICIENTS['HN']
    assert 'YJ' in COEFFICIENTS['HN']

def test_weights_exists():
    assert 'MNY' in WEIGHTS
    assert 'PH' in WEIGHTS['MNY']
    assert 'GG' in WEIGHTS['MNY']

def test_indicator_name_map():
    assert INDICATOR_NAME_MAP['PH'] == 'pH'
    assert INDICATOR_NAME_MAP['YJ'] == '有机质'

def test_calc_obstacle_level_ph_moderate():
    row = {'PH': 5.0}
    result = calc_obstacle_level(row, ['PH'])
    assert result['PH'] == '中度障碍'

def test_calc_obstacle_level_ph_no_obstacle():
    row = {'PH': 7.0}
    result = calc_obstacle_level(row, ['PH'])
    assert result['PH'] == '无障碍'

def test_calc_obstacle_level_ph_severe():
    row = {'PH': 4.0}
    result = calc_obstacle_level(row, ['PH'])
    assert result['PH'] == '重度障碍'

def test_calc_obstacle_level_organic_moderate():
    row = {'YJ': 15}
    result = calc_obstacle_level(row, ['YJ'])
    assert result['YJ'] == '中度障碍'

def test_calc_obstacle_level_organic_no_obstacle():
    row = {'YJ': 30}
    result = calc_obstacle_level(row, ['YJ'])
    assert result['YJ'] == '无障碍'

def test_calc_obstacle_level_multiple_indicators():
    row = {'PH': 6.5, 'YJ': 25, 'SXK': 80}
    result = calc_obstacle_level(row, ['PH', 'YJ', 'SXK'])
    assert result['PH'] == '无障碍'
    assert result['YJ'] == '轻度障碍'
    assert result['SXK'] == '中度障碍'
