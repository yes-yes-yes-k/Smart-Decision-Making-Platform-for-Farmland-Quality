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


# Storage tests
from src.ai_culti_demo.farmland_diagnosis.storage import DiagnosisStorage
import tempfile
import os
import sqlite3

def test_storage_create_tables():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        storage.create_tables()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        assert 'evaluation_results' in tables
        assert 'diagnosis_results' in tables
        assert 'acidification_results' in tables
        conn.close()

def test_storage_save_and_get_evaluation():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        storage.create_tables()

        record = {
            'parcel_id': 'test-001',
            'region_code': 'HN',
            'secondary_region_code': 'MNY',
            'PH': 6.5, 'YJ': 25, 'YXP': 30, 'SXK': 150, 'RZ': 1.2,
            'GZ': 'RT', 'GG': 'FS', 'PS': 'CM', 'DX': 'PLT', 'ZD': 'TLBC',
            'YXT': 100, 'GCH': 20,
            'PH_LD': 1.0, 'YJ_LD': 1.0, 'YXP_LD': 0.8, 'SXK_LD': 0.8, 'RZ_LD': 1.0,
            'GZ_LD': 1.0, 'GG_LD': 1.0, 'PS_LD': 1.0, 'DX_LD': 1.0, 'ZD_LD': 1.0,
            'YXT_LD': 1.0, 'GCH_LD': 1.0,
            'composite_weight': 0.85,
            'grade': '3'
        }

        count = storage.save_evaluation([record])
        assert count == 1

        result = storage.get_evaluation('test-001')
        assert result is not None
        assert result['parcel_id'] == 'test-001'
        assert result['PH'] == 6.5

def test_storage_save_and_get_diagnosis():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        storage.create_tables()

        eval_record = {
            'parcel_id': 'test-001',
            'region_code': 'HN', 'secondary_region_code': 'MNY',
            'PH': 5.0, 'YJ': 25, 'YXP': 30, 'SXK': 150, 'RZ': 1.2,
            'GZ': 'RT', 'GG': 'FS', 'PS': 'CM', 'DX': 'PLT', 'ZD': 'TLBC',
            'YXT': 100, 'GCH': 20,
            'PH_LD': 0.5, 'YJ_LD': 1.0, 'YXP_LD': 0.8, 'SXK_LD': 0.8, 'RZ_LD': 1.0,
            'GZ_LD': 1.0, 'GG_LD': 1.0, 'PS_LD': 1.0, 'DX_LD': 1.0, 'ZD_LD': 1.0,
            'YXT_LD': 1.0, 'GCH_LD': 1.0,
            'composite_weight': 0.85, 'grade': '3'
        }
        storage.save_evaluation([eval_record])

        diag_record = {
            'parcel_id': 'test-001',
            'obstacle_type': '单一障碍',
            'main_factors': ['pH(中度障碍, 25.0%)'],
            'secondary_factors': [],
            'PH_obstacle_level': '中度障碍',
            'PH_obstacle_degree': 0.25
        }
        storage.save_diagnosis([diag_record])

        result = storage.get_diagnosis('test-001')
        assert result is not None
        assert result['obstacle_type'] == '单一障碍'
        assert result['main_factors'] == ['pH(中度障碍, 25.0%)']

def test_storage_is_ready():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        assert not storage.is_ready()

        storage.create_tables()
        assert not storage.is_ready()

        eval_record = {
            'parcel_id': 'test-001', 'region_code': 'HN', 'secondary_region_code': 'MNY',
            'PH': 6.5, 'YJ': 25, 'YXP': 30, 'SXK': 150, 'RZ': 1.2,
            'GZ': 'RT', 'GG': 'FS', 'PS': 'CM', 'DX': 'PLT', 'ZD': 'TLBC',
            'YXT': 100, 'GCH': 20,
            'PH_LD': 1.0, 'YJ_LD': 1.0, 'YXP_LD': 0.8, 'SXK_LD': 0.8, 'RZ_LD': 1.0,
            'GZ_LD': 1.0, 'GG_LD': 1.0, 'PS_LD': 1.0, 'DX_LD': 1.0, 'ZD_LD': 1.0,
            'YXT_LD': 1.0, 'GCH_LD': 1.0,
            'composite_weight': 0.85, 'grade': '3'
        }
        storage.save_evaluation([eval_record])

        diag_record = {
            'parcel_id': 'test-001', 'obstacle_type': '无明显障碍',
            'main_factors': [], 'secondary_factors': []
        }
        storage.save_diagnosis([diag_record])

        assert storage.is_ready()


# Evaluation tests
from src.ai_culti_demo.farmland_diagnosis.evaluation import bulk_evaluate, evaluate_single, calc_continuous, calc_discrete
import pandas as pd

def test_evaluate_single():
    row = pd.Series({
        'JY': 'HN', 'EJ': 'MNY',
        'PH': 6.5, 'YJ': 25, 'YXP': 30, 'SXK': 150, 'RZ': 1.2,
        'GZ': 'RT', 'GG': 'FS', 'PS': 'CM', 'DX': 'PLT', 'ZD': 'TLBC',
        'YXT': 100, 'GCH': 20
    })

    result = evaluate_single(row, 'HN', 'MNY')

    assert 'PH_LD' in result
    assert 'composite_weight' in result
    assert 'grade' in result
    # 优质数据应评为最高等级1级
    assert result['grade'] == '1'

def test_bulk_evaluate():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''一级农业区,二级农业区,pH,有机质,有效磷,速效钾,容重,耕层质地,灌溉能力,排水能力,地形部位,质地构型,有效土层,耕层厚度
华南区,闽南粤中农林水产区,6.5,25,30,150,1.2,壤土,充分满足,充分满足,平原低阶,上松下紧型,100,20
''')

        db_path = os.path.join(tmpdir, 'test.db')
        result = bulk_evaluate(csv_path, db_path)

        assert result['status'] == 'ok'
        assert result['processed'] == 1

        storage = DiagnosisStorage(db_path)
        eval_result = storage.get_evaluation('0')
        assert eval_result is not None
        assert eval_result['PH'] == 6.5
        # 优质数据应评为最高等级1级
        assert eval_result['grade'] == '1'

def test_bulk_evaluate_missing_columns():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('pH,有机质\n6.5,25\n')

        result = bulk_evaluate(csv_path)
        assert result['status'] == 'error'
        assert 'Missing columns' in result['message']

def test_calc_continuous():
    params = {'a': 0.256941, 'c': 6.7, 'L': 4.0, 'U': 9.5}
    result = calc_continuous(6.5, params)
    assert 0.9 < result < 1.0

def test_calc_discrete():
    mapping = {'FS': 1, 'S': 0.8, 'BS': 0.6, 'US': 0.3}
    result = calc_discrete('FS', mapping)
    assert result == 1.0
