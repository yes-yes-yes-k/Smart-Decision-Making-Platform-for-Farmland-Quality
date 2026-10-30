import io

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager
from werkzeug.security import generate_password_hash

from framework.api.routes.auth import auth_bp
from framework.api.routes.docs import docs_bp
from framework.models.data_file import DataFile
from framework.models.document import Document
from framework.models.document_label import DocumentLabel
from framework.models.ingestion import IngestionBatch, IngestionItem
from framework.models.user import User, db


class _VectorStore:
    def __init__(self):
        self.updates = []

    def update_document_metadata(self, document_id, updates, owner_id=None):
        self.updates.append((document_id, updates, owner_id))
        return 1

    def delete_by_document_id(self, *args, **kwargs):
        return 0


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'kb.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY="test-secret-at-least-thirty-two-bytes-long",
        UPLOAD_FOLDER=str(tmp_path / "uploads"),
    )
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(docs_bp, url_prefix="/api/v1/docs")
    submitted = []
    monkeypatch.setattr(
        "framework.api.routes.docs.ingestion_worker.submit_ingest",
        lambda **kwargs: submitted.append(kwargs),
    )
    fake_store = _VectorStore()
    monkeypatch.setattr("framework.api.routes.docs.vector_store", fake_store)

    with app.app_context():
        User.__table__.create(db.engine)
        Document.__table__.create(db.engine)
        DataFile.__table__.create(db.engine)
        DocumentLabel.__table__.create(db.engine)
        IngestionBatch.__table__.create(db.engine)
        IngestionItem.__table__.create(db.engine)
        admin = User(
            username="admin", password=generate_password_hash("admin123"),
            nickname="管理员", role="admin", status=1,
        )
        user = User(
            username="user", password=generate_password_hash("user123"),
            nickname="用户", role="user", status=1,
        )
        db.session.add_all([admin, user])
        db.session.commit()
        public = Document(
            doc_name="public.txt", file_path="public.txt", file_type="txt",
            category="cultivated_land_quality", status=1, create_by=admin.id,
            visibility_scope="public",
        )
        admin_private = Document(
            doc_name="admin-private.txt", file_path="admin-private.txt", file_type="txt",
            category="other", status=1, create_by=admin.id,
            visibility_scope="private",
        )
        user_private = Document(
            doc_name="user-private.txt", file_path="user-private.txt", file_type="txt",
            category="other", status=1, create_by=user.id,
            visibility_scope="private",
        )
        db.session.add_all([public, admin_private, user_private])
        db.session.flush()
        db.session.add_all([
            DocumentLabel(
                document_id=public.id,
                label_code="cultivated_land_quality",
                label_level="domain",
                review_status=DocumentLabel.STATUS_APPROVED,
                assignment_source=DocumentLabel.SOURCE_MIGRATION,
                create_by=admin.id,
            ),
            DocumentLabel(
                document_id=public.id,
                label_code="heavy_metal",
                label_level="domain",
                review_status=DocumentLabel.STATUS_PENDING,
                assignment_source=DocumentLabel.SOURCE_AUTOMATIC,
                confidence=0.71,
                create_by=admin.id,
            ),
        ])
        db.session.commit()
        ids = {"public": public.id, "admin": admin.id, "user": user.id}

    test_client = app.test_client()
    test_client._ids = ids
    test_client._vector_store = fake_store
    test_client._submitted = submitted
    test_client._app = app
    return test_client


def _token(client, username, password):
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.get_json()["data"]["token"]


def test_regular_user_lists_public_and_own_private_only(client):
    token = _token(client, "user", "user123")
    response = client.get(
        "/api/v1/docs/", headers={"Authorization": f"Bearer {token}"},
    )
    names = {item["doc_name"] for item in response.get_json()["data"]["list"]}
    assert names == {"public.txt", "user-private.txt"}


