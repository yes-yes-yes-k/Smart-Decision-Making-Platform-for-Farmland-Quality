import hashlib
import json

from flask import Flask

from framework.knowledge_graph.contracts import GraphQuery, GraphQueryResult
from framework.knowledge_graph.query import SafeGraphQueryService
from framework.knowledge_graph.release_platform import (
    KnowledgeGraphReleaseService,
    ReleaseAuditExporter,
    ReleaseError,
)
from framework.knowledge_graph.stores import JsonGraphStore
from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphAuditExport,
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphControl,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphRelationCandidate,
    KnowledgeGraphRelease,
    KnowledgeGraphReleaseChange,
    KnowledgeGraphRollbackAudit,
)
from framework.models.user import User, db
from scripts.migrate_knowledge_graph_platform import (
    ensure_knowledge_graph_platform_schema,
)


class MemoryVersionedGraphStore:
    def __init__(self):
        self.releases = {}
        self.snapshots = {}
        self.active = None
        self.closed_relations = []
        self.fail_health_for = None

    def upsert_release(self, **values):
        self.releases[values["release_id"]] = dict(values)
        parent = self.active
        if values["release_id"] not in self.snapshots:
            base = self.snapshots.get(parent, {"entities": [], "relations": []})
            self.snapshots[values["release_id"]] = json.loads(json.dumps(base))
        self.snapshots[values["release_id"]]["schema_version"] = values["schema_version"]
        self.snapshots[values["release_id"]]["release"] = {
            "release_id": values["release_id"], "sequence": values["sequence"],
        }

    def upsert_entity(self, entity, *, valid_from_release, **_):
        snapshot = self.snapshots[valid_from_release]
        rows = {item["id"]: item for item in snapshot["entities"]}
        rows[entity["id"]] = json.loads(json.dumps(entity))
        snapshot["entities"] = [rows[key] for key in sorted(rows)]

    @staticmethod
    def _key(relation):
        return f"{relation['type']}|{relation['source']}|{relation['target']}"

    def upsert_relation(self, relation, *, valid_from_release, **_):
        snapshot = self.snapshots[valid_from_release]
        rows = {self._key(item): item for item in snapshot["relations"]}
        rows[self._key(relation)] = json.loads(json.dumps(relation))
        snapshot["relations"] = [rows[key] for key in sorted(rows)]

    def close_relation(self, relation_key, **values):
        self.closed_relations.append((relation_key, values))

    def activate_release(self, release_id):
        if not self.releases.get(release_id, {}).get("validated"):
            raise ValueError("release is not validated")
        self.active = release_id

    def active_release(self):
        return self.active

    def health(self):
        return {
            "ready": self.active is not None and self.active != self.fail_health_for,
            "active_release": self.active,
        }

    def export_snapshot(self, release_id):
        return json.loads(json.dumps(self.snapshots[release_id]))


