"""Worker integration tests use an isolated SQLite database and no network."""
import subprocess
import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphExtractionJob, KnowledgeGraphOutboxEvent, KnowledgeGraphEntityCandidate,
    KnowledgeGraphRelationCandidate, KnowledgeGraphCandidateEvidence,
    KnowledgeGraphClaimCandidate, KnowledgeGraphClaimEvidence,
)
from framework.knowledge_graph.adapters.live_graphrag import (
    LiveGraphRagProvider, LiveMicrosoftGraphRagBackend, ExtractionBackendError,
)
from framework.knowledge_graph.candidate_pipeline import CandidatePipeline, CanonicalEntityCatalog
from framework.knowledge_graph.contracts import ExtractionRequest, SourceChunk, ExtractionResult, EntityCandidate, stable_digest
from framework.knowledge_graph.extraction_config import backend_config_digest, model_endpoint
from framework.knowledge_graph.jobs import enqueue_document_indexed
from framework.knowledge_graph.schema import load_graph_schema
from framework.knowledge_graph.worker import GraphExtractionWorker


class Reader:
    def read_published_chunks(self, **kwargs):
        return [dict(content="秸秆还田缓解土壤板结。", metadata=dict(
            document_id=1, content_sha256="a" * 64, visibility_scope="public", chunk_index=0, page=1))]


class Backend:
    name, version = "microsoft-graphrag", "3.3.0"

    def __init__(self):
        self._config_digest = backend_config_digest(self.name, self.version, load_graph_schema().schema_version)

    def extract(self, request):
        return ExtractionResult(self.name, self.version, self._config_digest,
            request.schema_version, request.request_key,
            (EntityCandidate("e1", "measure", "秸秆还田"),), (), stable_digest("raw"))


@pytest.fixture
def setup_worker(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'worker.db'}", connect_args={"check_same_thread": False})
    for table in (Document, KnowledgeGraphExtractionJob, KnowledgeGraphOutboxEvent,
                  KnowledgeGraphEntityCandidate, KnowledgeGraphRelationCandidate,
                  KnowledgeGraphCandidateEvidence, KnowledgeGraphClaimCandidate, KnowledgeGraphClaimEvidence):
        table.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        document = Document(id=1, doc_name="paper.pdf", file_path="paper.pdf", file_type="pdf",
            file_size=10, status=Document.STATUS_COMPLETED, processing_stage="completed",
            review_status=Document.REVIEW_APPROVED, visibility_scope="public", document_kind="academic_paper",
            file_hash="a" * 64, chunk_count=1, category="other", create_by=1)
        session.add(document)
        session.flush()
        enqueue_document_indexed(session, document)
        session.commit()
    def factory(backend=None, **kwargs):
        return GraphExtractionWorker(sessions, backend or Backend(), Reader(), worker_id="worker-a",
            pipeline_factory=lambda s: CandidatePipeline(s, catalog=CanonicalEntityCatalog.from_mapping(
                dict(entities=[], relations=[]))), **kwargs)
    yield sessions, factory
    engine.dispose()


def test_outbox_to_pending_candidates_and_no_repeat(setup_worker):
    sessions, factory = setup_worker
    worker = factory()
    assert worker.run_once()["state"] == "completed"
    assert worker.run_once()["processed"] == 0
    with sessions() as session:
        assert session.query(KnowledgeGraphExtractionJob).one().state == "completed"
        candidate = session.query(KnowledgeGraphEntityCandidate).one()
        assert candidate.review_status == "pending"
        assert session.get(Document, 1).status == Document.STATUS_COMPLETED


def test_backend_failure_retries_without_touching_document(setup_worker):
    sessions, factory = setup_worker
    backend = Backend()
    def fail(_):
        raise ExtractionBackendError("extraction_timeout", retryable=True)
    backend.extract = fail
    assert factory(backend).run_once()["code"] == "extraction_timeout"
    with sessions() as session:
        assert session.query(KnowledgeGraphExtractionJob).one().state == "retry"
        assert session.query(KnowledgeGraphEntityCandidate).count() == 0
        assert session.get(Document, 1).status == Document.STATUS_COMPLETED


def test_partial_candidate_write_rolls_back(setup_worker):
    sessions, factory = setup_worker
    class BrokenPipeline:
        def __init__(self, session):
            self.session = session
        def process(self, job, request, result):
            self.session.add(KnowledgeGraphEntityCandidate(job_id=job.id, candidate_key="partial",
                entity_type="measure", mention="partial"))
            self.session.flush()
            raise RuntimeError("private model error must not be persisted")
    worker = factory()
    worker.pipeline_factory = BrokenPipeline
    assert worker.run_once()["state"] == "failed"
    with sessions() as session:
        assert session.query(KnowledgeGraphEntityCandidate).count() == 0
        assert session.query(KnowledgeGraphExtractionJob).one().failure_message is None


