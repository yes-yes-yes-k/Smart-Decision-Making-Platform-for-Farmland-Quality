from dataclasses import replace

from flask import Flask
import pytest

from framework.knowledge_graph.candidate_pipeline import (
    CandidatePipeline,
    CandidatePipelineError,
    CanonicalEntityCatalog,
    ExtractionInputBuilder,
)
from framework.knowledge_graph.contracts import (
    ClaimCandidate,
    EntityCandidate,
    EvidenceReference,
    ExtractionResult,
    RelationCandidate,
    SourceChunk,
    sha256_text,
    stable_digest,
)
from framework.knowledge_graph.schema import load_graph_schema
from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphClaimCandidate,
    KnowledgeGraphClaimEvidence,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphRelationCandidate,
)
from framework.models.user import db


HASH_A = "a" * 64
HASH_B = "b" * 64
BACKEND_CONFIG = stable_digest({"model": "fixture"})
CONTENT = "秸秆还田可以缓解土壤板结，并改善土壤有机质。"


class StaticChunkReader:
    def __init__(self, rows):
        self.rows = rows

    def read_published_chunks(self, **_kwargs):
        return self.rows


def _app(tmp_path):
    app = Flask("knowledge-graph-candidate-pipeline-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'kg-candidates.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    return app


def _catalog(*, fuzzy_threshold=0.86):
    base = CanonicalEntityCatalog.from_mapping({
        "entities": [
            {
                "id": "measure:straw_return",
                "type": "measure",
                "name": "秸秆还田",
                "aliases": ["秸秆直接还田"],
            },
            {
                "id": "obstacle:compaction",
                "type": "obstacle",
                "name": "土壤板结",
                "aliases": ["耕层板结"],
            },
            {
                "id": "indicator:organic_matter",
                "type": "indicator",
                "name": "土壤有机质",
                "aliases": ["有机质"],
            },
            {
                "id": "standard:gb33469",
                "type": "standard",
                "name": "耕地质量等级 GB/T 33469-2016",
                "aliases": ["GB/T 33469", "GB/T 33469-2016"],
            },
        ],
        "relations": [{
            "type": "addresses",
            "source": "measure:straw_return",
            "target": "obstacle:compaction",
        }],
    })
    return CanonicalEntityCatalog(
        base.entities,
        base.production_relations,
        fuzzy_threshold=fuzzy_threshold,
    )


def _document(document_id, content_hash):
    return Document(
        id=document_id,
        doc_name=f"paper-{document_id}.pdf",
        file_path=f"paper-{document_id}.pdf",
        file_type="pdf",
        file_size=100,
        chunk_count=1,
        status=Document.STATUS_COMPLETED,
        category="other",
        visibility_scope="public",
        file_hash=content_hash,
        document_kind="academic_paper",
        processing_stage="completed",
        review_status=Document.REVIEW_APPROVED,
        create_by=7,
    )


def _job(document_id, content_hash):
    return KnowledgeGraphExtractionJob(
        document_id=document_id,
        content_sha256=content_hash,
        schema_version=load_graph_schema().schema_version,
        backend_name="fixture-backend",
        extractor_version="1.0",
        backend_config_digest=BACKEND_CONFIG,
    )


def _rows(document_id, content_hash, *, content=CONTENT, **metadata_overrides):
    metadata = {
        "document_id": document_id,
        "content_sha256": content_hash,
        "chunk_index": 0,
        "page": 7,
        "visibility_scope": "public",
    }
    metadata.update(metadata_overrides)
    return [{"content": content, "metadata": metadata}]


def _setup(tmp_path, *, with_second_document=False):
    app = _app(tmp_path)
    context = app.app_context()
    context.push()
    for model in (
        Document,
        KnowledgeGraphExtractionJob,
        KnowledgeGraphEntityCandidate,
        KnowledgeGraphRelationCandidate,
        KnowledgeGraphClaimCandidate,
        KnowledgeGraphCandidateEvidence,
        KnowledgeGraphClaimEvidence,
    ):
        model.__table__.create(bind=db.engine, checkfirst=True)
    first = _document(1, HASH_A)
    db.session.add(first)
    if with_second_document:
        db.session.add(_document(2, HASH_B))
    db.session.flush()
    first_job = _job(1, HASH_A)
    db.session.add(first_job)
    db.session.commit()
    return context, first_job


def _request(job, *, content=CONTENT, page=7):
    return ExtractionInputBuilder(
        db.session,
        StaticChunkReader(_rows(job.document_id, job.content_sha256, content=content, page=page)),
    ).build(job)


def _entities():
    return (
        EntityCandidate("e-measure", "measure", "秸秆直接还田", confidence=0.94),
        EntityCandidate("e-obstacle", "obstacle", "耕层板结", confidence=0.91),
    )


def _result(job, request, *, entities=None, relations=(), claims=()):
    return ExtractionResult(
        backend_name=job.backend_name,
        backend_version=job.extractor_version,
        backend_config_digest=job.backend_config_digest,
        schema_version=job.schema_version,
        request_key=request.request_key,
        entities=tuple(_entities() if entities is None else entities),
        relations=tuple(relations),
        claims=tuple(claims),
        raw_output_fingerprint=stable_digest({
            "document": job.document_id,
            "relations": [item.candidate_id for item in relations],
            "claims": [item.candidate_id for item in claims],
        }),
    )


def _address_evidence(request):
    chunk = request.chunks[0]
    start = chunk.content.index("秸秆还田")
    end = chunk.content.index("土壤板结") + len("土壤板结")
    return EvidenceReference.from_chunk(chunk, start, end)


def test_input_builder_reads_only_published_page_aware_current_chunks(tmp_path):
    context, job = _setup(tmp_path)
    try:
        request = _request(job)
        assert request.document_id == 1
        assert request.chunks[0].page == 7
        assert request.chunks[0].content_sha256 == HASH_A

        private_reader = StaticChunkReader(_rows(1, HASH_A, visibility_scope="private"))
        with pytest.raises(CandidatePipelineError) as private_error:
            ExtractionInputBuilder(db.session, private_reader).build(job)
        assert private_error.value.code == "source_not_published"

        stale_reader = StaticChunkReader(_rows(1, HASH_B))
        with pytest.raises(CandidatePipelineError) as stale_error:
            ExtractionInputBuilder(db.session, stale_reader).build(job)
        assert stale_error.value.code == "stale_chunk_hash"

        page_reader = StaticChunkReader(_rows(1, HASH_A, page=None))
        with pytest.raises(CandidatePipelineError) as page_error:
            ExtractionInputBuilder(db.session, page_reader).build(job)
        assert page_error.value.code == "invalid_chunk_locator"
    finally:
        db.session.remove()
        context.pop()


def test_pipeline_rechecks_source_status_after_input_was_built(tmp_path):
    context, job = _setup(tmp_path)
    try:
        request = _request(job)
        document = db.session.get(Document, job.document_id)
        document.visibility_scope = "private"
        db.session.flush()

        with pytest.raises(CandidatePipelineError) as error:
            CandidatePipeline(db.session, catalog=_catalog()).process(
                job, request, _result(job, request),
            )
        assert error.value.code == "source_not_published"
    finally:
        db.session.remove()
        context.pop()


def test_catalog_resolves_alias_and_standard_number_but_blocks_fuzzy_and_broad_terms():
    catalog = _catalog(fuzzy_threshold=0.70)
    alias = catalog.resolve(EntityCandidate("1", "obstacle", "耕层板结"))
    standard = catalog.resolve(EntityCandidate("2", "standard", "GB／T 33469－2016"))
    fuzzy = catalog.resolve(EntityCandidate("3", "obstacle", "土壤板洁"))
    broad = catalog.resolve(EntityCandidate("4", "indicator", "土壤"))

    assert (alias.status, alias.canonical_id) == ("resolved", "obstacle:compaction")
    assert (standard.status, standard.canonical_id) == ("resolved", "standard:gb33469")
    assert fuzzy.status == "needs_entity_resolution"
    assert fuzzy.canonical_id is None
    assert fuzzy.suggestions == ("obstacle:compaction",)
    assert (broad.status, broad.risk_level) == ("rejected", "too_broad")


def test_backend_result_becomes_reviewable_entity_relation_claim_and_evidence(tmp_path):
    context, job = _setup(tmp_path)
    try:
        request = _request(job)
        evidence = _address_evidence(request)
        relation = RelationCandidate(
            "r-address", "addresses", "e-measure", "e-obstacle", (evidence,), 0.93,
        )
        claim = ClaimCandidate(
            "c-address", "causal_statement", "e-measure",
            "秸秆还田可以缓解土壤板结", (evidence,), "e-obstacle", 0.89,
        )

        report = CandidatePipeline(db.session, catalog=_catalog()).process(
            job, request, _result(job, request, relations=(relation,), claims=(claim,)),
        )
        db.session.commit()

        assert report.passed
        assert (report.entity_candidates, report.relation_candidates) == (2, 1)
        assert (report.claim_candidates, report.evidence_records) == (1, 2)
        relation_row = KnowledgeGraphRelationCandidate.query.one()
        assert relation_row.validation_status == "validated"
        assert relation_row.review_status == "pending"
        assert relation_row.risk_level == "evidence_append"
        assert relation_row.support_document_count == 1
        assert KnowledgeGraphClaimCandidate.query.one().validation_status == "validated"
        assert KnowledgeGraphCandidateEvidence.query.one().evidence_key == evidence.evidence_id
        assert KnowledgeGraphClaimEvidence.query.one().evidence_key == evidence.evidence_id
    finally:
        db.session.remove()
        context.pop()


def test_relation_triple_merges_cross_document_evidence_and_deduplicates_replay(tmp_path):
    context, first_job = _setup(tmp_path, with_second_document=True)
    try:
        pipeline = CandidatePipeline(db.session, catalog=_catalog())
        first_request = _request(first_job)
        first_evidence = _address_evidence(first_request)
        relation = RelationCandidate(
            "r-address", "addresses", "e-measure", "e-obstacle", (first_evidence,), 0.9,
        )
        pipeline.process(first_job, first_request, _result(
            first_job, first_request, relations=(relation,),
        ))

        second_job = _job(2, HASH_B)
        db.session.add(second_job)
        db.session.flush()
        second_request = _request(second_job)
        second_evidence = _address_evidence(second_request)
        second_relation = replace(relation, evidence=(second_evidence,))
        second_result = _result(second_job, second_request, relations=(second_relation,))
        merged = pipeline.process(second_job, second_request, second_result)
        replayed = pipeline.process(second_job, second_request, second_result)
        db.session.commit()

        assert merged.merged_relations == 1
        assert replayed.evidence_records == 0
        assert KnowledgeGraphRelationCandidate.query.count() == 1
        assert KnowledgeGraphCandidateEvidence.query.count() == 2
        row = KnowledgeGraphRelationCandidate.query.one()
        assert row.support_document_count == 2
        assert {e.evidence_key for e in KnowledgeGraphCandidateEvidence.query.all()} == {
            first_evidence.evidence_id, second_evidence.evidence_id,
        }
    finally:
        db.session.remove()
        context.pop()


def test_cooccurrence_does_not_create_a_relation_and_broad_concept_is_rejected(tmp_path):
    context, job = _setup(tmp_path)
    try:
        request = _request(job)
        entities = (*_entities(), EntityCandidate("e-broad", "indicator", "土壤", confidence=0.9))
        report = CandidatePipeline(db.session, catalog=_catalog()).process(
            job, request, _result(job, request, entities=entities),
        )
        db.session.commit()

        assert KnowledgeGraphRelationCandidate.query.count() == 0
        broad = KnowledgeGraphEntityCandidate.query.filter_by(candidate_key="e-broad").one()
        assert (broad.resolution_status, broad.review_status) == ("rejected", "not_reviewable")
        assert "concept_too_broad" in {issue.code for issue in report.issues}
    finally:
        db.session.remove()
        context.pop()


def test_reversed_direction_is_rejected_before_evidence_review(tmp_path):
    context, job = _setup(tmp_path)
    try:
        request = _request(job)
        evidence = _address_evidence(request)
        reversed_relation = RelationCandidate(
            "r-reversed", "addresses", "e-obstacle", "e-measure", (evidence,), 0.99,
        )
        report = CandidatePipeline(db.session, catalog=_catalog()).process(
            job, request, _result(job, request, relations=(reversed_relation,)),
        )
        db.session.commit()

        row = KnowledgeGraphRelationCandidate.query.one()
        assert (row.validation_status, row.review_status) == ("rejected", "not_reviewable")
        assert KnowledgeGraphCandidateEvidence.query.count() == 0
        assert "schema_direction" in {issue.code for issue in report.issues}
    finally:
        db.session.remove()
        context.pop()


def test_fabricated_quote_is_rejected_before_evidence_persistence(tmp_path):
    context, job = _setup(tmp_path)
    try:
        request = _request(job)
        valid = _address_evidence(request)
        fabricated_quote = "伪造的证据文本"
        fabricated = EvidenceReference(
            evidence_id=valid.evidence_id,
            document_id=valid.document_id,
            content_sha256=valid.content_sha256,
            chunk_index=valid.chunk_index,
            page=valid.page,
            span_start=valid.span_start,
            span_end=valid.span_end,
            quote=fabricated_quote,
            quote_sha256=sha256_text(fabricated_quote),
        )
        relation = RelationCandidate(
            "r-fabricated", "addresses", "e-measure", "e-obstacle", (fabricated,), 0.95,
        )
        report = CandidatePipeline(db.session, catalog=_catalog()).process(
            job, request, _result(job, request, relations=(relation,)),
        )
        db.session.commit()

        assert KnowledgeGraphCandidateEvidence.query.count() == 0
        assert KnowledgeGraphRelationCandidate.query.one().validation_status == "rejected"
        assert "quote_mismatch" in {issue.code for issue in report.issues}
    finally:
        db.session.remove()
        context.pop()


def test_conflicting_evidence_identity_is_rejected_and_original_is_retained(tmp_path):
    context, job = _setup(tmp_path)
    try:
        request = _request(job)
        chunk: SourceChunk = request.chunks[0]
        first = EvidenceReference.from_chunk(chunk, 0, len("秸秆还田"))
        other = EvidenceReference.from_chunk(
            chunk, chunk.content.index("土壤板结"),
            chunk.content.index("土壤板结") + len("土壤板结"),
        )
        conflicting = replace(other, evidence_id=first.evidence_id)
        relations = (
            RelationCandidate(
                "r-first", "addresses", "e-measure", "e-obstacle", (first,), 0.9,
            ),
            RelationCandidate(
                "r-conflict", "addresses", "e-measure", "e-obstacle", (conflicting,), 0.9,
            ),
        )
        report = CandidatePipeline(db.session, catalog=_catalog()).process(
            job, request, _result(job, request, relations=relations),
        )
        db.session.commit()

        assert KnowledgeGraphCandidateEvidence.query.count() == 1
        assert KnowledgeGraphCandidateEvidence.query.one().quote == "秸秆还田"
        rejected = KnowledgeGraphRelationCandidate.query.filter_by(
            candidate_key="r-conflict",
        ).one()
        assert rejected.validation_status == "rejected"
        assert "evidence_identity_conflict" in {issue.code for issue in report.issues}
    finally:
        db.session.remove()
        context.pop()