def _setup(tmp_path):
    app = Flask("knowledge-graph-release-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'kg-release.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    context = app.app_context()
    context.push()
    User.__table__.create(db.engine)
    Document.__table__.create(db.engine)
    ensure_knowledge_graph_platform_schema(db.engine)
    admin = User(username="admin", password="x", role="admin", status=1)
    db.session.add(admin)
    db.session.flush()
    document = Document(
        doc_name="paper.pdf", file_path="paper.pdf", file_type="pdf",
        chunk_count=2, status=Document.STATUS_COMPLETED,
        processing_stage="completed", review_status=Document.REVIEW_APPROVED,
        visibility_scope="public", document_kind="academic_paper",
        file_hash="a" * 64, create_by=admin.id,
    )
    db.session.add(document)
    db.session.flush()
    job = KnowledgeGraphExtractionJob(
        document_id=document.id, content_sha256=document.file_hash,
        schema_version="minimal-cultivated-land-kg-schema-v1",
        backend_name="stub", extractor_version="1", backend_config_digest="b" * 64,
        state="completed",
    )
    db.session.add(job)
    db.session.flush()
    source = KnowledgeGraphEntityCandidate(
        job_id=job.id, candidate_key="source", entity_type="measure",
        mention="秸秆还田", canonical_entity_id="measure:straw-returning",
        canonical_name="秸秆还田", resolution_status="resolved",
        risk_level="new_entity", review_status="approved", confidence=1,
    )
    target = KnowledgeGraphEntityCandidate(
        job_id=job.id, candidate_key="target", entity_type="obstacle",
        mention="板结", canonical_entity_id="obstacle:compaction",
        canonical_name="土壤板结", resolution_status="resolved",
        risk_level="new_entity", review_status="approved", confidence=1,
    )
    db.session.add_all([source, target])
    db.session.flush()
    relation = KnowledgeGraphRelationCandidate(
        job_id=job.id, candidate_key="relation", relation_type="addresses",
        source_candidate_id=source.id, target_candidate_id=target.id,
        canonical_source_id=source.canonical_entity_id,
        canonical_target_id=target.canonical_entity_id,
        risk_level="new_fact", validation_status="validated",
        review_status="approved", confidence=1,
    )
    db.session.add(relation)
    db.session.flush()
    quote = "秸秆还田缓解土壤板结。"
    evidence = KnowledgeGraphCandidateEvidence(
        relation_candidate_id=relation.id, evidence_key="evidence-1",
        document_id=document.id, content_sha256=document.file_hash,
        chunk_index=0, page=1, span_start=0, span_end=len(quote), quote=quote,
        quote_sha256=hashlib.sha256(quote.encode()).hexdigest(),
        schema_version=job.schema_version, backend_name=job.backend_name,
        extractor_version=job.extractor_version,
        validation_status="validated", review_status="approved", is_active=True,
    )
    db.session.add(evidence)
    db.session.commit()
    return app, context, admin, document, relation


def test_release_preview_publish_incremental_version_and_rollback(tmp_path):
    app, context, admin, document, relation = _setup(tmp_path)
    store = MemoryVersionedGraphStore()
    try:
        service = KnowledgeGraphReleaseService(db.session, store)
        preview = service.preview()
        assert preview.validation_report["passed"] is True
        assert preview.diff_summary == {
            "add_entity": 2, "add_relation": 1, "total": 3,
            "entity_count": 2, "relation_count": 1, "evidence_count": 1,
        }
        release_one = service.publish(release_id="release-1", created_by=admin.id)
        db.session.commit()
        assert store.active_release() == "release-1"
        assert db.session.get(KnowledgeGraphControl, "active").active_release_id == "release-1"
        changes = KnowledgeGraphReleaseChange.query.filter_by(
            release_id="release-1",
        ).all()
        assert all(item.valid_from_release == "release-1" for item in changes)
        assert KnowledgeGraphAuditExport.query.filter_by(
            release_id="release-1", state="pending",
        ).count() == 2

        quote = "长期试验再次支持该治理关系。"
        db.session.add(KnowledgeGraphCandidateEvidence(
            relation_candidate_id=relation.id, evidence_key="evidence-2",
            document_id=document.id, content_sha256=document.file_hash,
            chunk_index=1, page=2, span_start=4, span_end=18, quote=quote,
            quote_sha256=hashlib.sha256(quote.encode()).hexdigest(),
            schema_version=release_one.schema_version,
            backend_name="stub", extractor_version="1",
            validation_status="validated", review_status="approved", is_active=True,
        ))
        db.session.commit()
        preview_two = service.preview()
        assert preview_two.diff_summary["append_evidence"] == 1
        assert preview_two.diff_summary["total"] == 1
        service.publish(release_id="release-2", created_by=admin.id)
        db.session.commit()
        assert store.active_release() == "release-2"
        assert len(store.closed_relations) == 1
        assert len(store.export_snapshot("release-2")["entities"]) == 2

        audit, replayed = service.rollback(
            target_release_id="release-1", operator_id=admin.id,
            reason="第二版线上查询异常", idempotency_key="rollback-1",
        )
        db.session.commit()
        assert replayed is False
        assert audit.source_release_id == "release-2"
        assert audit.duration_ms < 60_000
        assert store.active_release() == "release-1"
        replay, replayed = service.rollback(
            target_release_id="release-1", operator_id=admin.id,
            reason="第二版线上查询异常", idempotency_key="rollback-1",
        )
        assert replayed is True and replay.id == audit.id
        assert KnowledgeGraphRollbackAudit.query.count() == 1
    finally:
        db.session.remove()
        context.pop()


def test_release_gates_reject_invalid_direction_missing_evidence_and_orphan(tmp_path):
    _, context, _, _, relation = _setup(tmp_path)
    store = MemoryVersionedGraphStore()
    try:
        relation.relation_type = "includes_indicator"
        evidence = KnowledgeGraphCandidateEvidence.query.one()
        evidence.is_active = False
        orphan = KnowledgeGraphEntityCandidate(
            job_id=relation.job_id, candidate_key="orphan", entity_type="indicator",
            mention="有机质", canonical_entity_id="indicator:organic-matter",
            canonical_name="有机质", resolution_status="resolved",
            risk_level="new_entity", review_status="approved", confidence=1,
        )
        db.session.add(orphan)
        db.session.commit()
        preview = KnowledgeGraphReleaseService(db.session, store).preview()
        gates = preview.validation_report["gates"]
        assert gates["direction"]["passed"] is False
        assert gates["valid_evidence"]["passed"] is False
        assert gates["no_orphan_entities"]["passed"] is False
        try:
            KnowledgeGraphReleaseService(db.session, store).publish(
                release_id="invalid", created_by=1,
            )
        except ReleaseError as exc:
            assert exc.code == "release_validation_failed"
        else:
            raise AssertionError("invalid release should have been rejected")
        assert KnowledgeGraphRelease.query.count() == 0
        assert store.active_release() is None
    finally:
        db.session.remove()
        context.pop()


def test_failed_release_activation_compensates_to_previous_healthy_release(tmp_path):
    _, context, admin, document, relation = _setup(tmp_path)
    store = MemoryVersionedGraphStore()
    try:
        service = KnowledgeGraphReleaseService(db.session, store)
        service.publish(release_id="healthy", created_by=admin.id)
        db.session.commit()
        quote = "new support"
        db.session.add(KnowledgeGraphCandidateEvidence(
            relation_candidate_id=relation.id, evidence_key="new-support",
            document_id=document.id, content_sha256=document.file_hash,
            chunk_index=1, page=2, span_start=0, span_end=len(quote), quote=quote,
            quote_sha256=hashlib.sha256(quote.encode()).hexdigest(),
            schema_version="minimal-cultivated-land-kg-schema-v1",
            backend_name="stub", extractor_version="1",
            validation_status="validated", review_status="approved", is_active=True,
        ))
        db.session.commit()
        store.fail_health_for = "faulty"
        try:
            service.publish(release_id="faulty", created_by=admin.id)
        except ReleaseError as exc:
            assert exc.code == "graph_store_activation_failed"
            db.session.rollback()
        else:
            raise AssertionError("faulty activation must fail")
        assert store.active_release() == "healthy"
        assert db.session.get(KnowledgeGraphControl, "active").active_release_id == "healthy"
    finally:
        db.session.remove()
        context.pop()


def test_audit_export_is_post_publish_and_json_is_reproducible(tmp_path):
    _, context, admin, _, _ = _setup(tmp_path)
    store = MemoryVersionedGraphStore()
    try:
        service = KnowledgeGraphReleaseService(db.session, store)
        service.publish(release_id="release-export", created_by=admin.id)
        db.session.commit()
        export_dir = tmp_path / "exports"
        counts = ReleaseAuditExporter(db.session, store, export_dir).process_pending()
        db.session.commit()
        assert counts == {"selected": 2, "completed": 2, "failed": 0}
        row = KnowledgeGraphAuditExport.query.filter_by(format="json").one()
        assert row.state == "completed"
        assert row.artifact_sha256 == hashlib.sha256(
            (export_dir / "release-export.json").read_bytes()
        ).hexdigest()
        parquet_path = export_dir / "release-export.parquet"
        assert parquet_path.read_bytes()[:4] == b"PAR1"
        assert KnowledgeGraphAuditExport.query.filter_by(
            format="parquet", state="completed",
        ).count() == 1
    finally:
        db.session.remove()
        context.pop()


def _dense_graph():
    entities = [{"id": "center", "type": "measure", "name": "中心"}]
    relations = []
    for index in range(130):
        entity_id = f"obstacle:{index}"
        entities.append({"id": entity_id, "type": "obstacle", "name": entity_id})
        relations.append({
            "id": f"r{index}", "type": "addresses", "source": "center",
            "target": entity_id, "evidence": [{
                "evidence_id": f"e{index}", "document_id": index + 1,
                "chunk_index": 0, "page": 1,
            }],
        })
    return {
        "schema_version": "minimal-cultivated-land-kg-schema-v1",
        "release": {"release_id": "dense"},
        "entities": entities, "relations": relations,
    }


def test_bounded_directional_query_high_degree_acl_and_timeout_fallback():
    store = JsonGraphStore(_dense_graph())
    outbound = store.neighbors(GraphQuery(
        ("center",), direction="outbound", max_hops=2, top_k=100,
    ))
    assert len(outbound.relations) == 100
    assert outbound.truncated is True
    byte_bounded = store.neighbors(GraphQuery(
        ("center",), direction="outbound", max_hops=2, top_k=100,
        max_result_bytes=1024,
    ))
    assert byte_bounded.truncated is True
    assert len(json.dumps({
        "active_release": byte_bounded.active_release,
        "entities": byte_bounded.entities,
        "relations": byte_bounded.relations,
        "evidence_references": byte_bounded.evidence_references,
    }, ensure_ascii=False, default=list).encode("utf-8")) <= 1024
    inbound = store.neighbors(GraphQuery(
        ("center",), direction="inbound", max_hops=1, top_k=100,
    ))
    assert inbound.relations == ()

    class FilteredChunks:
        received_filters = None

        def get_by_references(self, references, **kwargs):
            self.received_filters = kwargs["filters"]
            return [{
                "content": "公开证据", "metadata": {"visibility_scope": "public"},
            }]

    chunks = FilteredChunks()
    result = SafeGraphQueryService(store, chunks).query(
        entity_ids=("center",), direction="outbound", top_k=2,
        filters={"$or": [{"visibility_scope": "public"}, {"owner_id": 7}]},
    )
    assert result["evidence"][0]["content"] == "公开证据"
    assert chunks.received_filters == {
        "$or": [{"visibility_scope": "public"}, {"owner_id": 7}],
    }

    class TimeoutStore:
        def neighbors(self, _query):
            raise TimeoutError("database statement timeout with private details")

    degraded = SafeGraphQueryService(TimeoutStore(), chunks).query(
        entity_ids=("center",), top_k=2,
    )
    assert degraded["status"] == "degraded"
    assert degraded["failure_code"] == "graph_query_timeout"
    assert "private" not in str(degraded)