def test_regular_user_upload_waits_for_review_before_publication(client):
    token = _token(client, "user", "user123")
    response = client.post(
        "/api/v1/docs/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file": (io.BytesIO(b"content"), "forbidden.txt"),
            "visibility_scope": "public",
            "domain_labels": "cultivated_land_quality",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202
    payload = response.get_json()["data"]
    assert payload["document"]["visibility_scope"] == "private"
    assert payload["document"]["review_status"] == "pending"
    assert payload["ingestion"]["stage"] == "awaiting_admin_review"
    assert client._submitted == []


def _upload_user_paper(client, filename="paper.txt"):
    token = _token(client, "user", "user123")
    return client.post(
        "/api/v1/docs/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file": (io.BytesIO(b"literature body"), filename),
            "document_kind": "academic_paper",
            "title": "Test paper",
            "domain_labels": "cultivated_land_quality",
            "idempotency_key": f"key-{filename}",
        },
        content_type="multipart/form-data",
    )


def test_admin_approval_starts_ingestion_with_public_target(client):
    uploaded = _upload_user_paper(client)
    assert uploaded.status_code == 202
    document_id = uploaded.get_json()["data"]["document"]["id"]

    user_token = _token(client, "user", "user123")
    denied = client.post(
        f"/api/v1/docs/{document_id}/review",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"decision": "approve"},
    )
    assert denied.status_code == 403

    admin_token = _token(client, "admin", "admin123")
    approved = client.post(
        f"/api/v1/docs/{document_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "decision": "approve",
            "domain_labels": ["cultivated_land_quality"],
            "idempotency_key": "review-1",
        },
    )
    assert approved.status_code == 200
    assert approved.get_json()["data"]["document"]["review_status"] == "approved"
    assert len(client._submitted) == 1
    assert client._submitted[0]["visibility_scope"] == "public"
    assert client._submitted[0]["domain_labels"] == ["cultivated_land_quality"]


def test_admin_rejection_is_terminal_and_does_not_start_worker(client):
    uploaded = _upload_user_paper(client, "rejected.txt")
    document_id = uploaded.get_json()["data"]["document"]["id"]
    admin_token = _token(client, "admin", "admin123")
    rejected = client.post(
        f"/api/v1/docs/{document_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "decision": "reject",
            "review_note": "标签不符合资料内容",
            "idempotency_key": "review-reject-1",
        },
    )
    assert rejected.status_code == 200
    document = rejected.get_json()["data"]["document"]
    assert document["status"] == Document.STATUS_REJECTED
    assert document["processing_stage"] == "rejected"
    assert client._submitted == []


def test_literature_upload_requires_labels_and_rejects_private(client):
    token = _token(client, "user", "user123")
    missing = client.post(
        "/api/v1/docs/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"file": (io.BytesIO(b"body"), "missing.txt")},
        content_type="multipart/form-data",
    )
    assert missing.status_code == 422
    assert missing.get_json()["error_code"] == "domain_label_required"

    private = client.post(
        "/api/v1/docs/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file": (io.BytesIO(b"body"), "private.txt"),
            "domain_labels": "cultivated_land_quality",
            "visibility_scope": "private",
        },
        content_type="multipart/form-data",
    )
    assert private.status_code == 422
    assert private.get_json()["error_code"] == "visibility_not_configurable"


def test_upload_idempotency_replays_same_result_and_rejects_changed_file(client):
    first = _upload_user_paper(client, "idempotent.txt")
    second = _upload_user_paper(client, "idempotent.txt")
    assert second.status_code == 202
    assert (
        first.get_json()["data"]["document"]["id"]
        == second.get_json()["data"]["document"]["id"]
    )

    token = _token(client, "user", "user123")
    conflict = client.post(
        "/api/v1/docs/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file": (io.BytesIO(b"different body"), "idempotent.txt"),
            "domain_labels": "cultivated_land_quality",
            "idempotency_key": "key-idempotent.txt",
        },
        content_type="multipart/form-data",
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["error_code"] == "idempotency_conflict"


