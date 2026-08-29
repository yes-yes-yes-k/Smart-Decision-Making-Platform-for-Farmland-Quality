"""测试上传接口异步化：文档类返回 202 + status=0，并提交后台 worker。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from flask import Flask
from framework.api.routes import docs as docs_route
from framework.models.user import db
from framework.upload import ingestion_worker


@pytest.fixture(autouse=True)
def _stub_app_ctx(monkeypatch):
    """push minimal Flask app + request context，让 db.session / Document.query / 装饰器可访问。"""
    app = Flask("stub")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    # 跳过 @jwt_required() 的 JWT 验证（避免依赖真实 request/JWT）
    from flask_jwt_extended import view_decorators as _jwt_vd
    import flask_jwt_extended
    monkeypatch.setattr(_jwt_vd, "verify_jwt_in_request", lambda *a, **kw: None)
    monkeypatch.setattr(flask_jwt_extended, "verify_jwt_in_request", lambda *a, **kw: None)
    with app.app_context():
        with app.test_request_context():
            yield


def _make_request(filename, category):
    class _File:
        def __init__(self, name, size):
            self.filename = name
            self.content_length = size
    class _Req:
        method = "POST"
        path = "/upload"
        files = {"file": _File(filename, 100)}
        form = {"category": category}
    return _Req()


def test_upload_document_returns_202_and_submits(monkeypatch, tmp_path):
    # 准备：mock 文件保存、查重、worker 提交
    saved_path = tmp_path / "uuid.pdf"
    saved_path.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(docs_route, "save_uploaded_file",
                       lambda f: ("uuid.pdf", str(saved_path), "hash123"))
    monkeypatch.setattr(docs_route, "get_file_type", lambda name: "pdf")
    monkeypatch.setattr(docs_route, "allowed_file", lambda name: True)

    # 查重：返回 None（不重复）—— 保留 Document.query descriptor 但 mock filter_by
    class _Q:
        def first(self): return None
    class _Query:
        def filter_by(self, **kw):
            return _Q()
    monkeypatch.setattr(docs_route.Document, "query", _Query())

    # db.session.add 在调用时给 obj 设置 id（mock commit 后才有 id）
    def _fake_add(obj):
        obj.id = 42
    monkeypatch.setattr(docs_route.db.session, "add", _fake_add)
    monkeypatch.setattr(docs_route.db.session, "commit", lambda: None)

    submitted = {}
    monkeypatch.setattr(ingestion_worker, "submit_ingest",
                        lambda **kw: submitted.update(kw))

    monkeypatch.setattr(docs_route, "request", _make_request("test.pdf", "acidification"))
    monkeypatch.setattr(docs_route, "get_jwt_identity", lambda: 1)
    monkeypatch.setattr(docs_route.os.path, "getsize", lambda p: 100)

    # 执行
    resp = docs_route.upload_document()
    body = resp[0].get_json()
    code = resp[1]

    assert code == 202
    assert body["data"]["status"] == docs_route.Document.STATUS_PENDING
    assert submitted.get("document_id") == 42
    assert submitted.get("doc_name") == "test.pdf"


def test_upload_data_file_stays_sync(monkeypatch, tmp_path):
    # 数据文件（raw_data/improved_data）保持同步，不调 submit_ingest
    saved_path = tmp_path / "data.csv"
    saved_path.write_text("col\nval")
    monkeypatch.setattr(docs_route, "save_uploaded_file",
                       lambda f: ("data.csv", str(saved_path), "hashcsv"))
    monkeypatch.setattr(docs_route, "get_file_type", lambda name: "csv")
    monkeypatch.setattr(docs_route, "allowed_file", lambda name: True)

    class _Q:
        def first(self): return None
    class _Query:
        def filter_by(self, **kw):
            return _Q()
    monkeypatch.setattr(docs_route.Document, "query", _Query())

    submitted = {"called": False}
    monkeypatch.setattr(ingestion_worker, "submit_ingest", lambda **kw: submitted.update({"called": True}))

    def _fake_add(obj):
        obj.id = 7
    monkeypatch.setattr(docs_route.db.session, "add", _fake_add)
    monkeypatch.setattr(docs_route.db.session, "commit", lambda: None)

    monkeypatch.setattr(docs_route, "request", _make_request("data.csv", "raw_data"))
    monkeypatch.setattr(docs_route, "get_jwt_identity", lambda: 1)
    monkeypatch.setattr(docs_route.os.path, "getsize", lambda p: 100)

    resp = docs_route.upload_document()
    assert resp[1] == 200
    assert submitted["called"] is False
