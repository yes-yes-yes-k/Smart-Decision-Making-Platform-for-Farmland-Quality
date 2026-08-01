"""测试数据导入 API 路由：POST /api/v1/data/import

用 monkeypatch mock validator/deployer/trigger/audit_logger，
测试认证、请求解析、大小校验、校验失败、触发失败回滚等场景。
"""
import sys
import os
import io
import shutil
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.api.app import create_app
from framework.models.user import db, User
from framework.config import Config, SQLiteConfig
from werkzeug.security import generate_password_hash


@pytest.fixture
def client(monkeypatch):
    """创建测试客户端：SQLite 临时 DB + admin/user 用户。"""
    tmp_db_dir = tempfile.mkdtemp(prefix="test_data_import_")
    tmp_db_path = os.path.join(tmp_db_dir, "test.db")

    original_db_uri = SQLiteConfig.SQLALCHEMY_DATABASE_URI
    SQLiteConfig.SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmp_db_path}'

    app = create_app('sqlite')
    app.config['TESTING'] = True

    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            nickname='管理员',
            role='admin',
            status=1,
        )
        normal = User(
            username='user1',
            password=generate_password_hash('user1234'),
            nickname='普通用户',
            role='user',
            status=1,
        )
        db.session.add(admin)
        db.session.add(normal)
        db.session.commit()

    client = app.test_client()
    client._app = app

    yield client

    SQLiteConfig.SQLALCHEMY_DATABASE_URI = original_db_uri
    shutil.rmtree(tmp_db_dir, ignore_errors=True)


@pytest.fixture
def success_mocks(monkeypatch):
    """默认 mock 所有 upload 函数为成功路径，返回调用记录。"""
    from framework.api.routes import data_import as di

    calls = {'log': [], 'backup': [], 'restore': [], 'cleanup': []}

    monkeypatch.setattr(di, 'validate_csv', lambda p: (True, ''))
    monkeypatch.setattr(di, 'validate_shapefile_zip', lambda p: (True, '', {'current_year': 2024}))
    monkeypatch.setattr(di, 'validate_dat', lambda p: (True, ''))

    def fake_backup(d):
        calls['backup'].append(d)
        return '/fake/backup/path'
    monkeypatch.setattr(di, 'backup_existing', fake_backup)
    monkeypatch.setattr(di, 'deploy_csv', lambda s, d: os.path.join(d, 'test.csv'))
    monkeypatch.setattr(di, 'deploy_shapefile', lambda z, d, m: ['a.shp'])
    monkeypatch.setattr(di, 'deploy_dat', lambda s, d: os.path.join(d, 'Farmland_quality_Level_Database.csv'))

    def fake_cleanup(d, keep=None):
        calls['cleanup'].append(d)
    monkeypatch.setattr(di, 'cleanup_backups', fake_cleanup)

    def fake_restore(d):
        calls['restore'].append(d)
        return True
    monkeypatch.setattr(di, 'restore_from_backup', fake_restore)

    monkeypatch.setattr(di, 'trigger_csv_evaluate', lambda p, timeout=None: {'status': 'ok', 'processed': 10})
    monkeypatch.setattr(di, 'trigger_shapefile_precompute', lambda d, m, timeout=None: {'status': 'ok', 'processed': 5, 'saved_to_db': True})
    monkeypatch.setattr(di, 'trigger_dat_check', lambda d, timeout=None: {'deployment_ok': True, 'detail': {}})

    def fake_log(*args, **kwargs):
        calls['log'].append({'args': args, 'kwargs': kwargs})
    monkeypatch.setattr(di, 'log_data_import', fake_log)

    return calls


def _login(client, username, password):
    """登录获取 JWT token。"""
    resp = client.post('/api/v1/auth/login', json={
        'username': username,
        'password': password,
    })
    assert resp.status_code == 200, f"登录失败: {resp.get_json()}"
    return resp.get_json()['data']['token']


def _do_import(client, token, data_type='csv', content=b'fake,data\n1,2\n', filename='test.csv'):
    """发送数据导入请求。"""
    return client.post(
        '/api/v1/data/import',
        headers={'Authorization': f'Bearer {token}'},
        data={'data_type': data_type, 'file': (io.BytesIO(content), filename)},
        content_type='multipart/form-data',
    )


def test_import_csv_success(client, success_mocks):
    """admin 成功上传 CSV → 200 + 审计日志。"""
    token = _login(client, 'admin', 'admin123')
    resp = _do_import(client, token, data_type='csv', filename='my.csv')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['data_type'] == 'csv'
    assert 'test.csv' in data['deployed_path']
    assert data['trigger_result']['status'] == 'ok'
    # 审计日志记录了成功
    assert len(success_mocks['log']) == 1
    log_entry = success_mocks['log'][0]
    assert log_entry['args'][5] is True  # success=True
    # cleanup 被调用（成功路径）
    assert len(success_mocks['cleanup']) == 1


