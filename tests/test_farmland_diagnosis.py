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
    assert len(ALL_INDICATORS) == 14
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
        assert 'acidification_results' not in tables
        conn.close()


def test_legacy_acidification_storage_methods_are_unavailable_without_table_access():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        storage = DiagnosisStorage(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE acidification_results (parcel_id TEXT, expected_effect TEXT)")
        conn.execute("INSERT INTO acidification_results VALUES ('P-1', 'legacy text')")
        conn.commit()
        conn.close()

        saved = storage.save_acidification([{"parcel_id": "P-2", "expected_effect": "new text"}])
        loaded = storage.get_acidification("P-1")
        assert saved["status"] == "unavailable"
        assert loaded["status"] == "unavailable"
        assert "expected_effect" not in loaded

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT * FROM acidification_results").fetchall()
        conn.close()
        assert rows == [("P-1", "legacy text")]

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
from src.ai_culti_demo.farmland_diagnosis.diagnosis import diagnosis_row, diagnose, query_parcel, replace_abbr_in_text
from src.ai_culti_demo.farmland_diagnosis.config import WEIGHTED_INDICATORS

def test_replace_abbr_in_text():
    text = 'SJD(中度酸化, 25.0%)；SXJ(重度缺乏, 26.5%)'
    out = replace_abbr_in_text(text, {'SJD': 'pH', 'SXJ': '速效钾'})
    assert out == 'pH(中度酸化, 25.0%)；速效钾(重度缺乏, 26.5%)'

def test_replace_abbr_in_text_empty():
    assert replace_abbr_in_text('', {'SJD': 'pH'}) == ''

def test_diagnosis_row_single_obstacle():
    row = pd.Series({
        'SJDZADJ': '中度酸化', 'SJDZAD': 0.25,
        'YJZZADJ': '无障碍', 'YJZZAD': 0.05,
    })
    level_cols = [ind + 'ZADJ' for ind in WEIGHTED_INDICATORS]
    degree_cols = [ind + 'ZAD' for ind in WEIGHTED_INDICATORS]
    zalx, zyzays, cyzays = diagnosis_row(row, WEIGHTED_INDICATORS, level_cols, degree_cols)

    assert zalx == '单一障碍'
    assert isinstance(zyzays, str)
    assert isinstance(cyzays, str)
    assert 'pH' in zyzays  # 缩写已替换为中文
    assert cyzays == '无'

def test_diagnosis_row_multi_obstacle():
    row = pd.Series({
        'SJDZADJ': '中度酸化', 'SJDZAD': 0.25,
        'YJZZADJ': '中度贫瘠', 'YJZZAD': 0.20,
        'YXLZADJ': '轻度缺乏', 'YXLZAD': 0.15,
    })
    level_cols = [ind + 'ZADJ' for ind in WEIGHTED_INDICATORS]
    degree_cols = [ind + 'ZAD' for ind in WEIGHTED_INDICATORS]
    zalx, zyzays, cyzays = diagnosis_row(row, WEIGHTED_INDICATORS, level_cols, degree_cols)

    assert zalx == '多障碍'
    assert isinstance(zyzays, str)
    assert zyzays.count('；') >= 1  # 至少两个主要因素

def test_diagnosis_row_no_obstacle():
    row = pd.Series({
        'SJDZADJ': '无障碍', 'SJDZAD': 0.05,
        'YJZZADJ': '无障碍', 'YJZZAD': 0.03,
    })
    level_cols = [ind + 'ZADJ' for ind in WEIGHTED_INDICATORS]
    degree_cols = [ind + 'ZAD' for ind in WEIGHTED_INDICATORS]
    zalx, zyzays, cyzays = diagnosis_row(row, WEIGHTED_INDICATORS, level_cols, degree_cols)

    assert zalx == '无明显障碍'
    assert zyzays == ''
    assert cyzays == '无'  # V2.0 行为：空 CYZAYS 归一为 '无'

def test_diagnose_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
华南区,闽南粤中农林水产区,4.5,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')

        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)
        result = diagnose(db_path)

        assert result['status'] == 'ok'
        assert result['diagnosed'] == 1

        query_result = query_parcel('0', db_path)
        assert query_result['status'] == 'ok'
        assert 'diagnosis' in query_result
        diag = query_result['diagnosis']
        assert 'ZALX' in diag
        assert 'ZYZAYS' in diag
        assert 'CYZAYS' in diag


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
        # CSV 表头改标准码；用 CJ 一级区验证 region_code 正确分区（不再恒 HN）
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
长江中下游区,闽南粤中农林水产区,4.5,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')

        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)
        diagnose(db_path)  # 确保 is_ready 返回 True
        # evaluate_acidification 已废弃，改用 calculate_acidification_amendment 按需计算；
        # 调用仅返回 deprecated 状态，不再批量落库。
        result = evaluate_acidification(db_path)

        assert result['status'] == 'deprecated'

        # query_acidification 改为从 evaluation_results 取 SJD/JHX/JLA 调用新模型按需计算；
        # 本 CSV 缺 JHX/JLA 列，DB 中也缺，应返回 not_ready 或 missing_input。
        query_result = query_acidification('0', db_path)
        assert query_result['status'] in ('not_ready', 'missing_input')

