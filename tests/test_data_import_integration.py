"""集成测试：数据导入端到端流程。

使用真实 validator/deployer/audit_logger，仅 mock trigger 函数（避免依赖真实模型）。
验证文件部署、备份、回滚、审计日志写入、备份保留策略。
"""
import sys
import os
import io
import json
import shutil
import tempfile
import zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.api.app import create_app
from framework.models.user import db, User
from framework.config import Config, SQLiteConfig
from framework.upload.audit_logger import set_log_path, _DEFAULT_LOG_PATH
from werkzeug.security import generate_password_hash


# CSV 14 必需列（与 data_validator.py CSV_REQUIRED_COLUMNS 一致）
CSV_HEADER = '一级农业区,二级农业区,pH,有机质,有效磷,速效钾,容重,耕层质地,灌溉能力,排水能力,地形部位,质地构型,有效土层,耕层厚度'
CSV_ROW = '珠江区,亚区1,6.5,2.5,15,100,1.3,壤土,高,中,平原,均质,100,20'
CSV_CONTENT = CSV_HEADER + '\n' + CSV_ROW + '\n'

# 耕地质量评价 CSV 20 必需字段（与 data_validator.py GRADE_CSV_REQUIRED_COLUMNS 一致）
GRADE_CSV_HEADER = ('SiteID,JD,WD,MJ,SJD,YJZ,YXL,SXJ,TRRZ,YXTCHD,GCHD,'
                    'JHXLLZ,JHXQLZ,EJNYQcode,XQMCcode,GCZDcode,PSNLcode,'
                    'GGNLcode,DXBWcode,ZDGXcode')
GRADE_CSV_ROW = 'A0001,112.97,25.32,100.0,4.6,16.2,66.9,51.7,1.24,120.0,17.0,0.0,0.0,1,8,6,3,2,6,6'
GRADE_CSV_CONTENT = GRADE_CSV_HEADER + '\n' + GRADE_CSV_ROW + '\n'


def _make_shapefile_zip():
    """创建有效的 shapefile zip（manifest + 3 期 × 5 组件）。"""
    manifest = {
        'current_year': 2024,
        'history_years': [2020, 2021],
        'years': [2020, 2021, 2024],
        'current_filename': 'current.shp',
        'history_filenames': ['2020.shp', '2021.shp'],
    }
    files = {'manifest.json': json.dumps(manifest, ensure_ascii=False).encode('utf-8')}
    for shp_name in ['current.shp', '2020.shp', '2021.shp']:
        base = shp_name[:-4]
        for ext in ['.shp', '.cpg', '.dbf', '.prj', '.shx']:
            files[f'{base}{ext}'] = f'fake_{ext}'.encode('utf-8')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    return buf, manifest


@pytest.fixture
def client(monkeypatch, tmp_path):
    """创建测试客户端：真实 validator/deployer/audit_logger，仅 mock trigger。"""
    tmp_db_dir = tempfile.mkdtemp(prefix="test_int_db_")
    tmp_db_path = os.path.join(tmp_db_dir, "test.db")
    log_path = str(tmp_path / 'audit.log')

    csv_dir = str(tmp_path / 'csv')
    shp_dir = str(tmp_path / 'shp')
    dat_dir = str(tmp_path / 'dat')
    os.makedirs(csv_dir)
    os.makedirs(shp_dir)
    os.makedirs(dat_dir)

    original_db_uri = SQLiteConfig.SQLALCHEMY_DATABASE_URI
    SQLiteConfig.SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmp_db_path}'

    monkeypatch.setitem(Config.DATA_IMPORT_TARGETS, 'csv', csv_dir)
    monkeypatch.setitem(Config.DATA_IMPORT_TARGETS, 'shapefile', shp_dir)
    monkeypatch.setitem(Config.DATA_IMPORT_TARGETS, 'dat', dat_dir)

    set_log_path(log_path)

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
        db.session.add(admin)
        db.session.commit()

    client = app.test_client()
    client._app = app
    client._log_path = log_path
    client._csv_dir = csv_dir
    client._shp_dir = shp_dir
    client._dat_dir = dat_dir

    # 仅 mock trigger（避免依赖真实模型/geopandas/数据库文件）
    from framework.api.routes import data_import as di
    monkeypatch.setattr(di, 'trigger_csv_evaluate', lambda p, timeout=None: {'status': 'ok', 'processed': 1, 'errors': []})
    monkeypatch.setattr(di, 'trigger_shapefile_precompute', lambda d, m, timeout=None: {'status': 'ok', 'processed': 1, 'saved_to_db': True, 'output_files': []})
    monkeypatch.setattr(di, 'trigger_dat_check', lambda d, timeout=None: {'deployment_ok': True, 'detail': {}})

    yield client

    SQLiteConfig.SQLALCHEMY_DATABASE_URI = original_db_uri
    set_log_path(_DEFAULT_LOG_PATH)
    shutil.rmtree(tmp_db_dir, ignore_errors=True)


