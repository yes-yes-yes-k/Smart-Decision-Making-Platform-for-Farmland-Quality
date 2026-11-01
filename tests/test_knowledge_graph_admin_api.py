import hashlib

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from framework.api.routes.docs import docs_bp
from framework.api.routes.knowledge_graph import knowledge_graph_bp
from framework.models.document import Document
from framework.models.document_label import DocumentLabel
from framework.models.ingestion import IngestionBatch, IngestionItem
from framework.models.knowledge_graph import (
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphClaimCandidate,
    KnowledgeGraphClaimEvidence,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphRelationCandidate,
    KnowledgeGraphRelease,
    KnowledgeGraphReleaseChange,
    KnowledgeGraphReviewDecision,
)
from framework.models.user import User, db
from framework.knowledge_graph.extraction_config import backend_config_digest
from scripts.migrate_knowledge_graph_platform import (
    ensure_knowledge_graph_platform_schema,
)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def graph_api(tmp_path):
    app = Flask("knowledge-graph-admin-api-test")
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'kg-admin.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY="knowledge-graph-test-secret-at-least-32-bytes",
    )
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(
        knowledge_graph_bp, url_prefix="/api/v1/knowledge-graph",
    )
    app.register_blueprint(docs_bp, url_prefix="/api/v1/docs")

    with app.app_context():
        User.__table__.create(db.engine)
        Document.__table__.create(db.engine)
        DocumentLabel.__table__.create(db.engine)
        IngestionBatch.__table__.create(db.engine)
        IngestionItem.__table__.create(db.engine)
        ensure_knowledge_graph_platform_schema(db.engine)

        admin = User(username="admin", password="x", role="admin", status=1)
        reviewer = User(
            username="reviewer", password="x", role="domain_reviewer", status=1,
        )
        reader = User(username="reader", password="x", role="user", status=1)
        db.session.add_all([admin, reviewer, reader])
        db.session.flush()
        document = Document(
            doc_name="paper.pdf", file_path="paper.pdf", file_type="pdf",
            file_size=100, chunk_count=2, status=Document.STATUS_COMPLETED,
            category="other", visibility_scope="public", file_hash="a" * 64,
            document_kind="academic_paper", processing_stage="completed",
            review_status=Document.REVIEW_APPROVED, create_by=reader.id,
        )
        db.session.add(document)
        db.session.flush()
        job = KnowledgeGraphExtractionJob(
            document_id=document.id, content_sha256=document.file_hash,
            schema_version="minimal-cultivated-land-kg-schema-v1",
            backend_name="microsoft-graphrag", extractor_version="3.3.0",
            backend_config_digest=backend_config_digest(
                "microsoft-graphrag", "3.3.0", "minimal-cultivated-land-kg-schema-v1"), state="dead_letter",
            attempt_count=5, failure_code="model_timeout",
            failure_message="secret provider stack trace /private/path",
            retryable=True,
        )
        db.session.add(job)
        db.session.flush()
        measure = KnowledgeGraphEntityCandidate(
            job_id=job.id, candidate_key="entity-measure", entity_type="measure",
            mention="秸秆还田", resolution_status="unresolved",
            risk_level="new_entity", review_status="pending", confidence=0.91,
        )
        obstacle = KnowledgeGraphEntityCandidate(
            job_id=job.id, candidate_key="entity-obstacle", entity_type="obstacle",
            mention="土壤板结", canonical_entity_id="obstacle:compaction",
            canonical_name="土壤板结", resolution_status="resolved",
            risk_level="resolved_entity", review_status="pending", confidence=0.95,
        )
        db.session.add_all([measure, obstacle])
        db.session.flush()
        relation = KnowledgeGraphRelationCandidate(
            job_id=job.id, candidate_key="relation-addresses",
            relation_type="addresses", source_candidate_id=measure.id,
            target_candidate_id=obstacle.id,
            canonical_target_id=obstacle.canonical_entity_id,
            risk_level="new_fact", validation_status="blocked",
            review_status="blocked", confidence=0.88,
        )
        claim = KnowledgeGraphClaimCandidate(
            job_id=job.id, candidate_key="claim-one", claim_type="observation",
            subject_candidate_id=obstacle.id,
            canonical_subject_id=obstacle.canonical_entity_id,
            statement="土壤板结会降低耕层通透性", risk_level="new_claim",
            validation_status="validated", review_status="pending", confidence=0.8,
        )
        db.session.add_all([relation, claim])
        db.session.flush()
        quote = "秸秆还田能够缓解土壤板结。"
        evidence = KnowledgeGraphCandidateEvidence(
            relation_candidate_id=relation.id, evidence_key="evidence-one",
            document_id=document.id, content_sha256=document.file_hash,
            chunk_index=1, page=3, span_start=12, span_end=26, quote=quote,
            quote_sha256=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
            schema_version=job.schema_version, backend_name=job.backend_name,
            extractor_version=job.extractor_version,
            validation_status="validated", review_status="pending", is_active=True,
        )
        db.session.add(evidence)
        db.session.commit()

        ids = {
            "document": document.id, "job": job.id, "measure": measure.id,
            "obstacle": obstacle.id, "relation": relation.id,
            "claim": claim.id, "evidence": evidence.id,
        }
        tokens = {
            role: create_access_token(identity=str(user.id))
            for role, user in {
                "admin": admin, "reviewer": reviewer, "reader": reader,
            }.items()
        }
    return app.test_client(), app, ids, tokens


