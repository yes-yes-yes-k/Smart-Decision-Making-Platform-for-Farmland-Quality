import hashlib

from flask import Flask

from framework.knowledge_graph.backfill import HistoricalGraphBackfill
from framework.knowledge_graph.evidence_lifecycle import invalidate_document_evidence
from framework.knowledge_graph.query import SafeGraphQueryService
from framework.knowledge_graph.stores import JsonGraphStore
from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphBackfillRun,
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphOutboxEvent,
    KnowledgeGraphRelationCandidate,
    KnowledgeGraphRelationRetirementCandidate,
)
from framework.models.user import User, db
from scripts.migrate_knowledge_graph_platform import ensure_knowledge_graph_platform_schema


def _document(doc_id, *, eligible=True):
    return Document(
        id=doc_id, doc_name=f"paper-{doc_id}.pdf", file_path=f"{doc_id}.pdf",
        file_type="pdf", chunk_count=2 if eligible else 0,
        status=Document.STATUS_COMPLETED if eligible else Document.STATUS_PENDING,
        processing_stage="completed" if eligible else "accepted",
        review_status=Document.REVIEW_APPROVED,
        visibility_scope="public", document_kind="academic_paper",
        file_hash=(str(doc_id) * 64)[:64], create_by=1,
    )


def _setup(tmp_path):
    app = Flask("kg-evidence-lifecycle-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'lifecycle.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    context = app.app_context()
    context.push()
    User.__table__.create(db.engine)
    Document.__table__.create(db.engine)
    ensure_knowledge_graph_platform_schema(db.engine)
    db.session.add(User(id=1, username="admin", password="x", role="admin"))
    doc1, doc2 = _document(1), _document(2)
    db.session.add_all([doc1, doc2])
    db.session.flush()
    job = KnowledgeGraphExtractionJob(
        document_id=1, content_sha256=doc1.file_hash,
        schema_version="minimal-cultivated-land-kg-schema-v1",
        backend_name="stub", extractor_version="1", backend_config_digest="b" * 64,
        state="completed",
    )
    db.session.add(job)
    db.session.flush()
    source = KnowledgeGraphEntityCandidate(
        job_id=job.id, candidate_key="s", entity_type="measure", mention="措施",
        canonical_entity_id="measure:m", canonical_name="措施",
        resolution_status="resolved", review_status="approved", confidence=1,
    )
    target = KnowledgeGraphEntityCandidate(
        job_id=job.id, candidate_key="t", entity_type="obstacle", mention="障碍",
        canonical_entity_id="obstacle:o", canonical_name="障碍",
        resolution_status="resolved", review_status="approved", confidence=1,
    )
    db.session.add_all([source, target])
    db.session.flush()
    relation = KnowledgeGraphRelationCandidate(
        job_id=job.id, candidate_key="r", relation_type="addresses",
        source_candidate_id=source.id, target_candidate_id=target.id,
        canonical_source_id=source.canonical_entity_id,
        canonical_target_id=target.canonical_entity_id,
        validation_status="validated", review_status="approved",
        support_document_count=2, confidence=1,
    )
    db.session.add(relation)
    db.session.flush()
    for document in (doc1, doc2):
        quote = f"document {document.id} evidence"
        db.session.add(KnowledgeGraphCandidateEvidence(
            relation_candidate_id=relation.id,
            evidence_key=f"evidence-{document.id}", document_id=document.id,
            content_sha256=document.file_hash, chunk_index=0, page=1,
            span_start=0, span_end=len(quote), quote=quote,
            quote_sha256=hashlib.sha256(quote.encode()).hexdigest(),
            schema_version=job.schema_version, backend_name="stub",
            extractor_version="1", validation_status="validated",
            review_status="approved", is_active=True,
        ))
    db.session.commit()
    return context, relation


def test_withdrawing_one_support_keeps_relation_then_last_creates_one_retirement(tmp_path):
    context, relation = _setup(tmp_path)
    try:
        first = invalidate_document_evidence(
            db.session, document_id=1, reason="document_withdrawn",
        )
        db.session.commit()
        assert first["relation_evidence_invalidated"] == 1
        assert first["retirement_candidates_created"] == 0
        assert relation.support_document_count == 1
        assert KnowledgeGraphRelationRetirementCandidate.query.count() == 0
        assert KnowledgeGraphCandidateEvidence.query.filter_by(
            document_id=2, is_active=True,
        ).count() == 1

        graph = {
            "schema_version": "minimal-cultivated-land-kg-schema-v1",
            "release": {"release_id": "production"},
            "entities": [
                {"id": "measure:m", "type": "measure", "name": "措施"},
                {"id": "obstacle:o", "type": "obstacle", "name": "障碍"},
            ],
            "relations": [{
                "id": "r", "type": "addresses", "source": "measure:m",
                "target": "obstacle:o", "evidence": [
                    {"evidence_id": "evidence-1", "document_id": 1},
                    {"evidence_id": "evidence-2", "document_id": 2},
                ],
            }],
        }

        class PublishedChunks:
            def get_by_references(self, references, **_):
                active_ids = {
                    row.document_id for row in KnowledgeGraphCandidateEvidence.query.filter_by(
                        is_active=True,
                    ).all()
                }
                return [
                    {"content": f"doc-{item['document_id']}", "metadata": item}
                    for item in references if item.get("document_id") in active_ids
                ]

        production = SafeGraphQueryService(
            JsonGraphStore(graph), PublishedChunks(),
        ).query(entity_ids=("measure:m",), top_k=10)
        assert [item["content"] for item in production["evidence"]] == ["doc-2"]

        second = invalidate_document_evidence(
            db.session, document_id=2, reason="document_withdrawn",
        )
        duplicate = invalidate_document_evidence(
            db.session, document_id=2, reason="document_withdrawn",
        )
        db.session.commit()
        assert second["retirement_candidates_created"] == 1
        assert duplicate["retirement_candidates_created"] == 0
        assert relation.support_document_count == 0
        retirement = KnowledgeGraphRelationRetirementCandidate.query.one()
        assert retirement.relation_key == "addresses|measure:m|obstacle:o"
        assert retirement.review_status == "pending"
    finally:
        db.session.remove()
        context.pop()


def test_reparse_invalidates_only_evidence_from_old_content_hash(tmp_path):
    context, relation = _setup(tmp_path)
    try:
        evidence = KnowledgeGraphCandidateEvidence.query.filter_by(document_id=1).one()
        evidence.content_sha256 = "old" * 21 + "o"
        db.session.commit()
        report = invalidate_document_evidence(
            db.session, document_id=1, keep_content_sha256="1" * 64,
            reason="document_content_reparsed",
        )
        db.session.commit()
        assert report["relation_evidence_invalidated"] == 1
        assert relation.support_document_count == 1
        assert KnowledgeGraphCandidateEvidence.query.filter_by(
            document_id=2, is_active=True,
        ).count() == 1
    finally:
        db.session.remove()
        context.pop()


def test_historical_backfill_dry_run_checkpoint_resume_and_idempotency(tmp_path):
    app = Flask("kg-backfill-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'backfill.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        User.__table__.create(db.engine)
        Document.__table__.create(db.engine)
        ensure_knowledge_graph_platform_schema(db.engine)
        db.session.add(User(id=1, username="admin", password="x", role="admin"))
        db.session.add_all([_document(1), _document(2, eligible=False), _document(3)])
        db.session.commit()
        service = HistoricalGraphBackfill(db.session)
        dry = service.dry_run(limit=10)
        assert dry["eligible_document_ids"] == [1, 3]
        assert KnowledgeGraphBackfillRun.query.count() == 0
        assert KnowledgeGraphOutboxEvent.query.count() == 0

        run, first = service.run_batch(run_key="corpus-v1", created_by=1, batch_size=2)
        db.session.commit()
        assert first == {"selected": 2, "created": 1, "reused": 0, "skipped": 1}
        assert run.checkpoint_document_id == 2
        run, second = service.run_batch(run_key="corpus-v1", created_by=1, batch_size=2)
        db.session.commit()
        assert second["created"] == 1
        assert run.state == "completed"
        run, replay = service.run_batch(run_key="corpus-v1", created_by=1, batch_size=2)
        assert replay["selected"] == 0
        assert KnowledgeGraphOutboxEvent.query.count() == 2