def test_failed_approved_ingestion_can_be_retried_by_uploader(client):
    uploaded = _upload_user_paper(client, "retry.txt")
    document_id = uploaded.get_json()["data"]["document"]["id"]
    admin_token = _token(client, "admin", "admin123")
    approved = client.post(
        f"/api/v1/docs/{document_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"decision": "approve", "idempotency_key": "approve-retry"},
    )
    assert approved.status_code == 200
    with client._app.app_context():
        document = db.session.get(Document, document_id)
        document.status = Document.STATUS_FAILED
        document.processing_stage = "failed"
        document.failure_code = "ocr_failed"
        document.failure_message = "OCR temporary failure"
        document.retryable = True
        db.session.commit()

    user_token = _token(client, "user", "user123")
    retried = client.post(
        f"/api/v1/docs/{document_id}/retry",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert retried.status_code == 202
    assert retried.get_json()["data"]["ingestion"]["attempt"] == 2
    assert len(client._submitted) == 2


def test_regular_user_cannot_create_batch(client):
    token = _token(client, "user", "user123")
    response = client.post(
        "/api/v1/docs/batches",
        headers={"Authorization": f"Bearer {token}"},
        json={"staging_token": "initial", "manifest_path": "manifest.jsonl", "dry_run": True},
    )
    assert response.status_code == 403


def test_standard_authority_verification_requires_audit_source(client):
    token = _token(client, "user", "user123")
    uploaded = client.post(
        "/api/v1/docs/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file": (io.BytesIO(b"standard body"), "standard.txt"),
            "document_kind": "standard",
            "domain_labels": "cultivated_land_quality",
        },
        content_type="multipart/form-data",
    )
    document_id = uploaded.get_json()["data"]["document"]["id"]
    admin_token = _token(client, "admin", "admin123")
    missing_source = client.post(
        f"/api/v1/docs/{document_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "decision": "approve",
            "authority_status": "verified_current",
            "idempotency_key": "authority-review-1",
        },
    )
    assert missing_source.status_code == 422
    assert missing_source.get_json()["error_code"] == "authority_source_required"

    approved = client.post(
        f"/api/v1/docs/{document_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "decision": "approve",
            "authority_status": "verified_current",
            "authority_verification_source": "主管部门现行标准目录",
            "idempotency_key": "authority-review-1",
        },
    )
    assert approved.status_code == 200
    document = approved.get_json()["data"]["document"]
    assert document["authority_status"] == "verified_current"
    assert document["provenance_metadata"]["authority_verification"]["source"] == "主管部门现行标准目录"


def test_review_persists_retryable_failure_when_queue_is_full(client, monkeypatch):
    uploaded = _upload_user_paper(client, "queue-full.txt")
    document_id = uploaded.get_json()["data"]["document"]["id"]
    from framework.upload import ingestion_worker
    monkeypatch.setattr(
        ingestion_worker,
        "submit_ingest",
        lambda **kwargs: (_ for _ in ()).throw(
            ingestion_worker.QueueCapacityExceeded("full")
        ),
    )
    admin_token = _token(client, "admin", "admin123")
    response = client.post(
        f"/api/v1/docs/{document_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"decision": "approve", "idempotency_key": "queue-review-1"},
    )
    assert response.status_code == 503
    assert response.get_json()["error_code"] == "queue_capacity_exceeded"
    with client._app.app_context():
        document = db.session.get(Document, document_id)
        assert document.status == Document.STATUS_FAILED
        assert document.retryable is True


def test_pending_cross_label_requires_admin_review(client):
    user_token = _token(client, "user", "user123")
    denied = client.put(
        f"/api/v1/docs/{client._ids['public']}/labels",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"approved_labels": ["heavy_metal"]},
    )
    assert denied.status_code == 403

    admin_token = _token(client, "admin", "admin123")
    queue = client.get(
        "/api/v1/docs/label-reviews",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert queue.status_code == 200
    assert [item["label_code"] for item in queue.get_json()["data"]] == [
        "heavy_metal"
    ]
    response = client.put(
        f"/api/v1/docs/{client._ids['public']}/labels",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"approved_labels": ["heavy_metal"]},
    )
    assert response.status_code == 200
    assert set(response.get_json()["data"]["domain_labels"]) == {
        "cultivated_land_quality", "heavy_metal",
    }
    assert client._vector_store.updates[-1][1]["domain_heavy_metal"] is True
