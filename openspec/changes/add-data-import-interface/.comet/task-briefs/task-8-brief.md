# Task 8 Brief: API 路由（POST /api/v1/data/import）

> 本文件是 Task 8 的唯一需求来源，包含精确待写代码。请先完整阅读本文件。

## 对应 tasks.md

第 6 节（6.1-6.12）

## 前置依赖（全部已完成）

- ✅ `framework/config.py`：`MAX_DATA_IMPORT_SIZE`、`DATA_IMPORT_TIMEOUT`、`DATA_IMPORT_TARGETS`、`BACKUP_RETENTION_COUNT`
- ✅ `framework/upload/data_validator.py`：`validate_csv`、`validate_shapefile_zip`、`validate_dat`
- ✅ `framework/upload/data_deployer.py`：`backup_existing`、`deploy_csv`、`deploy_shapefile`、`deploy_dat`、`cleanup_backups`、`restore_from_backup`
- ✅ `framework/upload/data_trigger.py`：`trigger_csv_evaluate`、`trigger_shapefile_precompute`、`trigger_dat_check`
- ✅ `framework/upload/audit_logger.py`：`log_data_import`
- ✅ `framework/auth/decorators.py`：`admin_required`（组合 `@jwt_required()` + admin 角色校验，非 admin 返回 403）

## Files（允许修改）

- Create: `framework/api/routes/data_import.py`
- Create: `tests/test_data_import_route.py`
- Modify: `framework/api/app.py`（注册 Blueprint，2 行）
- Modify: `framework/config.py`（`MAX_CONTENT_LENGTH` 从 50MB 提升到 200MB，1 行）

## 关键设计决策

1. **认证**：用 `@admin_required` 装饰器（已存在），非 admin 返回 403，无 JWT 返回 401（由内部 `@jwt_required()` 处理）。
2. **请求解析**：`request.form.get('data_type')` + `request.files.get('file')`，multipart/form-data。
3. **大小校验**：先查 `request.content_length`（早拒），保存临时文件后再查 `os.path.getsize`（防 spoof）。超限返回 413。
4. **MAX_CONTENT_LENGTH 提升**：Flask 在 WSGI 层用 `MAX_CONTENT_LENGTH`（当前 50MB）拦截大请求，必须在路由运行前就提升到 200MB，否则 200MB 数据导入请求永远到不了路由。
5. **编排流程**：校验 → `backup_existing` → `deploy_*` → `trigger_*` → 成功则 `cleanup_backups` + 审计 → 200；触发失败则 `restore_from_backup` + 审计 → 504/500。
6. **触发失败判定**：
   - `TimeoutError` 异常 → 504 + 回滚
   - 其他异常 → 500 + 回滚
   - 返回错误字典（CSV/shapefile: `status=='error'`；dat: `deployment_ok==False`）→ 500 + 回滚
7. **审计日志**：所有路径（成功/校验失败/触发失败）都写审计条目；`log_data_import` 在测试中 mock。
8. **临时文件**：`tempfile.NamedTemporaryFile(delete=False)` → `close()` → `file.save()` → `finally: os.unlink()`。Windows 上必须先 close 再 save。
9. **manifest 作用域**：`validate_shapefile_zip` 返回 3-tuple `(ok, err, manifest)`，其他返回 2-tuple。在 if/elif/else 前 `manifest = {}` 预初始化。
10. **响应格式**：遵循现有约定 `{"status": "ok", "data": {...}}` / `{"status": "error", "message": ...}`。

## Step 1: 编写 tests/test_data_import_route.py 的失败测试

创建 `tests/test_data_import_route.py`：

```python
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
    monkeypatch.setattr(di, 'deploy_dat', lambda s, d: os.path.join(d, 'Farmlands_Quality_Level_Database.dat'))

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
```

## Step 2: 运行测试验证失败

```bash
d:\miniconda3\python.exe -m pytest tests/test_data_import_route.py -v
```

预期：FAIL，报 `ModuleNotFoundError: No module named 'framework.api.routes.data_import'` 或 `ImportError`

## Step 3: 实现路由 + 注册 Blueprint + 提升 MAX_CONTENT_LENGTH

### 3a. 创建 `framework/api/routes/data_import.py`

