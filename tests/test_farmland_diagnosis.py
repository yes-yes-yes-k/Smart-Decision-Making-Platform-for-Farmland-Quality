import pytest
import numpy as np
from src.ai_culti_demo.farmland_diagnosis.config import (
    REGION_MAP, COEFFICIENTS, WEIGHTS, INDICATOR_DISPLAY_MAP,
    GRADE_CONFIG, ALL_INDICATORS, CONTINUOUS_INDICATORS, DISCRETE_INDICATORS,
    calc_obstacle_level
)

def test_region_map():
    assert REGION_MAP['华南区'] == 'HN'
    assert REGION_MAP['长江中下游区'] == 'CJ'

def test_coefficients_exists():
    assert 'HN' in COEFFICIENTS
    assert 'CJ' in COEFFICIENTS
    assert 'SJD' in COEFFICIENTS['HN']
    assert 'YJZ' in COEFFICIENTS['HN']

def test_weights_exists():
    assert 'MNY' in WEIGHTS
    assert 'SJD' in WEIGHTS['MNY']
    assert 'GGNL' in WEIGHTS['MNY']

def test_indicator_display_map():
    assert INDICATOR_DISPLAY_MAP['SJD'] == 'pH'
    assert INDICATOR_DISPLAY_MAP['YJZ'] == '有机质'

def test_grade_config_exists():
    assert 'HN' in GRADE_CONFIG
    assert 'CJ' in GRADE_CONFIG
    assert len(GRADE_CONFIG['HN'][0]) == 11  # 10 个边界 + inf

def test_indicator_constants():
    assert len(ALL_INDICATORS) == 12
    assert set(CONTINUOUS_INDICATORS) | set(DISCRETE_INDICATORS) == set(ALL_INDICATORS)
    assert set(CONTINUOUS_INDICATORS) & set(DISCRETE_INDICATORS) == set()

def test_calc_obstacle_level_sjd_moderate():
    row = {'SJD': 5.0}
    result = calc_obstacle_level(row, ['SJD'])
    assert result['SJD'] == '中度障碍'

def test_calc_obstacle_level_sjd_no_obstacle():
    row = {'SJD': 7.0}
    result = calc_obstacle_level(row, ['SJD'])
    assert result['SJD'] == '无障碍'

def test_calc_obstacle_level_sjd_severe():
    row = {'SJD': 4.0}
    result = calc_obstacle_level(row, ['SJD'])
    assert result['SJD'] == '重度障碍'

def test_calc_obstacle_level_organic_moderate():
    row = {'YJZ': 15}
    result = calc_obstacle_level(row, ['YJZ'])
    assert result['YJZ'] == '中度障碍'

def test_calc_obstacle_level_organic_no_obstacle():
    row = {'YJZ': 30}
    result = calc_obstacle_level(row, ['YJZ'])
    assert result['YJZ'] == '无障碍'

def test_calc_obstacle_level_multiple_indicators():
    row = {'SJD': 6.5, 'YJZ': 25, 'SXJ': 80}
    result = calc_obstacle_level(row, ['SJD', 'YJZ', 'SXJ'])
    assert result['SJD'] == '无障碍'
    assert result['YJZ'] == '轻度障碍'
    assert result['SXJ'] == '中度障碍'

def test_calc_obstacle_level_gczd_uses_lsd():
    # GCZD 障碍等级依赖隶属度列 GCZDLSD
    row = {'GCZDLSD': 0.5}
    result = calc_obstacle_level(row, ['GCZD'])
    assert result['GCZD'] == '重度障碍'

def test_calc_obstacle_level_dxbw_uses_lsd():
    row = {'DXBWLSD': 0.3}
    result = calc_obstacle_level(row, ['DXBW'])
    assert result['DXBW'] == '重度障碍'


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


# Diagnosis tests
from src.ai_culti_demo.farmland_diagnosis.diagnosis import diagnosis_row, diagnose, query_parcel

def test_diagnosis_row_single_obstacle():
    row = pd.Series({
        'pH障碍等级': '中度障碍', 'pH_OD': 0.25,
        '有机质障碍等级': '无障碍', '有机质_OD': 0.05
    })

    result = diagnosis_row(row)

    assert result['obstacle_type'] == '单一障碍'
    assert len(result['main_factors']) == 1
    assert 'pH' in result['main_factors'][0]

def test_diagnosis_row_multi_obstacle():
    row = pd.Series({
        'pH障碍等级': '中度障碍', 'pH_OD': 0.25,
        '有机质障碍等级': '中度障碍', '有机质_OD': 0.20,
        '有效磷障碍等级': '轻度障碍', '有效磷_OD': 0.15
    })

    result = diagnosis_row(row)

    assert result['obstacle_type'] == '多障碍'
    assert len(result['main_factors']) >= 2

def test_diagnosis_row_no_obstacle():
    row = pd.Series({
        'pH障碍等级': '无障碍', 'pH_OD': 0.05,
        '有机质障碍等级': '无障碍', '有机质_OD': 0.03
    })

    result = diagnosis_row(row)

    assert result['obstacle_type'] == '无明显障碍'
    assert result['main_factors'] == []

def test_diagnose_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''一级农业区,二级农业区,pH,有机质,有效磷,速效钾,容重,耕层质地,灌溉能力,排水能力,地形部位,质地构型,有效土层,耕层厚度
华南区,闽南粤中农林水产区,4.5,10,5,50,1.8,粘土,基本满足,基本满足,丘陵岗地,夹砂型,60,15
''')

        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)
        result = diagnose(db_path)

        assert result['status'] == 'ok'
        assert result['diagnosed'] == 1

        query_result = query_parcel('0', db_path)
        assert query_result['status'] == 'ok'
        assert 'diagnosis' in query_result


# Acidification tests
from src.ai_culti_demo.farmland_diagnosis.acidification import classify_acidification, generate_amendment, evaluate_acidification, query_acidification

def test_classify_acidification_severe():
    result = classify_acidification(4.0, 'HN')
    assert result['level'] == 'severe'
    assert result['description'] == '强酸性'

def test_classify_acidification_moderate():
    result = classify_acidification(5.0, 'HN')
    assert result['level'] == 'moderate'
    assert result['description'] == '酸性'

def test_classify_acidification_slight():
    result = classify_acidification(6.0, 'HN')
    assert result['level'] == 'slight'
    assert result['description'] == '微酸性'

def test_classify_acidification_neutral():
    result = classify_acidification(7.0, 'HN')
    assert result['level'] == 'neutral'
    assert result['description'] == '中性'

def test_generate_amendment_severe():
    result = generate_amendment(4.0, 10, 'HN')
    assert result['need_amendment'] == True
    assert len(result['amendment_plan']) > 0

def test_generate_amendment_no_need():
    result = generate_amendment(7.0, 20, 'HN')
    assert result['need_amendment'] == False
    assert result['amendment_plan'] == []

def test_evaluate_acidification_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''一级农业区,二级农业区,pH,有机质,有效磷,速效钾,容重,耕层质地,灌溉能力,排水能力,地形部位,质地构型,有效土层,耕层厚度
华南区,闽南粤中农林水产区,4.5,10,5,50,1.8,粘土,基本满足,基本满足,丘陵岗地,夹砂型,60,15
''')

        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)
        diagnose(db_path)  # 需要先运行诊断确保 is_ready 返回 True
        result = evaluate_acidification(db_path)

        assert result['status'] == 'ok'
        assert result['evaluated'] == 1

        query_result = query_acidification('0', db_path)
        assert query_result['status'] == 'ok'
        assert 'acidification' in query_result
