"""Unit tests for the R2.6c candidate reader."""
from __future__ import annotations

from flask import Flask

from framework.knowledge_graph.candidate_reader import read_candidates
from framework.knowledge_graph.candidate_store import write_bundle
from framework.models.document import Document
from framework.models.user import User, db
from scripts.migrate_knowledge_graph_platform import ensure_knowledge_graph_platform_schema

SHA = "a" * 64


def _bundle() -> dict:
    span = {
        "document_id": 100, "document_sha256": SHA, "parse_version": SHA,
        "chunk_set_version": SHA, "chunk_index": 0, "start": 0, "end": 4,
        "quote": "Cd在", "page": 1, "quote_sha256": SHA, "id": "span:test",
    }
    return {
        "schema_version": "task-evidence-extraction-v2",
        "source": {"document_id": 100, "document_sha256": SHA,
                    "parse_version": SHA, "chunk_set_version": SHA},
        "provenance": {"origin": "test", "configuration_sha256": SHA},
        "studies": [{"local_id": "s1", "kind": "observational",
                      "context": [span], "attribution": None}],
        "entities": [
            {"local_id": "e_src", "study_id": "s1", "entity_type": "measure",
             "surface": "Cd在", "mention": span,
             "normalization": {"status": "unresolved", "canonical_id": None, "canonical_name": None}},
            {"local_id": "e_tgt", "study_id": "s1", "entity_type": "indicator",
             "surface": "Cd在", "mention": span,
             "normalization": {"status": "unresolved", "canonical_id": None, "canonical_name": None}},
        ],
        "relations": [{
            "id": "research:test", "local_id": "r1", "study_id": "s1",
            "relation_type": "reports_effect", "source_id": "e_src", "target_id": "e_tgt",
            "result": span, "direction": "increase",
            "qualifiers": {"dose": {"status": "unknown", "evidence": None}},
            "review_status": "pending", "semantic_support": "unreviewed",
        }],
        "review_status": "pending", "published_claims_added": 0,
        "rule_validation": "passed", "semantic_support": "unreviewed",
        "identity": "test-identity",
    }


def _setup(tmp_path, *, visibility="public", review=Document.REVIEW_APPROVED, file_hash=SHA):
    app = Flask("candidate-reader-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'reader.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    context = app.app_context()
    context.push()
    User.__table__.create(db.engine)
    Document.__table__.create(db.engine)
    ensure_knowledge_graph_platform_schema(db.engine)
    db.session.add(User(id=1, username="admin", password="x", role="admin"))
    db.session.add(Document(
        id=100, doc_name="paper.pdf", file_path="paper.pdf",
        file_type="pdf", chunk_count=1, status=Document.STATUS_COMPLETED,
        processing_stage="completed", review_status=review,
        visibility_scope=visibility, document_kind="academic_paper",
        file_hash=file_hash, create_by=1,
    ))
    db.session.commit()
    write_bundle(_bundle())


def test_normal_read_returns_pending_candidates(tmp_path):
    _setup(tmp_path)
    result = read_candidates(100)
    assert result["status"] == "ok"
    c = result["candidates"]
    assert len(c["studies"]) == 1
    assert len(c["entities"]) == 2
    assert len(c["relations"]) == 1
    assert len(c["claims"]) == 1
    assert all(s["review_status"] == "pending" for s in c["studies"])
    assert all(e["review_status"] == "pending" for e in c["entities"])
    assert all(r["review_status"] == "pending" for r in c["relations"])
    assert len(c["relations"][0]["evidence"]) == 1  # result evidence only


def test_non_public_source_rejected(tmp_path):
    _setup(tmp_path, visibility="private")
    result = read_candidates(100)
    assert result["status"] == "ineligible"
    assert result["candidates"] == {}


def test_unapproved_source_rejected(tmp_path):
    _setup(tmp_path, review=Document.REVIEW_PENDING)
    result = read_candidates(100)
    assert result["status"] == "ineligible"


def test_version_drift_returns_invalidated(tmp_path):
    _setup(tmp_path, file_hash="b" * 64)
    result = read_candidates(100)
    assert result["status"] == "invalidated"
    # Candidates are still returned so reviewers can see what drifted.
    assert len(result["candidates"]["relations"]) == 1
    assert result["job"]["content_sha256"] == SHA  # the old hash


def test_no_job_returns_not_found(tmp_path):
    _setup(tmp_path)
    # Add a second eligible document with no extraction job.
    db.session.add(Document(
        id=200, doc_name="paper2.pdf", file_path="paper2.pdf",
        file_type="pdf", chunk_count=1, status=Document.STATUS_COMPLETED,
        processing_stage="completed", review_status=Document.REVIEW_APPROVED,
        visibility_scope="public", document_kind="academic_paper",
        file_hash="c" * 64, create_by=1,
    ))
    db.session.commit()
    result = read_candidates(200)
    assert result["status"] == "not_found"
