"""测试异步入库 worker 状态机（mock vector_store 与 parse_document）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.upload import ingestion_worker
from framework.upload.ingestion_worker import _ingest
from framework.models.document import Document


class _FakeDoc:
    def __init__(self, doc_id):
        self.id = doc_id
        self.status = Document.STATUS_PENDING
        self.chunk_count = 0


def _patch_app_context(monkeypatch):
    # 用真实 Flask app context 让 db.session 可访问（不连数据库）
    from flask import Flask
    from framework.models.user import db

    class _StubApp:
        def __init__(self):
            self._app = Flask("stub")
            self._app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
            self._app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
            db.init_app(self._app)

        def app_context(self):
            return self._app.app_context()

    # create_app 在 _ingest 内延迟导入，mock 源模块而非 ingestion_worker 命名空间
    monkeypatch.setattr("framework.api.app.create_app", lambda: _StubApp())


def test_ingest_success_transitions_pending_to_completed(monkeypatch):
    _patch_app_context(monkeypatch)
    fake = _FakeDoc(1)

    monkeypatch.setattr(ingestion_worker, "_set_status", lambda did, s: setattr(fake, "status", s))
    monkeypatch.setattr(ingestion_worker, "parse_document", lambda fp, ft, page_aware=True: "正文内容" * 100)
    monkeypatch.setattr(ingestion_worker, "split_text", lambda text, size=None, overlap=None: ["c1", "c2"])

    class _FakeVS:
        def add_documents(self, chunks, metadatas, category=None):
            return len(chunks)
    monkeypatch.setattr(ingestion_worker, "vector_store", _FakeVS())

    class _FakeQuery:
        def get(self, did):
            return fake
    monkeypatch.setattr(ingestion_worker.db.session, "query", lambda *a: _FakeQuery())
    monkeypatch.setattr(ingestion_worker.db.session, "commit", lambda: setattr(fake, "_committed", True))

    _ingest(1, "/tmp/x.pdf", "pdf", "x.pdf", "acidification", None)

    assert fake.status == Document.STATUS_COMPLETED
    assert fake.chunk_count == 2


def test_ingest_failure_promotes_to_failed(monkeypatch):
    _patch_app_context(monkeypatch)
    fake = _FakeDoc(2)

    def _boom_set(did, s):
        # pending → processing 正常；后续 parse 抛异常
        fake.status = s

    monkeypatch.setattr(ingestion_worker, "_set_status", _boom_set)

    def _parse_boom(fp, ft, page_aware=True):
        raise RuntimeError("解析爆炸")
    monkeypatch.setattr(ingestion_worker, "parse_document", _parse_boom)

    class _FakeQuery:
        def get(self, did):
            return fake
    monkeypatch.setattr(ingestion_worker.db.session, "query", lambda *a: _FakeQuery())
    monkeypatch.setattr(ingestion_worker.db.session, "commit", lambda: None)

    _ingest(2, "/tmp/bad.pdf", "pdf", "bad.pdf", "other", None)

    assert fake.status == Document.STATUS_FAILED
