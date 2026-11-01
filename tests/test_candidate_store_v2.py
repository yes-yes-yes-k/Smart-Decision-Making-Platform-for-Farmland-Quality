"""Unit tests for the R2.6b v2 candidate store."""
from __future__ import annotations

from flask import Flask

from framework.knowledge_graph.candidate_store import write_bundle
from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphClaimCandidate,
    KnowledgeGraphClaimEvidence,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphRelationCandidate,
    KnowledgeGraphStudyCandidate,
)
from framework.models.user import User, db
from scripts.migrate_knowledge_graph_platform import ensure_knowledge_graph_platform_schema


SHA = "a" * 64


def _bundle(*, with_qualifier: bool = True) -> dict:
    """A minimal v2 bundle: 1 study, 2 entities, 1 relation, 1 claim."""
    span = {
        "document_id": 100,
        "document_sha256": SHA,
        "parse_version": SHA,
        "chunk_set_version": SHA,
        "chunk_index": 0,
        "start": 0,
        "end": 4,
        "quote": "Cd在",
        "page": 1,
        "quote_sha256": SHA,
        "id": "span:test",
    }
    qualifier_evidence = span if with_qualifier else None
    return {
        "schema_version": "task-evidence-extraction-v2",
        "source": {
            "document_id": 100,
            "document_sha256": SHA,
            "parse_version": SHA,
            "chunk_set_version": SHA,
        },
        "provenance": {
            "origin": "R2.6b unit test",
            "configuration_sha256": SHA,
        },
        "studies": [
            {
                "local_id": "s1",
                "kind": "observational",
                "context": [span],
                "attribution": None,
            }
        ],
        "entities": [
            {
                "local_id": "e_src",
                "study_id": "s1",
                "entity_type": "measure",
                "surface": "Cd在",
                "mention": span,
                "normalization": {"status": "unresolved", "canonical_id": None, "canonical_name": None},
            },
            {
                "local_id": "e_tgt",
                "study_id": "s1",
                "entity_type": "indicator",
                "surface": "Cd在",
                "mention": span,
                "normalization": {"status": "unresolved", "canonical_id": None, "canonical_name": None},
            },
        ],
        "relations": [
            {
                "id": "research:test",
                "local_id": "r1",
                "study_id": "s1",
                "relation_type": "reports_effect",
                "source_id": "e_src",
                "target_id": "e_tgt",
                "result": span,
                "direction": "increase",
                "qualifiers": {
                    "soil_type": {"status": "source_selected", "evidence": qualifier_evidence} if with_qualifier else {"status": "unknown", "evidence": None},
                    "dose": {"status": "unknown", "evidence": None},
                },
                "review_status": "pending",
                "semantic_support": "unreviewed",
            }
        ],
        "review_status": "pending",
        "published_claims_added": 0,
        "rule_validation": "passed",
        "semantic_support": "unreviewed",
        "identity": "bundle-test-identity",
    }


def _setup(tmp_path):
    app = Flask("candidate-store-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'candidate.db'}",
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
        processing_stage="completed", review_status=Document.REVIEW_APPROVED,
        visibility_scope="public", document_kind="academic_paper",
        file_hash=SHA, create_by=1,
    ))
    db.session.commit()


def test_write_bundle_creates_candidates_with_correct_counts(tmp_path):
    _setup(tmp_path)
    summary = write_bundle(_bundle())
    assert summary == {
        "job": 1, "studies": 1, "entities": 2, "relations": 1,
        "relation_evidence": 2, "claims": 1, "claim_evidence": 1,
    }
    assert db.session.query(KnowledgeGraphExtractionJob).count() == 1
    assert db.session.query(KnowledgeGraphStudyCandidate).count() == 1
    assert db.session.query(KnowledgeGraphEntityCandidate).count() == 2
    assert db.session.query(KnowledgeGraphRelationCandidate).count() == 1
    assert db.session.query(KnowledgeGraphCandidateEvidence).count() == 2  # result + qualifier:soil_type
    assert db.session.query(KnowledgeGraphClaimCandidate).count() == 1
    assert db.session.query(KnowledgeGraphClaimEvidence).count() == 1


def test_all_candidates_are_pending(tmp_path):
    _setup(tmp_path)
    write_bundle(_bundle())
    for model in (
        KnowledgeGraphStudyCandidate, KnowledgeGraphEntityCandidate,
        KnowledgeGraphRelationCandidate, KnowledgeGraphCandidateEvidence,
        KnowledgeGraphClaimCandidate, KnowledgeGraphClaimEvidence,
    ):
        rows = db.session.query(model).all()
        assert rows, f"{model.__tablename__} should have rows"
        assert all(r.review_status == "pending" for r in rows), f"{model.__tablename__} has non-pending rows"


def test_relation_evidence_foreign_keys_are_correct(tmp_path):
    _setup(tmp_path)
    write_bundle(_bundle())
    rel = db.session.query(KnowledgeGraphRelationCandidate).one()
    src = db.session.query(KnowledgeGraphEntityCandidate).filter_by(candidate_key="e_src").one()
    tgt = db.session.query(KnowledgeGraphEntityCandidate).filter_by(candidate_key="e_tgt").one()
    assert rel.source_candidate_id == src.id
    assert rel.target_candidate_id == tgt.id
    ev_rows = db.session.query(KnowledgeGraphCandidateEvidence).filter_by(relation_candidate_id=rel.id).all()
    assert {e.evidence_key for e in ev_rows} == {"result", "qualifier:soil_type"}


def test_idempotent_rewrite_replaces_candidates(tmp_path):
    _setup(tmp_path)
    write_bundle(_bundle())
    first_job = db.session.query(KnowledgeGraphExtractionJob).one()
    # Rewrite with a bundle that drops the qualifier evidence.
    write_bundle(_bundle(with_qualifier=False))
    second_job = db.session.query(KnowledgeGraphExtractionJob).one()
    assert first_job.id == second_job.id  # same job, no duplicate
    assert db.session.query(KnowledgeGraphExtractionJob).count() == 1
    assert db.session.query(KnowledgeGraphStudyCandidate).count() == 1
    assert db.session.query(KnowledgeGraphEntityCandidate).count() == 2
    assert db.session.query(KnowledgeGraphRelationCandidate).count() == 1
    # Qualifier evidence gone, only result remains.
    assert db.session.query(KnowledgeGraphCandidateEvidence).count() == 1
    assert db.session.query(KnowledgeGraphClaimCandidate).count() == 1
    assert db.session.query(KnowledgeGraphClaimEvidence).count() == 1


def test_claim_links_to_relation_evidence(tmp_path):
    _setup(tmp_path)
    write_bundle(_bundle())
    claim = db.session.query(KnowledgeGraphClaimCandidate).one()
    assert claim.claim_type == "effect_direction"
    assert claim.statement == "increase"
    ev = db.session.query(KnowledgeGraphClaimEvidence).one()
    assert ev.claim_candidate_id == claim.id
    assert ev.evidence_key == "result"
    assert ev.is_active is True
