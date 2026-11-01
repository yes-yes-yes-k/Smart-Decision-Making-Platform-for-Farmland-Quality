"""Plan first, then apply/resume or roll back verified public chunk hashes."""
import argparse
import json
import os
from datetime import datetime, UTC
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--document-id", type=int, action="append")
    parser.add_argument("--after-id", type=int, default=0)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--continue-report", type=Path, help="continue a paused report and retain its completed checkpoints")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    mode.add_argument("--rollout", action="store_true", help="verify each document, then lock and apply its audited plan")
    args = parser.parse_args()
    previous = None
    if args.continue_report:
        previous = json.loads(args.continue_report.read_text(encoding="utf-8"))
        if previous.get("state") != "paused" or not args.rollout:
            parser.error("--continue-report requires a paused report and --rollout")
        args.after_id = int(previous.get("last_document_id", 0))
    if not 1 <= args.limit <= 10000:
        parser.error("--limit must be between 1 and 10000")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from framework.config import Config
    from framework.models.document import Document
    from framework.knowledge_graph.jobs import document_is_graph_eligible, SUPPORTED_DOCUMENT_KINDS
    from framework.knowledge_graph.chunk_reader import WorkerPublishedChunkReader
    from framework.knowledge_graph.chunk_hash_migration import ChunkHashMigration, HashMigrationJournal, HashMigrationError
    from framework.knowledge_graph.contracts import stable_digest
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI, connect_args={"connect_timeout": 5})
    sessions = sessionmaker(bind=engine)
    reader = WorkerPublishedChunkReader(Config.CHROMA_PERSIST_DIR)
    scope = stable_digest(dict(database=engine.url.render_as_string(hide_password=True),
                               vectors=str(Path(Config.CHROMA_PERSIST_DIR).resolve())))
    journal = HashMigrationJournal(args.journal, scope=scope)
    service = ChunkHashMigration(reader.client, journal, Config.UPLOAD_FOLDER)
    with sessions() as session:
        ids = args.document_id or (journal.pending_ids()[:args.limit] if args.resume else [row[0] for row in
            session.query(Document.id).filter(Document.id > args.after_id, Document.status == Document.STATUS_COMPLETED,
                Document.processing_stage == "completed", Document.review_status == Document.REVIEW_APPROVED,
                Document.visibility_scope == "public", Document.chunk_count > 0,
                Document.document_kind.in_(SUPPORTED_DOCUMENT_KINDS), Document.file_hash.is_not(None))
                .order_by(Document.id).limit(args.limit)])
    report = dict(mode="rollback" if args.rollback else "apply" if args.apply else "verified_rollout" if args.rollout else "dry_run",
                  process_id=os.getpid(), state="running", started_at=datetime.now(UTC).isoformat(),
                  selected_documents=len(set(ids)), documents=[], vector_embeddings_rebuilt=False, failed=0)
    if previous:
        report["documents"] = list(previous.get("documents", []))
        report["selected_documents"] = len(set(ids) | {row["document_id"] for row in report["documents"]})
        report["failed"] = sum(row["state"] == "blocked" for row in report["documents"])
        report["updated_chunks"] = sum(row.get("updated_chunks", 0) for row in report["documents"])
        report["resumed_from_document_id"] = args.after_id
        report["previous_started_at"] = previous.get("started_at")
    def save_report():
        args.report.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.report.with_suffix(args.report.suffix+".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(args.report)
    save_report()
    try:
        for document_id in sorted(set(ids)):
            try:
                with sessions() as session:
                    query = session.query(Document).filter_by(id=document_id)
                    if args.apply or args.rollback:
                        query = query.with_for_update()
                    document = query.one_or_none()
                    if not document or not document_is_graph_eligible(document):
                        raise HashMigrationError("source_not_eligible")
                    source = {column.name: getattr(document, column.name) for column in Document.__table__.columns}
                    if args.apply or args.rollback:
                        result = service.execute(source, rollback=args.rollback)
                    else:
                        result = service.plan(source)
                        if args.rollout and result["state"] != "already_bound":
                            # Parsing takes place without the source row lock.
                            # Lock and re-read only for the short metadata write.
                            session.rollback()
                            document = session.query(Document).filter_by(id=document_id).with_for_update().one_or_none()
                            if not document or not document_is_graph_eligible(document):
                                raise HashMigrationError("source_not_eligible")
                            current = {column.name: getattr(document, column.name) for column in Document.__table__.columns}
                            result = service.execute(current)
                    session.commit()
            except Exception as exc:
                result = dict(document_id=document_id, state="blocked", code=getattr(exc, "code", "verification_failed"))
                report["failed"] += 1
            report["documents"].append(result)
            report["updated_chunks"] = sum(item.get("updated_chunks", 0) for item in report["documents"])
            report["missing_chunks"] = sum(item.get("missing_chunks", 0) for item in report["documents"])
            report["reindex_document_ids"] = [item["document_id"] for item in report["documents"]
                if item.get("code") in {"legacy_source_reindex_required", "chunk_count_mismatch"}]
            report["last_document_id"] = document_id
            save_report()
            print(json.dumps(result), flush=True)
    finally:
        journal.close()
        engine.dispose()
    report["state"] = "completed_with_blocks" if report["failed"] else "completed"
    report["finished_at"] = datetime.now(UTC).isoformat()
    save_report()
    return int(bool(report["failed"]))


if __name__ == "__main__":
    raise SystemExit(main())
