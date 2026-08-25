"""测试上传入库时写入 chunk 级元数据。"""
import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.api.app import create_app
from framework.models.user import db, User
from framework.config import Config, SQLiteConfig
from werkzeug.security import generate_password_hash


class CaptureVectorStore:
    def __init__(self):
        self.captured = None

    def add_documents(self, texts, metadatas=None, ids=None):
        self.captured = {"texts": texts, "metadatas": metadatas, "ids": ids}
        return len(texts) if texts else 0

    def delete_by_source(self, source_doc_name):
        return 0


@pytest.fixture
def client(monkeypatch):
    tmp_upload = tempfile.mkdtemp(prefix="test_meta_upload_")
    tmp_db_dir = tempfile.mkdtemp(prefix="test_meta_db_")
    tmp_db_path = os.path.join(tmp_db_dir, "test.db")

    original_folder = Config.UPLOAD_FOLDER
    original_db_uri = SQLiteConfig.SQLALCHEMY_DATABASE_URI
    Config.UPLOAD_FOLDER = tmp_upload
    SQLiteConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_db_path}"

    app = create_app("sqlite")
    app.config["TESTING"] = True

    capture_vs = CaptureVectorStore()
    monkeypatch.setattr("framework.api.routes.docs.vector_store", capture_vs)

    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = User(username="admin", password=generate_password_hash("admin123"),
                     nickname="管理员", role="admin", status=1)
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    client = app.test_client()
    client._app = app
    client._capture_vs = capture_vs
    client._admin_id = admin_id

    yield client

    Config.UPLOAD_FOLDER = original_folder
    SQLiteConfig.SQLALCHEMY_DATABASE_URI = original_db_uri
    shutil.rmtree(tmp_upload, ignore_errors=True)
    shutil.rmtree(tmp_db_dir, ignore_errors=True)


def _login(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.get_json()["data"]["token"]


def test_upload_writes_chunk_metadata(client):
    token = _login(client)
    content = "土壤" * 1000  # 足够长以产生多块
    resp = client.post(
        "/api/v1/docs/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file": (io.BytesIO(content.encode("utf-8")), "meta.txt"),
            "category": "acidification",
            "treatment_type": "regulation",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200

    captured = client._capture_vs.captured
    assert captured is not None
    metadatas = captured["metadatas"]
    texts = captured["texts"]
    assert len(metadatas) == len(texts) > 0
    for i, meta in enumerate(metadatas):
        assert meta["source"] == "meta.txt"
        assert meta["category"] == "acidification"
        assert meta["treatment_type"] == "regulation"
        assert meta["chunk_index"] == i
    # page / section 本阶段不写入
    assert "page" not in metadatas[0]
    assert "section" not in metadatas[0]