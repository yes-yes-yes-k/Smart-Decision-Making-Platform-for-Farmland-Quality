"""测试观测 API：追溯链命中/未命中、看板指标、看板缺失、鉴权 401。"""
import sys
import os
import json
import datetime
import shutil
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.api.app import create_app
from framework.models.user import db, User
from framework.config import SQLiteConfig
from werkzeug.security import generate_password_hash


@pytest.fixture
def client():
    """创建测试客户端：SQLite 临时 DB + admin 用户。"""
    tmp_db_dir = tempfile.mkdtemp(prefix="test_observability_")
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
        db.session.add(admin)
        db.session.commit()

    client = app.test_client()
    client._app = app

    yield client

    SQLiteConfig.SQLALCHEMY_DATABASE_URI = original_db_uri
    shutil.rmtree(tmp_db_dir, ignore_errors=True)


def _login(client, username='admin', password='admin123'):
    """登录获取 JWT token。"""
    resp = client.post('/api/v1/auth/login', json={'username': username, 'password': password})
    assert resp.status_code == 200, f"登录失败: {resp.get_json()}"
    return resp.get_json()['data']['token']


def _write_log_entry(log_dir, tid, **overrides):
    """直接写一条按天命名的路由日志到 log_dir（不依赖全局日志状态）。"""
    day = datetime.datetime.now().strftime("%Y%m%d")
    path = os.path.join(str(log_dir), f"routing_calls_{day}.jsonl")
    entry = {
        "trace_id": tid,
        "timestamp": "2026-08-15 10:00:00",
        "data_version": "v1",
        "agent_version": "m2",
        "params": {},
    }
    entry.update(overrides)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


class TestTraceEndpoint:
    def test_trace_hit_returns_200(self, client, tmp_path, monkeypatch):
        from framework.observability import routing_log
        monkeypatch.setattr(routing_log, "_LOG_DIR", str(tmp_path))
        _write_log_entry(tmp_path, "trace-abc")
        token = _login(client)
        resp = client.get(
            "/api/v1/observability/trace/trace-abc",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["trace_id"] == "trace-abc"
        assert data["data_version"] == "v1"
        assert data["call_time"] == "2026-08-15 10:00:00"

    def test_trace_miss_returns_404(self, client, tmp_path, monkeypatch):
        from framework.observability import routing_log
        monkeypatch.setattr(routing_log, "_LOG_DIR", str(tmp_path))
        token = _login(client)
        resp = client.get(
            "/api/v1/observability/trace/not-exist",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_no_jwt_returns_401(self, client):
        resp = client.get("/api/v1/observability/trace/any")
        assert resp.status_code == 401