def test_evaluate_acidification_uses_region_code():
    # 验证酸化评估按地块实际 region_code 分区，不恒回退 HN
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
长江中下游区,闽南粤中农林水产区,4.4,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')
        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)
        diagnose(db_path)
        # 酸化改为按需计算，不再批量落库；evaluate_acidification 仅返回 deprecated。
        result = evaluate_acidification(db_path)
        assert result['status'] == 'deprecated'

        # region_code 分区仍由 bulk_evaluate 正确处理，直接查 evaluation_results 确认 CJ。
        storage = DiagnosisStorage(db_path)
        eval_row = storage.get_evaluation('0')
        assert eval_row['region_code'] == 'CJ'


# Task 8: 跨模块/边界测试
def test_obstacle_degree_does_not_overwrite_original():
    # 障碍度存独立 xxxZAD 列，原始指标值 SJD/YJZ 等保持不变
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
华南区,闽南粤中农林水产区,4.5,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')
        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)

        storage = DiagnosisStorage(db_path)
        result = storage.get_evaluation('0')

        # 原始值未被覆盖
        assert result['SJD'] == 4.5
        assert result['YJZ'] == 10
        # 障碍度独立列存在
        assert 'SJDZAD' in result and result['SJDZAD'] is not None
        assert 'YJZZAD' in result and result['YJZZAD'] is not None
        # 障碍度列与原始值不同（原始值是测量值，障碍度是 0~1 占比）
        assert result['SJDZAD'] != result['SJD']


def test_diagnosis_row_returns_string_triple():
    row = pd.Series({
        'SJDZADJ': '重度酸化', 'SJDZAD': 0.30,
        'SXJZADJ': '重度缺乏', 'SXJZAD': 0.25,
    })
    level_cols = [ind + 'ZADJ' for ind in WEIGHTED_INDICATORS]
    degree_cols = [ind + 'ZAD' for ind in WEIGHTED_INDICATORS]
    result = diagnosis_row(row, WEIGHTED_INDICATORS, level_cols, degree_cols)

    assert isinstance(result, tuple) and len(result) == 3
    zalx, zyzays, cyzays = result
    assert isinstance(zalx, str)
    assert isinstance(zyzays, str)
    assert isinstance(cyzays, str)
    # 缩写已替换为中文显示名
    assert 'pH' in zyzays
    assert '速效钾' in zyzays
    assert 'SJD' not in zyzays
    assert 'SXJ' not in zyzays


def test_end_to_end_zalx_zyzays_cyzays():
    # 端到端：bulk_evaluate → diagnose → query_parcel 返回 ZALX/ZYZAYS/CYZAYS
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, 'test.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
华南区,闽南粤中农林水产区,4.5,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')
        db_path = os.path.join(tmpdir, 'test.db')
        bulk_evaluate(csv_path, db_path)
        diagnose(db_path)

        result = query_parcel('0', db_path)
        assert result['status'] == 'ok'
        diag = result['diagnosis']
        eval_data = result['evaluation']

        # 诊断三字段均为字符串
        assert isinstance(diag['ZALX'], str)
        assert isinstance(diag['ZYZAYS'], str)
        assert isinstance(diag['CYZAYS'], str)
        # 评价返回标准字段
        assert 'GDZLDJ' in eval_data
        assert 'ZHQZ' in eval_data
        # 障碍地块应有非空 ZALX
        assert diag['ZALX'] in ('单一障碍', '多障碍', '无明显障碍')
        # CYZAYS 空时归一为 '无'
        assert diag['CYZAYS'] == '无' or diag['CYZAYS'] != ''