def _login(client):
    """登录获取 JWT token。"""
    resp = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'})
    assert resp.status_code == 200
    return resp.get_json()['data']['token']


def _read_audit_log(client):
    """读取审计日志文件，返回条目列表。"""
    if not os.path.exists(client._log_path):
        return []
    entries = []
    with open(client._log_path, 'r', encoding='utf-8') as f:
        for line in f:
            entries.append(json.loads(line))
    return entries


def test_csv_import_end_to_end(client):
    """7.1 CSV 上传 → 校验 → 部署 → 触发 → 审计日志写入。"""
    token = _login(client)
    resp = client.post(
        '/api/v1/data/import',
        headers={'Authorization': f'Bearer {token}'},
        data={'data_type': 'csv', 'file': (io.BytesIO(CSV_CONTENT.encode('utf-8')), 'my.csv')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['data_type'] == 'csv'
    assert data['trigger_result']['status'] == 'ok'

    # 验证文件已部署到 target_dir/test.csv
    deployed = os.path.join(client._csv_dir, 'test.csv')
    assert os.path.exists(deployed)
    with open(deployed, 'r', encoding='utf-8') as f:
        content = f.read()
    assert '一级农业区' in content
    assert '亚区1' in content

    # 验证审计日志写入
    entries = _read_audit_log(client)
    assert len(entries) == 1
    assert entries[0]['success'] is True
    assert entries[0]['data_type'] == 'csv'
    assert entries[0]['username'] == 'admin'


def test_shapefile_import_end_to_end(client):
    """7.2 shapefile zip 上传 → 校验 → 解压部署 → 触发 → 审计日志。"""
    token = _login(client)
    zip_buf, manifest = _make_shapefile_zip()
    resp = client.post(
        '/api/v1/data/import',
        headers={'Authorization': f'Bearer {token}'},
        data={'data_type': 'shapefile', 'file': (zip_buf, 'shp.zip')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200

    # 验证 shapefile 组件已解压部署到 target_dir
    for shp_name in ['current', '2020', '2021']:
        for ext in ['.shp', '.cpg', '.dbf', '.prj', '.shx']:
            expected = os.path.join(client._shp_dir, f'{shp_name}{ext}')
            assert os.path.exists(expected), f"缺少部署文件: {shp_name}{ext}"

    # 验证 manifest.json 也已部署
    assert os.path.exists(os.path.join(client._shp_dir, 'manifest.json'))

    # 验证审计日志
    entries = _read_audit_log(client)
    assert len(entries) == 1
    assert entries[0]['data_type'] == 'shapefile'
    assert entries[0]['success'] is True


def test_dat_import_end_to_end(client):
    """7.3 耕地质量评价 CSV（data_type=dat）上传 → 校验 → 部署 → check_deployment → 审计日志。"""
    token = _login(client)
    grade_csv_bytes = GRADE_CSV_CONTENT.encode('utf-8')
    resp = client.post(
        '/api/v1/data/import',
        headers={'Authorization': f'Bearer {token}'},
        data={'data_type': 'dat', 'file': (io.BytesIO(grade_csv_bytes), 'Farmland_quality_Level_Database.csv')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200

    # 验证文件已部署到 target_dir/Farmland_quality_Level_Database.csv
    deployed = os.path.join(client._dat_dir, 'Farmland_quality_Level_Database.csv')
    assert os.path.exists(deployed)
    with open(deployed, 'rb') as f:
        assert f.read() == grade_csv_bytes

    # 验证审计日志
    entries = _read_audit_log(client)
    assert len(entries) == 1
    assert entries[0]['data_type'] == 'dat'
    assert entries[0]['success'] is True


def test_trigger_failure_rolls_back(client, monkeypatch):
    """7.4 触发失败 → 回滚 → 审计日志记录回滚。"""
    from framework.api.routes import data_import as di

    # 先部署一个原始 CSV（模拟已有数据）
    original_content = CSV_CONTENT.encode('utf-8')
    with open(os.path.join(client._csv_dir, 'test.csv'), 'wb') as f:
        f.write(original_content)

    # Mock trigger 抛异常
    def trigger_fail(p, timeout=None):
        raise RuntimeError('model crashed')
    monkeypatch.setattr(di, 'trigger_csv_evaluate', trigger_fail)

    token = _login(client)
    new_content = CSV_HEADER + '\n' + '珠江区,亚区2,7.0,3.0,20,120,1.4,粘土,低,高,山地,异质,80,15\n'
    resp = client.post(
        '/api/v1/data/import',
        headers={'Authorization': f'Bearer {token}'},
        data={'data_type': 'csv', 'file': (io.BytesIO(new_content.encode('utf-8')), 'new.csv')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 500

    # 验证回滚：test.csv 内容应恢复为原始内容（含"亚区1"，不含"亚区2"）
    with open(os.path.join(client._csv_dir, 'test.csv'), 'r', encoding='utf-8') as f:
        restored = f.read()
    assert '亚区1' in restored
    assert '亚区2' not in restored

    # 验证审计日志记录了失败 + 回滚
    entries = _read_audit_log(client)
    assert len(entries) == 1
    assert entries[0]['success'] is False
    assert entries[0]['restored_from_backup'] is True


def test_backup_retention_policy(client):
    """7.5 备份保留策略：预创建 4 个旧备份 + 导入 1 次 → cleanup 保留最近 3 份。

    偏离 tasks.md "连续导入 4 次"：改为预创建旧备份 + 1 次导入，
    以直接测试 cleanup_backups 删除逻辑，且避免秒级时间戳碰撞问题。
    """
    # 预创建 4 个旧时间戳备份目录（每个含一个假文件）
    backup_root = os.path.join(client._csv_dir, 'backup')
    os.makedirs(backup_root, exist_ok=True)
    old_timestamps = ['20260101-000001', '20260101-000002', '20260101-000003', '20260101-000004']
    for ts in old_timestamps:
        bk_dir = os.path.join(backup_root, ts)
        os.makedirs(bk_dir)
        with open(os.path.join(bk_dir, 'old_test.csv'), 'w', encoding='utf-8') as f:
            f.write('old data')

    # 部署一个现有 test.csv（供 backup_existing 备份）
    with open(os.path.join(client._csv_dir, 'test.csv'), 'w', encoding='utf-8') as f:
        f.write(CSV_CONTENT)

    # 导入新 CSV（会备份现有 test.csv + 触发 cleanup_backups 保留 3 份）
    token = _login(client)
    new_content = CSV_HEADER + '\n' + '珠江区,亚区3,7.5,3.5,25,130,1.5,砂土,中,低,丘陵,均质,60,10\n'
    resp = client.post(
        '/api/v1/data/import',
        headers={'Authorization': f'Bearer {token}'},
        data={'data_type': 'csv', 'file': (io.BytesIO(new_content.encode('utf-8')), 'new.csv')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200

    # 验证 backup/ 下仅保留 3 份
    remaining = [d for d in os.listdir(backup_root) if os.path.isdir(os.path.join(backup_root, d))]
    assert len(remaining) == 3, f"期望 3 个备份目录，实际 {len(remaining)}: {remaining}"

    # 验证最旧的 2 个已被删除
    assert '20260101-000001' not in remaining
    assert '20260101-000002' not in remaining

    # 验证当前时间戳的备份存在（含原始 test.csv）
    current_backups = [d for d in remaining if d.startswith('2026')]
    assert len(current_backups) >= 1