def test_source_changed_during_model_call_is_rejected(setup_worker):
    sessions, factory = setup_worker
    backend = Backend()
    original = backend.extract
    def change(request):
        with sessions() as session:
            session.get(Document, 1).file_hash = "b" * 64
            session.commit()
        return original(request)
    backend.extract = change
    assert factory(backend).run_once()["code"] == "stale_document_hash"
    with sessions() as session:
        assert session.query(KnowledgeGraphEntityCandidate).count() == 0


def test_lease_is_renewed_during_slow_extraction(setup_worker):
    sessions, factory = setup_worker
    backend = Backend()
    original = backend.extract
    def slow(request):
        time.sleep(1.3)
        return original(request)
    backend.extract = slow
    assert factory(backend, lease_seconds=1, heartbeat_seconds=0.1).run_once()["state"] == "completed"


@pytest.mark.parametrize("endpoint", ["https://api.openai.com/v1", "http://127.0.0.1.evil/v1",
                                       "http://user:secret@localhost/v1"])
def test_model_endpoint_rejects_remote_addresses(monkeypatch, endpoint):
    monkeypatch.delenv("KG_EXTRACTION_ALLOW_SILICONFLOW", raising=False)
    monkeypatch.setenv("KG_EXTRACTION_BASE_URL", endpoint)
    with pytest.raises(ValueError, match="must_be_local"):
        model_endpoint()


def test_siliconflow_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("KG_EXTRACTION_BASE_URL", "https://api.siliconflow.cn/v1")
    monkeypatch.delenv("KG_EXTRACTION_ALLOW_SILICONFLOW", raising=False)
    with pytest.raises(ValueError):
        model_endpoint()
    monkeypatch.setenv("KG_EXTRACTION_ALLOW_SILICONFLOW", "true")
    assert model_endpoint() == "https://api.siliconflow.cn/v1"


def test_invalid_model_configuration_does_not_break_upload_outbox(monkeypatch, setup_worker):
    sessions, _ = setup_worker
    monkeypatch.setenv("KG_EXTRACTION_BASE_URL", "https://unapproved.invalid/v1")
    monkeypatch.setenv("KG_EXTRACTION_MAX_TOKENS", "bad-config")
    with sessions() as session:
        event, created = enqueue_document_indexed(session, session.get(Document, 1))
        session.commit()
        assert created is True
        assert event.state == "pending"
        assert session.get(Document, 1).status == Document.STATUS_COMPLETED


def test_subprocess_timeout_and_error_are_sanitized():
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("contains secret", 1)
    provider = LiveGraphRagProvider("python", run=timeout)
    with pytest.raises(ExtractionBackendError, match="extraction_timeout"):
        provider.load(ExtractionRequest("1", 1, "a" * 64, load_graph_schema().schema_version,
            (SourceChunk(1, "a" * 64, 0, "测试正文", page=1),)))


def test_stale_worker_cannot_persist_candidates(setup_worker):
    sessions, factory = setup_worker
    backend = Backend()
    original = backend.extract
    def take_over(request):
        with sessions() as session:
            session.get(KnowledgeGraphExtractionJob, int(request.job_id)).lease_owner = "worker-b"
            session.commit()
        return original(request)
    backend.extract = take_over
    assert factory(backend).run_once()["state"] == "lease_lost"
    with sessions() as session:
        assert session.query(KnowledgeGraphEntityCandidate).count() == 0
        assert session.query(KnowledgeGraphExtractionJob).one().lease_owner == "worker-b"


def test_config_mismatch_prevents_model_call(setup_worker):
    _, factory = setup_worker
    backend = Backend()
    backend._config_digest = "wrong"
    backend.extract = lambda _: pytest.fail("must not call a different model configuration")
    assert factory(backend).run_once()["code"] == "backend_config_mismatch"


def test_worker_stops_without_polling_after_shutdown(setup_worker):
    _, factory = setup_worker
    stop = threading.Event()
    stop.set()
    worker = factory()
    worker.run_once = lambda: pytest.fail("must not consume after shutdown")
    worker.run_forever(stop)


def test_worker_leaves_audit_outbox_for_exporter(setup_worker):
    sessions, factory = setup_worker
    with sessions() as session:
        session.add(KnowledgeGraphOutboxEvent(event_key="audit-export", event_type="knowledge_graph_release_export_requested",
            aggregate_type="kg_release", aggregate_id="release-1", payload={}, state="pending"))
        session.commit()
    factory().run_once()
    with sessions() as session:
        assert session.query(KnowledgeGraphOutboxEvent).filter_by(event_key="audit-export").one().state == "pending"


