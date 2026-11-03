import json
import zipfile
from pathlib import Path

import pytest
from flask import Flask

from framework.config import Config
from framework.models.document import Document
from framework.models.document_label import DocumentLabel
from framework.models.ingestion import IngestionBatch, IngestionItem
from framework.models.user import User, db
from framework.upload import literature_batch


@pytest.fixture
def batch_context(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    upload = tmp_path / "uploads"
    manifest = staging / "manifest.jsonl"
    pdf_path = staging / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\ntest fixture")
    manifest.write_text(json.dumps({
        "schema_version": "1.0",
        "item_key": "paper-1",
        "path": "paper.pdf",
        "document_kind": "academic_paper",
        "title": "Batch paper",
        "domain_labels": ["cultivated_land_quality"],
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        Config, "LITERATURE_STAGING_ROOTS_JSON",
        json.dumps({"initial": str(staging)}),
    )
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload))
    monkeypatch.setattr(Config, "LITERATURE_RETAIN_DERIVED_PDF", False)
    monkeypatch.setattr(literature_batch, "validate_file_content", lambda *args: None)

    app = Flask("literature-batch-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'batch.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    submitted = []
    monkeypatch.setattr(
        literature_batch.ingestion_worker, "submit_ingest",
        lambda **kwargs: submitted.append(kwargs),
    )
    with app.app_context():
        User.__table__.create(db.engine)
        Document.__table__.create(db.engine)
        DocumentLabel.__table__.create(db.engine)
        IngestionBatch.__table__.create(db.engine)
        IngestionItem.__table__.create(db.engine)
        admin = User(username="admin", password="x", role="admin", status=1)
        db.session.add(admin)
        db.session.commit()
        yield {
            "staging": staging,
            "manifest": manifest,
            "admin": admin,
            "submitted": submitted,
        }


def test_manifest_dry_run_is_read_only(batch_context):
    report, _ = literature_batch.preflight_manifest("initial", "manifest.jsonl")
    assert report["counts"] == {"ready": 1}
    assert report["items"][0]["domain_labels"] == ["cultivated_land_quality"]
    assert IngestionBatch.query.count() == 0
    assert Document.query.count() == 0


def test_execute_manifest_creates_approved_public_target(batch_context):
    batch, created = literature_batch.execute_manifest(
        staging_token="initial",
        manifest_relative_path="manifest.jsonl",
        batch_key="batch-1",
        name="Initial literature",
        actor_id=batch_context["admin"].id,
    )
    assert created is True
    assert batch.total_count == 1
    document = Document.query.one()
    assert document.review_status == Document.REVIEW_APPROVED
    assert document.visibility_scope == "private"
    assert len(batch_context["submitted"]) == 1
    assert batch_context["submitted"][0]["visibility_scope"] == "public"


def test_manifest_path_cannot_escape_staging_root(batch_context):
    batch_context["manifest"].write_text(json.dumps({
        "schema_version": "1.0",
        "item_key": "escape",
        "path": "../outside.pdf",
        "domain_labels": ["cultivated_land_quality"],
    }) + "\n", encoding="utf-8")
    report, _ = literature_batch.preflight_manifest("initial", "manifest.jsonl")
    assert report["counts"] == {"invalid": 1}
    assert "staging root" in report["items"][0]["reason"]


def test_resume_batch_creates_new_attempt_for_interrupted_item(batch_context):
    batch, _ = literature_batch.execute_manifest(
        staging_token="initial",
        manifest_relative_path="manifest.jsonl",
        batch_key="batch-resume",
        name="Resume batch",
        actor_id=batch_context["admin"].id,
    )
    item = batch.items[0]
    item.state = "processing"
    item.stage = "ocr"
    item.document.status = Document.STATUS_PROCESSING
    db.session.commit()

    resumed_batch, resumed = literature_batch.resume_batch("batch-resume")
    assert resumed == 1
    attempts = sorted(
        item.attempt_no for item in resumed_batch.items if item.document_id is not None
    )
    assert attempts == [1, 2]
    previous = next(item for item in resumed_batch.items if item.attempt_no == 1)
    assert previous.state == "superseded"
    assert previous.stage == "superseded"
    assert previous.finished_at is not None
    literature_batch.refresh_batch_counters(resumed_batch.id)
    assert resumed_batch.completed_count == 0
    assert resumed_batch.failed_count == 0
    assert len(batch_context["submitted"]) == 2


def test_zip_path_traversal_is_rejected(batch_context):
    archive = batch_context["staging"] / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("../escape.pdf", b"%PDF-1.7")
    batch_context["manifest"].write_text(json.dumps({
        "schema_version": "1.0",
        "item_key": "unsafe-zip",
        "path": "unsafe.zip",
        "domain_labels": ["cultivated_land_quality"],
    }) + "\n", encoding="utf-8")
    report, _ = literature_batch.preflight_manifest("initial", "manifest.jsonl")
    assert report["counts"] == {"invalid": 1}
    assert "路径不安全" in report["items"][0]["reason"]
