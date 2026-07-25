"""测试审计日志写入。"""
import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.upload.audit_logger import log_data_import, set_log_path


def test_log_data_import_success():
    """成功导入审计条目字段完整性。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, 'data_import.log')
        set_log_path(log_path)

        log_data_import(
            username='admin',
            data_type='csv',
            filename='mydata.csv',
            deployed_path='/data/farmland_diagnosis/test.csv',
            trigger_result={'status': 'ok', 'processed': 100},
            success=True,
        )

        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry['username'] == 'admin'
        assert entry['data_type'] == 'csv'
        assert entry['filename'] == 'mydata.csv'
        assert entry['deployed_path'] == '/data/farmland_diagnosis/test.csv'
        assert entry['success'] is True
        assert entry['restored_from_backup'] is False
        assert 'timestamp' in entry
        assert 'trigger_result' in entry


def test_log_data_import_failure_with_rollback():
    """失败 + 回滚条目包含 restored_from_backup。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, 'data_import.log')
        set_log_path(log_path)

        log_data_import(
            username='admin',
            data_type='shapefile',
            filename='data.zip',
            deployed_path='/data/farmland_stability/',
            trigger_result={'status': 'error', 'error': {'message': '字段缺失'}},
            success=False,
            message='触发失败已回滚',
            restored_from_backup=True,
        )

        with open(log_path, 'r', encoding='utf-8') as f:
            entry = json.loads(f.readline())
        assert entry['success'] is False
        assert entry['restored_from_backup'] is True
        assert '回滚' in entry['message']


def test_log_data_import_appends_multiple():
    """多次调用追加写入（不覆盖）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, 'data_import.log')
        set_log_path(log_path)

        for i in range(3):
            log_data_import(
                username='admin', data_type='csv', filename=f'f{i}.csv',
                deployed_path='/p', trigger_result={}, success=True,
            )

        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) == 3
