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
    monkeypatch.setattr(
        "framework.api.routes.docs.ingestion_worker.submit_ingest", lambda **kwargs: None,
    )
    fake_store = _VectorStore()
    monkeypatch.setattr("framework.api.routes.docs.vector_store", fake_store)

    with app.app_context():
        User.__table__.create(db.engine)
        Document.__table__.create(db.engine)
        DataFile.__table__.create(db.engine)
        DocumentLabel.__table__.create(db.engine)
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


def test_regular_user_cannot_publish_public_document(client):
    token = _token(client, "user", "user123")
    response = client.post(
        "/api/v1/docs/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file": (io.BytesIO(b"content"), "forbidden.txt"),
            "visibility_scope": "public",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 403


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