```python
"""数据导入 API 路由：POST /api/v1/data/import

编排校验 → 部署 → 触发 → 审计日志的完整流程，支持 CSV / shapefile / .dat 三类数据。
仅 admin 角色可调用。触发失败时自动从备份回滚。
"""
import os
import tempfile

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity

from framework.config import Config
from framework.models.user import User
from framework.auth.decorators import admin_required
from framework.upload.data_validator import (
    validate_csv,
    validate_shapefile_zip,
    validate_dat,
)
from framework.upload.data_deployer import (
    backup_existing,
    deploy_csv,
    deploy_shapefile,
    deploy_dat,
    cleanup_backups,
    restore_from_backup,
)
from framework.upload.data_trigger import (
    trigger_csv_evaluate,
    trigger_shapefile_precompute,
    trigger_dat_check,
)
from framework.upload.audit_logger import log_data_import

data_import_bp = Blueprint('data_import', __name__)

_VALID_TYPES = ('csv', 'shapefile', 'dat')


@data_import_bp.route('/import', methods=['POST'])
@admin_required
def import_data():
    """数据导入端点：上传 → 校验 → 部署 → 触发 → 审计。"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    username = user.username if user else 'unknown'

    # 1. 解析请求
    data_type = request.form.get('data_type')
    if not data_type:
        return jsonify({"status": "error", "message": "缺少 data_type 字段"}), 400
    if data_type not in _VALID_TYPES:
        return jsonify({"status": "error", "message": f"不支持的 data_type: {data_type}"}), 400

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "缺少 file 字段"}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({"status": "error", "message": "未选择文件"}), 400

    # 2. 大小校验（Content-Length 头，早拒）
    max_size = Config.MAX_DATA_IMPORT_SIZE
    if request.content_length is not None and request.content_length > max_size:
        return jsonify({"status": "error", "message": f"文件大小超过 {max_size // (1024 * 1024)}MB 限制"}), 413

    # 3. 保存到临时文件
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp_path = tmp.name
    tmp.close()  # Windows 上必须先 close 再让 file.save 写入
    try:
        file.save(tmp_path)

        # 实际大小校验（防 Content-Length spoof）
        actual_size = os.path.getsize(tmp_path)
        if actual_size > max_size:
            return jsonify({"status": "error", "message": f"文件大小超过 {max_size // (1024 * 1024)}MB 限制"}), 413

        # 4. 校验
        manifest = {}
        if data_type == 'csv':
            ok, err = validate_csv(tmp_path)
        elif data_type == 'shapefile':
            ok, err, manifest = validate_shapefile_zip(tmp_path)
        else:
            ok, err = validate_dat(tmp_path)

        if not ok:
            log_data_import(username, data_type, file.filename, '', {}, False, f"校验失败: {err}")
            return jsonify({"status": "error", "message": err}), 400

        # 5. 部署 + 触发
        target_dir = Config.DATA_IMPORT_TARGETS[data_type]
        backup_path = backup_existing(target_dir)

        try:
            if data_type == 'csv':
                deployed_path = deploy_csv(tmp_path, target_dir)
                trigger_result = trigger_csv_evaluate(deployed_path)
            elif data_type == 'shapefile':
                deploy_shapefile(tmp_path, target_dir, manifest)
                deployed_path = target_dir
                trigger_result = trigger_shapefile_precompute(target_dir, manifest)
            else:
                deployed_path = deploy_dat(tmp_path, target_dir)
                trigger_result = trigger_dat_check(target_dir)
        except TimeoutError as e:
            restored = restore_from_backup(target_dir)
            log_data_import(
                username, data_type, file.filename, '', {}, False,
                f"触发超时: {e}", restored_from_backup=restored,
            )
            return jsonify({"status": "error", "message": f"触发超时: {e}"}), 504
        except Exception as e:
            restored = restore_from_backup(target_dir)
            log_data_import(
                username, data_type, file.filename, '', {}, False,
                f"触发异常: {e}", restored_from_backup=restored,
            )
            return jsonify({"status": "error", "message": f"触发失败: {e}"}), 500

        # 6. 检查触发结果是否为错误字典
        if data_type == 'dat':
            trigger_failed = not trigger_result.get('deployment_ok', False)
        else:
            trigger_failed = trigger_result.get('status') == 'error'

        if trigger_failed:
            restored = restore_from_backup(target_dir)
            log_data_import(
                username, data_type, file.filename, '', trigger_result, False,
                "触发返回错误", restored_from_backup=restored,
            )
            return jsonify({
                "status": "error",
                "message": "触发失败",
                "trigger_result": trigger_result,
            }), 500

        # 7. 成功：清理旧备份 + 审计
        cleanup_backups(target_dir)
        log_data_import(username, data_type, file.filename, deployed_path, trigger_result, True)

        return jsonify({
            "status": "ok",
            "data": {
                "data_type": data_type,
                "deployed_path": deployed_path,
                "backup_path": backup_path,
                "trigger_result": trigger_result,
            }
        })
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
```

