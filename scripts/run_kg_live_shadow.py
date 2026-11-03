"""Read one approved public source; exercise the worker in an isolated shadow DB."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id", type=int)
    parser.add_argument("--list-sources", action="store_true")
    parser.add_argument("--siliconflow", action="store_true", help="use the explicitly authorized existing provider")
    parser.add_argument("--verify-legacy-chunks", action="store_true", help="prove old chunks against original file and current parser")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.siliconflow:
        os.environ["KG_EXTRACTION_BASE_URL"] = "https://api.siliconflow.cn/v1"
        os.environ["KG_EXTRACTION_ALLOW_SILICONFLOW"] = "true"
        os.environ["KG_EXTRACTION_MODEL"] = os.environ.get("SILICONFLOW_CHAT_MODEL", "deepseek-ai/DeepSeek-V4-Flash")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from framework.config import Config
    from framework.models.document import Document
    from framework.models.knowledge_graph import (
        KnowledgeGraphExtractionJob, KnowledgeGraphOutboxEvent, KnowledgeGraphEntityCandidate,
        KnowledgeGraphRelationCandidate, KnowledgeGraphCandidateEvidence,
        KnowledgeGraphClaimCandidate, KnowledgeGraphClaimEvidence,
    )
    from framework.knowledge_graph.jobs import document_is_graph_eligible, enqueue_document_indexed
    source_engine = create_engine(Config.SQLALCHEMY_DATABASE_URI, connect_args={"connect_timeout": 5})
    with sessionmaker(bind=source_engine)() as session:
        if args.list_sources:
            rows = session.query(Document).filter_by(status=Document.STATUS_COMPLETED,
                processing_stage="completed", review_status=Document.REVIEW_APPROVED,
                visibility_scope="public").filter(Document.chunk_count > 0,
                Document.document_kind.in_(["academic_paper", "standard", "policy", "method_guideline"])
                ).order_by(Document.chunk_count, Document.id).limit(10).all()
            print(json.dumps([dict(id=d.id, chunks=d.chunk_count, kind=d.document_kind) for d in rows]))
            return 0
        if not args.document_id or not args.output:
            parser.error("--document-id and --output are required for shadow extraction")
        document = session.get(Document, args.document_id)
        if not document or not document_is_graph_eligible(document):
            parser.error("source must be an approved, completed public literature document")
        values = {column.name: getattr(document, column.name) for column in Document.__table__.columns}
    source_engine.dispose()
    from framework.knowledge_graph.adapters.live_graphrag import LiveMicrosoftGraphRagBackend
    from framework.knowledge_graph.chunk_reader import WorkerPublishedChunkReader, VerifiedLegacyShadowReader
    from framework.knowledge_graph.worker import GraphExtractionWorker
    python = os.environ.get("KG_GRAPHRAG_PYTHON") or str(ROOT / ".tools/graphrag-runtime/Scripts/python.exe")
    backend = LiveMicrosoftGraphRagBackend(python)
    backend.provider.check_runtime()
    run_id = uuid.uuid4().hex
    shadow_dir = ROOT / ".tools/kg-shadow" / run_id
    shadow_dir.mkdir(parents=True)
    engine = create_engine(f"sqlite:///{(shadow_dir / 'shadow.db').as_posix()}")
    for model in (Document, KnowledgeGraphExtractionJob, KnowledgeGraphOutboxEvent,
                  KnowledgeGraphEntityCandidate, KnowledgeGraphRelationCandidate, KnowledgeGraphCandidateEvidence,
                  KnowledgeGraphClaimCandidate, KnowledgeGraphClaimEvidence):
        model.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        document = Document(**values)
        session.add(document)
        session.flush()
        enqueue_document_indexed(session, document)
        session.commit()
    reader = (VerifiedLegacyShadowReader(Config.CHROMA_PERSIST_DIR, source=values, upload_root=Config.UPLOAD_FOLDER)
              if args.verify_legacy_chunks else WorkerPublishedChunkReader(Config.CHROMA_PERSIST_DIR))
    worker = GraphExtractionWorker(sessions, backend, reader, worker_id=f"shadow:{run_id}")
    started = time.monotonic()
    result = worker.run_once()
    with sessions() as session:
        job = session.query(KnowledgeGraphExtractionJob).one()
        report = dict(schema="kg-live-shadow-v1",
            evaluation_mode=("live_backend_predictions" if backend.provider.last_usage and result.get("state") == "completed"
                             else "live_backend_attempt" if backend.provider.last_usage else "shadow_worker_attempt"),
            document_id=values["id"], chunks=values["chunk_count"], content_sha256=values["file_hash"],
            backend=backend.name, backend_version=backend.version, backend_config_digest=job.backend_config_digest,
            model=os.environ.get("KG_EXTRACTION_MODEL"), duration_seconds=round(time.monotonic()-started, 3),
            token_usage=backend.provider.last_usage,
            legacy_chunks_verified=getattr(reader, "legacy_verified", False),
            worker=result, entity_candidates=session.query(KnowledgeGraphEntityCandidate).count(),
            relation_candidates=session.query(KnowledgeGraphRelationCandidate).count(),
            evidence_records=session.query(KnowledgeGraphCandidateEvidence).count(),
            production_database_modified=False, active_release_modified=False,
            shadow_database=str(shadow_dir / "shadow.db"), quality_evaluation_complete=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    engine.dispose()
    return int(result.get("state") != "completed")


if __name__ == "__main__":
    raise SystemExit(main())
