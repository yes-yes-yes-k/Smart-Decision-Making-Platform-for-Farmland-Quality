"""测试文档上传查重与删除清理功能"""
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


class MockVectorStore:
    """模拟向量库，避免测试依赖 ChromaDB 磁盘操作"""
    def __init__(self):
        self._should_fail = False

    def add_documents(self, texts, metadatas=None, ids=None, category=None):
        if self._should_fail:
            raise RuntimeError("mock vector store failure")
        return len(texts) if texts else 0

    def delete_by_source(self, source_doc_name):
        if self._should_fail:
            raise RuntimeError("mock vector store failure")
        return 0

    def delete_by_document_id(self, document_id, owner_id=None):
        if self._should_fail:
            raise RuntimeError("mock vector store failure")
        return 0

    def set_fail(self, should_fail):
        self._should_fail = should_fail


@pytest.fixture
def client(monkeypatch):
    """创建测试客户端，使用 SQLite 临时文件数据库，mock 向量库"""
    tmp_upload = tempfile.mkdtemp(prefix="test_upload_")
    tmp_db_dir = tempfile.mkdtemp(prefix="test_db_")
    tmp_db_path = os.path.join(tmp_db_dir, "test.db")

    original_folder = Config.UPLOAD_FOLDER
    original_db_uri = SQLiteConfig.SQLALCHEMY_DATABASE_URI
    Config.UPLOAD_FOLDER = tmp_upload
    # 在 create_app 之前覆盖 SQLiteConfig 的 URI，确保引擎绑定到临时文件
    SQLiteConfig.SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmp_db_path}'

    app = create_app('sqlite')
    app.config['TESTING'] = True

    mock_vs = MockVectorStore()
    monkeypatch.setattr('framework.api.routes.docs.vector_store', mock_vs)
    # 异步 worker 适配：阻止后台 worker 运行（测试关注查重/删除逻辑，不关注入库）
    monkeypatch.setattr('framework.upload.ingestion_worker.submit_ingest', lambda **kw: None)

    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            nickname='管理员',
            role='admin',
            status=1
        )
        user2 = User(
            username='user2',
            password=generate_password_hash('user1234'),
            nickname='用户2',
            role='user',
            status=1
        )
        db.session.add(admin)
        db.session.add(user2)
        db.session.commit()
        admin_id = admin.id
        user2_id = user2.id

    client = app.test_client()

    # 暴露 app、mock_vs 和用户 ID 供测试使用
    client._app = app
    client._mock_vs = mock_vs
    client._admin_id = admin_id
    client._user2_id = user2_id
    client._tmp_upload = tmp_upload

    yield client

    Config.UPLOAD_FOLDER = original_folder
    SQLiteConfig.SQLALCHEMY_DATABASE_URI = original_db_uri
    shutil.rmtree(tmp_upload, ignore_errors=True)
    shutil.rmtree(tmp_db_dir, ignore_errors=True)


def _login(client, username, password):
    """登录获取 JWT token"""
    resp = client.post('/api/v1/auth/login', json={
        'username': username,
        'password': password
    })
    assert resp.status_code == 200
    return resp.get_json()['data']['token']


def _upload(client, token, filename, content):
    """上传文件辅助函数"""
    resp = client.post(
        '/api/v1/docs/upload',
        headers={'Authorization': f'Bearer {token}'},
        data={
            'file': (io.BytesIO(content), filename),
            'domain_labels': 'cultivated_land_quality',
        },
        content_type='multipart/form-data'
    )
    return resp


def test_upload_first_occurrence_stores_hash(client):
    """首次上传成功，file_hash 已记录"""
    token = _login(client, 'admin', 'admin123')
    resp = _upload(client, token, 'first.txt', b'unique content for first upload')

    assert resp.status_code == 202
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['data']['document']['file_hash'] is not None
    assert len(data['data']['document']['file_hash']) == 64
    print("✓ 首次上传成功，file_hash 已记录")


def test_upload_duplicate_same_user_returns_409(client):
    """同用户上传重复内容（不同文件名）返回 409 Conflict"""
    token = _login(client, 'admin', 'admin123')

    # 首次上传
    resp1 = _upload(client, token, 'original.txt', b'duplicate detection test content')
    assert resp1.status_code == 202
    existing_id = resp1.get_json()['data']['document']['id']

    # 同用户再次上传相同内容，不同文件名
    resp2 = _upload(client, token, 'renamed_copy.txt', b'duplicate detection test content')

    assert resp2.status_code == 409
    data = resp2.get_json()
    assert data['status'] == 'error'
    assert data['existing_document_id'] == existing_id
    print("✓ 同用户重复上传返回 409 Conflict")


def test_upload_same_content_different_users_succeeds(client):
    """跨用户上传相同内容返回 200 成功"""
    token1 = _login(client, 'admin', 'admin123')
    token2 = _login(client, 'user2', 'user1234')

    resp1 = _upload(client, token1, 'user1_doc.txt', b'shared content across users')
    assert resp1.status_code == 202

    resp2 = _upload(client, token2, 'user2_doc.txt', b'shared content across users')
    assert resp2.status_code == 202
    assert resp2.get_json()['data']['document']['id'] != resp1.get_json()['data']['document']['id']
    print("✓ 跨用户相同内容上传成功")