### 3b. 修改 `framework/api/app.py`（注册 Blueprint）

在 import 区（第 10 行 `from framework.api.routes.county import county_bp` 之后）添加：
```python
from framework.api.routes.data_import import data_import_bp
```

在 `app.register_blueprint(report_bp, url_prefix='/api/v1/report')` 之后（第 26 行后）添加：
```python
    app.register_blueprint(data_import_bp, url_prefix='/api/v1/data')
```

### 3c. 修改 `framework/config.py`（提升 MAX_CONTENT_LENGTH）

将第 43 行：
```python
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
```
改为：
```python
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200MB，对齐 MAX_DATA_IMPORT_SIZE，允许数据导入大文件
```

## Step 4: 运行测试验证通过

```bash
d:\miniconda3\python.exe -m pytest tests/test_data_import_route.py -v
```

预期：全部 PASS（12 个测试）

若现有 `tests/test_docs_dedup.py` 等其他测试因 `MAX_CONTENT_LENGTH` 提升而行为变化（理论上不会，因为提升上限只会放行更多请求），运行确认：
```bash
d:\miniconda3\python.exe -m pytest tests/test_data_import_route.py tests/test_docs_dedup.py -v
```

## Step 5: 提交

```bash
git add framework/api/routes/data_import.py tests/test_data_import_route.py framework/api/app.py framework/config.py
git commit -m "feat: add POST /api/v1/data/import route with validation, deploy, trigger and rollback"
```

## 全局约束（binds this task）

- 认证：`@admin_required`（非 admin → 403，无 JWT → 401）
- 请求格式：multipart/form-data，`data_type` 字段 + `file` 字段
- 大小校验：Content-Length 头 + 实际文件大小，超限 → 413
- 校验失败 → 400 + 审计日志（success=False）
- 触发超时 → 504 + 回滚 + 审计
- 触发异常 → 500 + 回滚 + 审计
- 触发返回错误字典 → 500 + 回滚 + 审计
- 成功 → cleanup_backups + 审计（success=True）+ 200
- 临时文件 finally 清理
- 不修改 validator/deployer/trigger/audit_logger/adapters/decorators 等已存在模块
- `MAX_CONTENT_LENGTH` 提升到 200MB 是必要变更（否则 200MB 请求被 Flask WSGI 层拦截）

## 环境提示

- 用 `d:\miniconda3\python.exe -m pytest` 运行测试
- 测试用 `create_app('sqlite')` + SQLite 临时 DB
- 测试用 monkeypatch mock `framework.api.routes.data_import` 模块的函数引用
- `success_mocks` fixture 提供默认成功 mock，个别测试用 `monkeypatch.setattr(di, ...)` 覆盖
- Windows 上 `NamedTemporaryFile` 必须先 `close()` 再 `file.save()`

## 风险信号自报项（回报时逐条回答）

1. 是否偏离 brief 代码？
2. 是否跳过 RED？
3. 测试是否全部 PASS？数量？
4. 是否只修改允许文件（data_import.py + test_data_import_route.py + app.py + config.py）？
5. 是否提交了不该提交的文件？
6. 是否引入非预期依赖？
7. 是否满足全局约束（11 条）？
8. 自检项：1 路由函数 + 12 测试 + app.py 注册 + config.py MAX_CONTENT_LENGTH？
9. 是否运行了 test_docs_dedup.py 确认无回归？
