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
            'SJD': 6.5, 'YJZ': 25, 'YXL': 30, 'SXJ': 150, 'TRRZ': 1.2,
            'GCZD': 'RT', 'GGNL': 'FS', 'PSNL': 'CM', 'DXBW': 'PLT', 'ZDGX': 'TLBC',
            'YXTCHD': 100, 'GCHD': 20,
            'SJDLSD': 1.0, 'YJZLSD': 1.0, 'YXLLSD': 0.8, 'SXJLSD': 0.8, 'TRRZLSD': 1.0,
            'GCZDLSD': 1.0, 'GGNLLSD': 1.0, 'PSNLLSD': 1.0, 'DXBWLSD': 1.0, 'ZDGXLSD': 1.0,
            'YXTCHDLSD': 1.0, 'GCHDLSD': 1.0,
            'ZHQZ': 0.85,
            'GDZLDJ': '3',
        }

        count = storage.save_evaluation([record])
        assert count == 1

        result = storage.get_evaluation('test-001')
        assert result is not None
        assert result['parcel_id'] == 'test-001'
        assert result['SJD'] == 6.5
        assert result['ZHQZ'] == 0.85
        assert result['GDZLDJ'] == '3'

def test_storage_save_and_get_diagnosis():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        storage.create_tables()

        eval_record = {
            'parcel_id': 'test-001',
            'region_code': 'HN', 'secondary_region_code': 'MNY',
            'SJD': 5.0, 'YJZ': 25, 'YXL': 30, 'SXJ': 150, 'TRRZ': 1.2,
            'GCZD': 'RT', 'GGNL': 'FS', 'PSNL': 'CM', 'DXBW': 'PLT', 'ZDGX': 'TLBC',
            'YXTCHD': 100, 'GCHD': 20,
            'SJDLSD': 0.5, 'YJZLSD': 1.0, 'YXLLSD': 0.8, 'SXJLSD': 0.8, 'TRRZLSD': 1.0,
            'GCZDLSD': 1.0, 'GGNLLSD': 1.0, 'PSNLLSD': 1.0, 'DXBWLSD': 1.0, 'ZDGXLSD': 1.0,
            'YXTCHDLSD': 1.0, 'GCHDLSD': 1.0,
            'ZHQZ': 0.85, 'GDZLDJ': '3',
        }
        storage.save_evaluation([eval_record])

        diag_record = {
            'parcel_id': 'test-001',
            'ZALX': '单一障碍',
            'ZYZAYS': 'pH(中度酸化, 25.0%)',
            'CYZAYS': '无',
            'SJDZADJ': '中度酸化',
            'SJDZAD': 0.25,
        }
        storage.save_diagnosis([diag_record])

        result = storage.get_diagnosis('test-001')
        assert result is not None
        assert result['ZALX'] == '单一障碍'
        # ZYZAYS/CYZAYS 是 TEXT 字符串，不再是 JSON list
        assert result['ZYZAYS'] == 'pH(中度酸化, 25.0%)'
        assert result['CYZAYS'] == '无'
        assert result['SJDZADJ'] == '中度酸化'
        assert result['SJDZAD'] == 0.25

def test_storage_is_ready():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        assert not storage.is_ready()

        storage.create_tables()
        assert not storage.is_ready()

        eval_record = {
            'parcel_id': 'test-001', 'region_code': 'HN', 'secondary_region_code': 'MNY',
            'SJD': 6.5, 'YJZ': 25, 'YXL': 30, 'SXJ': 150, 'TRRZ': 1.2,
            'GCZD': 'RT', 'GGNL': 'FS', 'PSNL': 'CM', 'DXBW': 'PLT', 'ZDGX': 'TLBC',
            'YXTCHD': 100, 'GCHD': 20,
            'SJDLSD': 1.0, 'YJZLSD': 1.0, 'YXLLSD': 0.8, 'SXJLSD': 0.8, 'TRRZLSD': 1.0,
            'GCZDLSD': 1.0, 'GGNLLSD': 1.0, 'PSNLLSD': 1.0, 'DXBWLSD': 1.0, 'ZDGXLSD': 1.0,
            'YXTCHDLSD': 1.0, 'GCHDLSD': 1.0,
            'ZHQZ': 0.85, 'GDZLDJ': '3',
        }
        storage.save_evaluation([eval_record])

        diag_record = {
            'parcel_id': 'test-001', 'ZALX': '无明显障碍',
            'ZYZAYS': '', 'CYZAYS': '无',
        }
        storage.save_diagnosis([diag_record])

        assert storage.is_ready()


# Evaluation tests
from src.ai_culti_demo.farmland_diagnosis.evaluation import bulk_evaluate, evaluate_single, calc_continuous, calc_discrete, translate_obstacle_level
import pandas as pd

def test_translate_obstacle_level_sjd_acidification():
    assert translate_obstacle_level('SJD', '中度障碍', 5.0) == '中度酸化'

def test_translate_obstacle_level_sjd_alkalization():
    assert translate_obstacle_level('SJD', '中度障碍', 8.8) == '中度碱化'

def test_translate_obstacle_level_trrz_compaction():
    assert translate_obstacle_level('TRRZ', '重度障碍', 1.5) == '重度板结'

def test_translate_obstacle_level_yjz_barren():
    assert translate_obstacle_level('YJZ', '重度障碍', 5.0) == '重度贫瘠'

def test_translate_obstacle_level_yxl_deficiency():
    assert translate_obstacle_level('YXL', '重度障碍', 5.0) == '重度缺乏'

def test_translate_obstacle_level_no_obstacle():
    assert translate_obstacle_level('SJD', '无障碍', 7.0) == '无障碍'

def test_evaluate_single():
    row = pd.Series({
        'YJNYQ': '华南区', 'EJNYQ': '闽南粤中农林水产区',
        'SJD': 6.5, 'YJZ': 25, 'YXL': 30, 'SXJ': 150, 'TRRZ': 1.2,
        'GCZD': 'RT', 'GGNL': 'FS', 'PSNL': 'CM', 'DXBW': 'PLT', 'ZDGX': 'TLBC',
        'YXTCHD': 100, 'GCHD': 20,
    })

    result = evaluate_single(row, 'HN', 'MNY')

    assert 'SJDLSD' in result
    assert 'ZHQZ' in result
    assert 'GDZLDJ' in result
    assert result['GDZLDJ'] == '1'
    # 原始值保留
    assert result['SJD'] == 6.5

def test_bulk_evaluate():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        # CSV 直接使用标准码表头（无中文列名）
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
华南区,闽南粤中农林水产区,6.5,25,30,150,1.2,壤土,充分满足,充分满足,平原低阶,上松下紧型,100,20
''')

        db_path = os.path.join(tmpdir, 'test.db')
        result = bulk_evaluate(csv_path, db_path)

        assert result['status'] == 'ok'
        assert result['processed'] == 1

        storage = DiagnosisStorage(db_path)
        eval_result = storage.get_evaluation('0')
        assert eval_result is not None
        assert eval_result['SJD'] == 6.5
        assert eval_result['GDZLDJ'] == '1'

def test_bulk_evaluate_missing_columns():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('SJD,YJZ\n6.5,25\n')

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