def test_upload_skips_historical_null_hash_documents(client):
    """历史文档 file_hash=NULL 不参与查重，上传不同内容应成功"""
    from framework.models.document import Document
    token = _login(client, 'admin', 'admin123')

    # 直接向数据库插入一条历史文档（file_hash=NULL）
    with client._app.app_context():
        legacy_doc = Document(
            doc_name='legacy.txt',
            file_path='legacy_file.txt',
            file_type='txt',
            file_size=100,
            chunk_count=1,
            status=1,
            file_hash=None,
            create_by=client._admin_id,
        )
        db.session.add(legacy_doc)
        db.session.commit()

    # 上传不同内容的新文档，应成功（不被历史 NULL hash 文档干扰）
    resp = _upload(client, token, 'new_content.txt', b'brand new content different from legacy')
    assert resp.status_code == 202
    assert resp.get_json()['data']['document']['file_hash'] is not None
    print("✓ 历史文档 file_hash=NULL 不参与查重")


def test_upload_duplicate_deletes_physical_file(client):
    """检测到重复时，刚保存的物理文件应被删除"""
    token = _login(client, 'admin', 'admin123')
    _upload(client, token, 'keep.txt', b'keep this content')

    resp = _upload(client, token, 'dup.txt', b'keep this content')
    assert resp.status_code == 409

    # uploads 目录中应只有首次上传的文件，无重复文件
    files_after = os.listdir(client._tmp_upload)
    assert len(files_after) == 1
    print("✓ 重复上传时物理文件已清理")


def test_delete_removes_db_vector_and_file(client):
    """正常删除：数据库记录、向量库数据、物理文件全删"""
    token = _login(client, 'admin', 'admin123')
    resp = _upload(client, token, 'to_delete.txt', b'content to be deleted')
    assert resp.status_code == 202
    doc_id = resp.get_json()['data']['document']['id']

    # 确认物理文件存在
    files_before = os.listdir(client._tmp_upload)
    assert len(files_before) == 1

    # 删除文档
    del_resp = client.delete(
        f'/api/v1/docs/{doc_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert del_resp.status_code == 200

    # 验证数据库记录已删除
    from framework.models.document import Document
    with client._app.app_context():
        doc = Document.query.get(doc_id)
        assert doc is None

    # 验证物理文件已删除
    files_after = os.listdir(client._tmp_upload)
    assert len(files_after) == 0
    print("✓ 正常删除清理三资源完成")


def test_delete_when_physical_file_missing(client):
    """物理文件已不存在时，DB 和向量库正常删除，返回 200"""
    token = _login(client, 'admin', 'admin123')
    resp = _upload(client, token, 'file_will_be_missing.txt', b'content for missing file test')
    assert resp.status_code == 202
    doc_id = resp.get_json()['data']['document']['id']

    # 手动删除物理文件模拟文件已不存在
    files = os.listdir(client._tmp_upload)
    for f in files:
        os.remove(os.path.join(client._tmp_upload, f))

    # 删除文档，应不报错
    del_resp = client.delete(
        f'/api/v1/docs/{doc_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert del_resp.status_code == 200

    from framework.models.document import Document
    with client._app.app_context():
        assert Document.query.get(doc_id) is None
    print("✓ 物理文件已不存在时删除不报错")


def test_delete_when_physical_file_deletion_fails(client, monkeypatch):
    """物理文件删除失败（权限错误）时，DB 和向量库正常删除，返回 200"""
    token = _login(client, 'admin', 'admin123')
    resp = _upload(client, token, 'protected.txt', b'content for deletion failure test')
    assert resp.status_code == 202
    doc_id = resp.get_json()['data']['document']['id']

    # mock os.remove 抛出权限异常
    import builtins
    original_remove = os.remove
    def fail_remove(path):
        raise PermissionError("mock permission denied")
    monkeypatch.setattr(os, 'remove', fail_remove)

    del_resp = client.delete(
        f'/api/v1/docs/{doc_id}',
        headers={'Authorization': f'Bearer {token}'}
    )

    # 恢复 os.remove 以便清理
    monkeypatch.setattr(os, 'remove', original_remove)

    assert del_resp.status_code == 200
    from framework.models.document import Document
    with client._app.app_context():
        assert Document.query.get(doc_id) is None
    print("✓ 物理文件删除失败时不阻塞业务")


def test_delete_when_vector_store_fails(client):
    """向量库删除失败时，DB 和物理文件正常删除，返回 200"""
    token = _login(client, 'admin', 'admin123')
    resp = _upload(client, token, 'vector_fail_test.txt', b'content for vector store failure test')
    assert resp.status_code == 202
    doc_id = resp.get_json()['data']['document']['id']

    # 配置 mock 向量库删除时抛异常
    client._mock_vs.set_fail(True)

    del_resp = client.delete(
        f'/api/v1/docs/{doc_id}',
        headers={'Authorization': f'Bearer {token}'}
    )

    client._mock_vs.set_fail(False)

    assert del_resp.status_code == 200
    from framework.models.document import Document
    with client._app.app_context():
        assert Document.query.get(doc_id) is None
    # 物理文件应已被删除
    files_after = os.listdir(client._tmp_upload)
    assert len(files_after) == 0
    print("✓ 向量库删除失败时不阻塞业务")
