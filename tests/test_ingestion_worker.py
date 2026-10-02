"""测试异步入库 worker 状态机（mock vector_store 与 parse_document）。"""
import sys
import os
import types
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

    # _ingest 只需要 create_app；注入轻量模块，避免单元测试加载完整 API 依赖。
    app_module = types.ModuleType("framework.api.app")
    app_module.create_app = lambda: _StubApp()
    monkeypatch.setitem(sys.modules, "framework.api.app", app_module)
    monkeypatch.setattr(
        ingestion_worker,
        "assign_labels_for_ingestion",
        lambda *args, **kwargs: list(kwargs.get("explicit_labels") or []),
    )


def test_ingest_success_transitions_pending_to_completed(monkeypatch):
    _patch_app_context(monkeypatch)
    fake = _FakeDoc(1)

    monkeypatch.setattr(ingestion_worker, "_set_status", lambda did, s: setattr(fake, "status", s))
    monkeypatch.setattr(ingestion_worker, "parse_document", lambda fp, ft, page_aware=True: "正文内容" * 100)
    monkeypatch.setattr(ingestion_worker, "split_text", lambda text, size=None, overlap=None: ["c1", "c2"])

    class _FakeVS:
        def add_documents(self, chunks, metadatas, ids=None, category=None):
            assert ids == ["doc-1-chunk-0", "doc-1-chunk-1"]
            assert all(m["owner_id"] == 7 for m in metadatas)
            assert all(m["visibility_scope"] == "private" for m in metadatas)
            assert all(m["domain_cultivated_land_quality"] is True for m in metadatas)
            assert all("treatment_type" not in m for m in metadatas)
            return len(chunks)
        def delete_by_document_id(self, document_id, owner_id=None):
            return 0
    monkeypatch.setattr(ingestion_worker, "vector_store", _FakeVS())

    class _FakeQuery:
        def get(self, did):
            return fake
    monkeypatch.setattr(ingestion_worker.db.session, "query", lambda *a: _FakeQuery())
    monkeypatch.setattr(ingestion_worker.db.session, "commit", lambda: setattr(fake, "_committed", True))

    _ingest(1, "/tmp/x.pdf", "pdf", "x.pdf", "acidification", None, 7)

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
    monkeypatch.setattr(
        ingestion_worker.vector_store, "delete_by_document_id", lambda *a, **k: 0,
    )

    _ingest(2, "/tmp/bad.pdf", "pdf", "bad.pdf", "other", None, 7)

    assert fake.status == Document.STATUS_FAILED


def test_ingest_incomplete_vector_write_promotes_to_failed(monkeypatch):
    _patch_app_context(monkeypatch)
    fake = _FakeDoc(3)
    monkeypatch.setattr(ingestion_worker, "_set_status", lambda did, s: setattr(fake, "status", s))
    monkeypatch.setattr(ingestion_worker, "parse_document", lambda *a, **k: "正文")
    monkeypatch.setattr(ingestion_worker, "split_text", lambda *a, **k: ["c1", "c2"])

    class _FakeVS:
        def __init__(self):
            self.deleted = []
        def add_documents(self, *args, **kwargs):
            return 1
        def delete_by_document_id(self, document_id, owner_id=None):
            self.deleted.append((document_id, owner_id))
            return 1
    fake_vs = _FakeVS()
    monkeypatch.setattr(ingestion_worker, "vector_store", fake_vs)

    class _FakeQuery:
        def get(self, did):
            return fake
    monkeypatch.setattr(ingestion_worker.db.session, "query", lambda *a: _FakeQuery())
    monkeypatch.setattr(ingestion_worker.db.session, "commit", lambda: None)

    _ingest(3, "/tmp/partial.pdf", "pdf", "partial.pdf", "other", None, 9)

    assert fake.status == Document.STATUS_FAILED
    assert fake_vs.deleted == [(3, 9)]
