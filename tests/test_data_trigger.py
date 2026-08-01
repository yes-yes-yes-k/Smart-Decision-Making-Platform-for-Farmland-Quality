"""测试数据导入触发器：用 monkeypatch 模拟 adapter 调用。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.upload import data_trigger


@pytest.fixture
def fake_adapter(monkeypatch):
    """用 monkeypatch 替换 core_engine 的三个方法，并记录调用参数。"""
    calls = {
        'bulk_evaluate_csv': [],
        'precompute_stability': [],
        'check_grade_eval_deployment': [],
    }

    def fake_bulk(csv_path):
        calls['bulk_evaluate_csv'].append(csv_path)
        return {'status': 'ok', 'processed': 100, 'errors': []}

    def fake_precompute(shapefile_dir, manifest):
        calls['precompute_stability'].append((shapefile_dir, manifest))
        return {'status': 'ok', 'processed': 50, 'saved_to_db': True, 'output_files': ['/o/s.shp']}

    def fake_check():
        calls['check_grade_eval_deployment'].append(None)
        return {'deployment_ok': True, 'detail': {'ready': True}}

    monkeypatch.setattr(data_trigger.core_engine, 'bulk_evaluate_csv', fake_bulk)
    monkeypatch.setattr(data_trigger.core_engine, 'precompute_stability', fake_precompute)
    monkeypatch.setattr(data_trigger.core_engine, 'check_grade_eval_deployment', fake_check)
    return calls


def test_trigger_csv_evaluate_success(fake_adapter):
    """CSV 触发成功：透传 adapter 返回，参数正确传递。"""
    result = data_trigger.trigger_csv_evaluate('/tmp/test.csv')
    assert result['status'] == 'ok'
    assert result['processed'] == 100
    assert fake_adapter['bulk_evaluate_csv'] == ['/tmp/test.csv']


def test_trigger_csv_evaluate_returns_error_dict(monkeypatch):
    """adapter 返回错误字典时，trigger 原样透传。"""
    monkeypatch.setattr(
        data_trigger.core_engine, 'bulk_evaluate_csv',
        lambda p: {'status': 'error', 'error': {'code': 'BULK_EVALUATE_ERROR', 'message': '字段缺失'}},
    )
    result = data_trigger.trigger_csv_evaluate('/tmp/bad.csv')
    assert result['status'] == 'error'
    assert result['error']['code'] == 'BULK_EVALUATE_ERROR'
    assert '字段缺失' in result['error']['message']


def test_trigger_csv_evaluate_propagates_exception(monkeypatch):
    """adapter 抛异常时，异常向上冒泡（由 API 路由层捕获）。"""
    def raise_error(csv_path):
        raise RuntimeError('connection lost')
    monkeypatch.setattr(data_trigger.core_engine, 'bulk_evaluate_csv', raise_error)
    with pytest.raises(RuntimeError, match='connection lost'):
        data_trigger.trigger_csv_evaluate('/tmp/x.csv')


def test_trigger_shapefile_precompute_success(fake_adapter):
    """shapefile 触发成功：参数（target_dir, manifest）正确传递。"""
    manifest = {'current_year': 2024, 'history_years': [2020, 2021]}
    result = data_trigger.trigger_shapefile_precompute('/tmp/shp', manifest)
    assert result['status'] == 'ok'
    assert result['saved_to_db'] is True
    assert fake_adapter['precompute_stability'] == [('/tmp/shp', manifest)]


def test_trigger_dat_check_success(fake_adapter):
    """dat 触发成功：调用无参 adapter 方法，target_dir 不传入。"""
    result = data_trigger.trigger_dat_check('/bin/farmland_quality_eval')
    assert result['deployment_ok'] is True
    # 验证 adapter 被调用一次（无参数）
    assert len(fake_adapter['check_grade_eval_deployment']) == 1


def test_trigger_grade_csv_check_success(fake_adapter):
    """grade_csv 触发成功：新函数名与旧别名行为一致。"""
    result = data_trigger.trigger_grade_csv_check('/bin/farmland_quality_eval')
    assert result['deployment_ok'] is True
    assert len(fake_adapter['check_grade_eval_deployment']) == 1


def test_trigger_timeout_raises_timeout_error(monkeypatch):
    """超时抛内置 TimeoutError。"""
    import time

    def slow_call(csv_path):
        time.sleep(10)
        return {'status': 'ok'}

    monkeypatch.setattr(data_trigger.core_engine, 'bulk_evaluate_csv', slow_call)
    with pytest.raises(TimeoutError):
        data_trigger.trigger_csv_evaluate('/tmp/slow.csv', timeout=0.1)


def test_trigger_default_timeout_uses_config(monkeypatch):
    """timeout=None 时使用 Config.DATA_IMPORT_TIMEOUT。"""
    captured = {}

    def fake_bulk(csv_path):
        # 由于无法真正等待 600s，这里通过捕获 future.result 的 timeout 间接验证
        return {'status': 'ok'}

    # 用 monkeypatch 替换 ThreadPoolExecutor 以捕获 timeout 参数
    import concurrent.futures

    class FakeFuture:
        def __init__(self, result_value):
            self._result = result_value

        def result(self, timeout=None):
            captured['timeout'] = timeout
            return self._result

    class FakeExecutor:
        def __init__(self, max_workers=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, func, *args):
            return FakeFuture(func(*args))

    monkeypatch.setattr(data_trigger, 'core_engine', type('FakeCE', (), {
        'bulk_evaluate_csv': staticmethod(fake_bulk),
    })())
    monkeypatch.setattr(data_trigger.concurrent_futures, 'ThreadPoolExecutor', FakeExecutor)

    from framework.config import Config
    data_trigger.trigger_csv_evaluate('/tmp/x.csv')
    assert captured['timeout'] == Config.DATA_IMPORT_TIMEOUT