def test_worker_chunk_reader_is_filtered_and_bounded():
    from framework.knowledge_graph.chunk_reader import WorkerPublishedChunkReader
    from unittest.mock import Mock
    client = Mock()
    client.list_collections.return_value = ["literature"]
    client.get_collection.return_value.get.return_value = dict(documents=["published"], metadatas=[{}])
    assert len(WorkerPublishedChunkReader(client=client).read_published_chunks(
        document_id=1, content_sha256="abc", expected_count=1)) == 1
    kwargs = client.get_collection.return_value.get.call_args.kwargs
    assert kwargs["limit"] == 2
    assert kwargs["where"] == {"$and": [{"document_id": 1}, {"content_sha256": "abc"}, {"visibility_scope": "public"}]}


def test_cli_does_not_consume_before_backend_qualification(monkeypatch):
    import sys
    import dotenv
    from scripts.run_knowledge_graph_worker import main
    from framework.knowledge_graph import adapter_gate
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *_: False)
    monkeypatch.setenv("KG_GRAPHRAG_PYTHON", sys.executable)
    monkeypatch.setenv("KG_EXTRACTION_MODEL", "fixture")
    monkeypatch.setenv("KG_EXTRACTION_BASE_URL", "http://127.0.0.1:8001/v1")
    monkeypatch.setattr(LiveGraphRagProvider, "check_runtime", lambda self: None)
    monkeypatch.setattr(adapter_gate, "evaluate_adapter_policy", lambda *_: {"production_ready": False})
    monkeypatch.setattr(sys, "argv", ["worker", "--once"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_extraction_schema_import_needs_no_application_packages():
    import sys
    from pathlib import Path
    root = str(Path(__file__).resolve().parents[1])
    result = subprocess.run([sys.executable, "-S", "-c",
        f"import sys; sys.path.insert(0, {root!r}); from framework.knowledge_graph.schema import load_graph_schema; print(load_graph_schema().schema_version)"],
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "minimal-cultivated-land-kg-schema-v1"


@pytest.mark.parametrize("matches", [True, False])
def test_legacy_shadow_binding_requires_exact_original_chunks(tmp_path, monkeypatch, matches):
    import hashlib
    from unittest.mock import Mock
    from framework.knowledge_graph.chunk_reader import VerifiedLegacyShadowReader
    from framework.knowledge_graph.candidate_pipeline import CandidatePipelineError
    from framework.upload import document_parser
    original = tmp_path / "source.pdf"
    original.write_bytes(b"original bytes")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    client = Mock()
    client.list_collections.return_value = ["public"]
    metadata = dict(document_id=1, visibility_scope="public", chunk_index=0, page=1)
    client.get_collection.return_value.get.side_effect = [dict(documents=[], metadatas=[]),
        dict(documents=["original text" if matches else "different vector text"], metadatas=[metadata])]
    monkeypatch.setattr(document_parser, "parse_document", lambda *_a, **_k: [(1, "original text")])
    reader = VerifiedLegacyShadowReader(None, source=dict(id=1, file_hash=digest,
        file_path=str(original), file_type="pdf"), upload_root=tmp_path, client=client)
    if matches:
        rows = reader.read_published_chunks(document_id=1, content_sha256=digest, expected_count=1)
        assert rows[0]["metadata"]["content_sha256"] == digest
        assert "content_sha256" not in metadata
        assert reader.legacy_verified is True
        client.get_collection.return_value.update.assert_not_called()
    else:
        with pytest.raises(CandidatePipelineError, match="source chunks differ"):
            reader.read_published_chunks(document_id=1, content_sha256=digest, expected_count=1)
        assert reader.legacy_verified is False


def test_graph_record_transport_normalizes_separators_without_changing_facts():
    from framework.knowledge_graph.graph_record_transport import normalize_graph_records
    entity = '("entity"<|>lime application<|>measure<|>liming)'
    relation = '("relationship"<|>lime application<|>acidification<|>addresses<|>1)'
    assert normalize_graph_records(f"{entity}\n{relation}\n##<|>COMPLETE|>") == f"{entity}##{relation}##<|COMPLETE|>"
    assert normalize_graph_records("<|COMPLETE|>") == "<|COMPLETE|>"
    with pytest.raises(ValueError, match="invalid_model_output"):
        normalize_graph_records("unstructured summary without facts")


def test_standard_chinese_tuple_punctuation_preserves_names():
    from framework.knowledge_graph.graph_record_transport import normalize_graph_records
    raw = '("entity"<|>饱和导水率（指标）<|>indicator<|>土壤性质）  \n（"entity"<|>NY/T 1121.22—2010<|>standard<|>测定标准)\n##<|COMPLETE|>'
    value = normalize_graph_records(raw)
    assert '饱和导水率（指标）' in value
    assert '（"entity"' not in value
    assert value.count('("entity"') == 2