def test_job_admin_endpoints_and_sanitized_document_substatus(graph_api):
    client, app, ids, tokens = graph_api
    assert client.get(
        "/api/v1/knowledge-graph/jobs", headers=_auth(tokens["reader"]),
    ).status_code == 403
    assert client.get(
        "/api/v1/knowledge-graph/jobs", headers=_auth(tokens["reviewer"]),
    ).status_code == 403

    response = client.get(
        "/api/v1/knowledge-graph/jobs?state=dead_letter"
        "&backend_name=microsoft-graphrag&extractor_version=3.3.0",
        headers=_auth(tokens["admin"]),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["total"] == 1
    detail = client.get(
        f"/api/v1/knowledge-graph/jobs/{ids['job']}",
        headers=_auth(tokens["admin"]),
    ).get_json()["data"]
    assert detail["candidate_counts"] == {
        "entities": 2, "relations": 1, "claims": 1,
    }
    assert "failure_message" not in detail

    status = client.get(
        f"/api/v1/docs/{ids['document']}/ingestion",
        headers=_auth(tokens["reader"]),
    )
    assert status.status_code == 200
    graph_status = status.get_json()["data"]["knowledge_graph"]
    assert graph_status == {
        "state": "dead_letter", "latest_job_id": ids["job"],
        "schema_version": "minimal-cultivated-land-kg-schema-v1",
        "backend_name": "microsoft-graphrag", "extractor_version": "3.3.0",
        "retryable": True, "failure_code": "model_timeout",
    }
    assert "secret provider" not in str(graph_status)

    retried = client.post(
        f"/api/v1/knowledge-graph/jobs/{ids['job']}/retry",
        headers=_auth(tokens["admin"]),
    )
    assert retried.status_code == 202
    assert retried.get_json()["data"]["state"] == "pending"
    rerun = client.post(
        f"/api/v1/knowledge-graph/documents/{ids['document']}/rerun",
        json={}, headers=_auth(tokens["admin"]),
    )
    assert rerun.status_code == 202
    assert rerun.get_json()["created"] is False

    with app.app_context():
        assert KnowledgeGraphExtractionJob.query.count() == 1


def test_rerun_does_not_replace_candidate_provenance_or_running_job(graph_api):
    client, app, ids, tokens = graph_api
    url = f"/api/v1/knowledge-graph/documents/{ids['document']}/rerun"
    response = client.post(url, json={"backend_config_digest": "c" * 64}, headers=_auth(tokens["admin"]))
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "backend_config_conflict"
    with app.app_context():
        job = db.session.get(KnowledgeGraphExtractionJob, ids["job"])
        original = job.backend_config_digest
        job.state = "running"
        db.session.commit()
    response = client.post(url, json={}, headers=_auth(tokens["admin"]))
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "job_running"
    with app.app_context():
        assert db.session.get(KnowledgeGraphExtractionJob, ids["job"]).backend_config_digest == original


def test_candidate_filters_and_evidence_detail_are_available_to_reviewer(graph_api):
    client, _, ids, tokens = graph_api
    response = client.get(
        "/api/v1/knowledge-graph/candidates"
        f"?kind=relation&review_status=blocked&risk_level=new_fact"
        f"&relation_type=addresses&document_id={ids['document']}",
        headers=_auth(tokens["reviewer"]),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["total"] == 1
    detail = client.get(
        f"/api/v1/knowledge-graph/candidates/relation/{ids['relation']}",
        headers=_auth(tokens["reviewer"]),
    ).get_json()["data"]
    assert detail["evidence"][0]["quote"] == "秸秆还田能够缓解土壤板结。"
    assert detail["evidence"][0]["page"] == 3
    assert detail["evidence"][0]["span_start"] == 12
    evidence = client.get(
        f"/api/v1/knowledge-graph/evidence/relation/{ids['evidence']}",
        headers=_auth(tokens["reviewer"]),
    )
    assert evidence.status_code == 200
    assert evidence.get_json()["data"]["chunk_index"] == 1


def test_review_flow_enforces_gates_and_writes_idempotent_immutable_audit(graph_api):
    client, app, ids, tokens = graph_api
    headers = _auth(tokens["reviewer"])

    early = client.post(
        f"/api/v1/knowledge-graph/candidates/relation/{ids['relation']}/review",
        json={"decision": "approve", "reason": "证据充分", "idempotency_key": "early"},
        headers=headers,
    )
    assert early.status_code == 409
    assert early.get_json()["error_code"] == "candidate_not_validated"

    resolution_payload = {
        "canonical_id": "measure:straw-returning",
        "canonical_name": "秸秆还田",
        "reason": "确认是新的治理措施实体",
        "idempotency_key": "resolve-measure-v1",
    }
    resolved = client.post(
        f"/api/v1/knowledge-graph/entities/{ids['measure']}/resolve",
        json=resolution_payload, headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["replayed"] is False
    replay = client.post(
        f"/api/v1/knowledge-graph/entities/{ids['measure']}/resolve",
        json=resolution_payload, headers=headers,
    )
    assert replay.status_code == 200
    assert replay.get_json()["data"]["replayed"] is True

    conflict = client.post(
        f"/api/v1/knowledge-graph/candidates/entity/{ids['obstacle']}/review",
        json={
            "decision": "approve", "reason": "误用幂等键",
            "idempotency_key": "resolve-measure-v1",
        }, headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["error_code"] == "idempotency_key_conflict"

    for entity_id, key in (
        (ids["measure"], "approve-measure"),
        (ids["obstacle"], "approve-obstacle"),
    ):
        response = client.post(
            f"/api/v1/knowledge-graph/candidates/entity/{entity_id}/review",
            json={"decision": "approve", "reason": "实体已核验", "idempotency_key": key},
            headers=headers,
        )
        assert response.status_code == 200

    evidence = client.post(
        f"/api/v1/knowledge-graph/evidence/relation/{ids['evidence']}/review",
        json={"decision": "approve", "reason": "原文定位有效", "idempotency_key": "approve-evidence"},
        headers=headers,
    )
    assert evidence.status_code == 200
    relation = client.post(
        f"/api/v1/knowledge-graph/candidates/relation/{ids['relation']}/review",
        json={"decision": "approve", "reason": "端点和证据均通过", "idempotency_key": "approve-relation"},
        headers=headers,
    )
    assert relation.status_code == 200
    assert relation.get_json()["data"]["candidate"]["review_status"] == "approved"

    rejected = client.post(
        f"/api/v1/knowledge-graph/candidates/claim/{ids['claim']}/review",
        json={"decision": "reject", "reason": "表述过于宽泛", "idempotency_key": "reject-claim"},
        headers=headers,
    )
    assert rejected.status_code == 200
    assert rejected.get_json()["data"]["candidate"]["review_status"] == "rejected"

    with app.app_context():
        audits = KnowledgeGraphReviewDecision.query.order_by(
            KnowledgeGraphReviewDecision.id,
        ).all()
        assert len(audits) == 6
        assert audits[0].reviewed_value["before"]["canonical_entity_id"] is None
        assert audits[0].reviewed_value["after"]["canonical_entity_id"] == (
            "measure:straw-returning"
        )


def test_direct_production_edge_write_is_forbidden(graph_api):
    client, app, _, tokens = graph_api
    response = client.post(
        "/api/v1/knowledge-graph/production-relations",
        json={"relation_type": "addresses"}, headers=_auth(tokens["reviewer"]),
    )
    assert response.status_code == 405
    assert response.get_json()["error_code"] == "direct_production_write_forbidden"
    assert client.post(
        "/api/v1/knowledge-graph/production-relations",
        json={}, headers=_auth(tokens["reader"]),
    ).status_code == 403
    with app.app_context():
        assert KnowledgeGraphRelease.query.count() == 0
        assert KnowledgeGraphReleaseChange.query.count() == 0


def test_release_api_is_admin_only_and_graph_query_degrades_safely(graph_api):
    client, app, _, tokens = graph_api
    app.extensions["knowledge_graph_store"] = None
    assert client.get(
        "/api/v1/knowledge-graph/releases/preview",
        headers=_auth(tokens["reviewer"]),
    ).status_code == 403
    unavailable = client.get(
        "/api/v1/knowledge-graph/releases/preview",
        headers=_auth(tokens["admin"]),
    )
    assert unavailable.status_code == 503
    assert unavailable.get_json()["error_code"] == "graph_store_unavailable"
    assert client.post(
        "/api/v1/knowledge-graph/releases",
        json={"release_id": "unauthorized"},
        headers=_auth(tokens["reviewer"]),
    ).status_code == 403
    assert client.post(
        "/api/v1/knowledge-graph/releases/release-1/rollback",
        json={"reason": "x", "idempotency_key": "x"},
        headers=_auth(tokens["reviewer"]),
    ).status_code == 403
    query = client.post(
        "/api/v1/knowledge-graph/query",
        json={"entity_ids": ["measure:straw-returning"]},
        headers=_auth(tokens["reader"]),
    )
    assert query.status_code == 200
    assert query.get_json()["data"]["failure_code"] == "graph_query_unavailable"