def test_import_shapefile_success(client, success_mocks):
    """admin 成功上传 shapefile zip → 200。"""
    token = _login(client, 'admin', 'admin123')
    resp = _do_import(client, token, data_type='shapefile', content=b'PK\x03\x04fakezip', filename='shp.zip')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['data_type'] == 'shapefile'
    assert data['trigger_result']['saved_to_db'] is True


def test_import_dat_success(client, success_mocks):
    """admin 成功上传 .dat → 200。"""
    token = _login(client, 'admin', 'admin123')
    resp = _do_import(client, token, data_type='dat', content=b'\x00\x01\x02\x03', filename='data.dat')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['data_type'] == 'dat'
    assert data['trigger_result']['deployment_ok'] is True


def test_import_non_admin_returns_403(client, success_mocks):
    """非 admin 用户 → 403。"""
    token = _login(client, 'user1', 'user1234')
    resp = _do_import(client, token)
    assert resp.status_code == 403
    assert '权限' in resp.get_json()['message']


def test_import_no_jwt_returns_401(client, success_mocks):
    """无 JWT → 401。"""
    resp = client.post(
        '/api/v1/data/import',
        data={'data_type': 'csv', 'file': (io.BytesIO(b'data'), 't.csv')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 401


def test_import_missing_data_type_returns_400(client, success_mocks):
    """缺 data_type → 400。"""
    token = _login(client, 'admin', 'admin123')
    resp = client.post(
        '/api/v1/data/import',
        headers={'Authorization': f'Bearer {token}'},
        data={'file': (io.BytesIO(b'data'), 't.csv')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 400
    assert 'data_type' in resp.get_json()['message']


def test_import_missing_file_returns_400(client, success_mocks):
    """缺 file → 400。"""
    token = _login(client, 'admin', 'admin123')
    resp = client.post(
        '/api/v1/data/import',
        headers={'Authorization': f'Bearer {token}'},
        data={'data_type': 'csv'},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 400
    assert 'file' in resp.get_json()['message']


def test_import_file_too_large_returns_413(client, success_mocks, monkeypatch):
    """文件超限 → 413。"""
    monkeypatch.setattr(Config, 'MAX_DATA_IMPORT_SIZE', 10)
    token = _login(client, 'admin', 'admin123')
    resp = _do_import(client, token, content=b'x' * 200, filename='big.csv')
    assert resp.status_code == 413


def test_import_validation_failed_returns_400(client, success_mocks, monkeypatch):
    """校验失败 → 400 + 审计日志记录失败。"""
    from framework.api.routes import data_import as di
    monkeypatch.setattr(di, 'validate_csv', lambda p: (False, 'CSV 缺少必需列: [pH]'))
    token = _login(client, 'admin', 'admin123')
    resp = _do_import(client, token)
    assert resp.status_code == 400
    assert 'pH' in resp.get_json()['message']
    # 审计日志记录了校验失败
    assert len(success_mocks['log']) == 1
    assert success_mocks['log'][0]['args'][5] is False  # success=False


def test_import_trigger_exception_rolls_back_500(client, success_mocks, monkeypatch):
    """触发器抛异常 → 500 + 回滚 + 审计。"""
    from framework.api.routes import data_import as di
    monkeypatch.setattr(di, 'trigger_csv_evaluate', lambda p, timeout=None: (_ for _ in ()).throw(RuntimeError('model crashed')))
    token = _login(client, 'admin', 'admin123')
    resp = _do_import(client, token)
    assert resp.status_code == 500
    assert 'model crashed' in resp.get_json()['message']
    # 回滚被调用
    assert len(success_mocks['restore']) == 1
    # 审计记录了失败 + 回滚
    log_entry = success_mocks['log'][0]
    assert log_entry['args'][5] is False  # success=False
    assert log_entry['kwargs'].get('restored_from_backup') is True


def test_import_trigger_timeout_rolls_back_504(client, success_mocks, monkeypatch):
    """触发器超时 → 504 + 回滚。"""
    from framework.api.routes import data_import as di

    def raise_timeout(p, timeout=None):
        raise TimeoutError('执行超时')
    monkeypatch.setattr(di, 'trigger_csv_evaluate', raise_timeout)
    token = _login(client, 'admin', 'admin123')
    resp = _do_import(client, token)
    assert resp.status_code == 504
    assert len(success_mocks['restore']) == 1


def test_import_trigger_error_dict_rolls_back_500(client, success_mocks, monkeypatch):
    """触发器返回错误字典 → 500 + 回滚。"""
    from framework.api.routes import data_import as di
    monkeypatch.setattr(di, 'trigger_csv_evaluate', lambda p, timeout=None: {'status': 'error', 'error': {'code': 'BULK_EVALUATE_ERROR', 'message': '字段缺失'}})
    token = _login(client, 'admin', 'admin123')
    resp = _do_import(client, token)
    assert resp.status_code == 500
    assert len(success_mocks['restore']) == 1
    # 审计记录了触发返回错误
    log_entry = success_mocks['log'][0]
    assert log_entry['args'][5] is False
