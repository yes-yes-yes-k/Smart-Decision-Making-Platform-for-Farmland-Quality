"""Create the public/private multi-label knowledge schema and migrate documents.

Safe default: schema only. Existing content is changed only with explicit flags.

Example for the confirmed initial migration::

    python scripts/migrate_kb_taxonomy.py --publish-existing \
        --approve-domain cultivated_land_quality --propose-labels --sync-vectors
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import chromadb
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from framework.config import Config
from framework.knowledge.taxonomy import (
    DOMAIN_CODES, classify_label_candidates, label_level, parent_domain,
)
from framework.models.document import Document
from framework.models.document_label import DocumentLabel


def ensure_schema(engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("kb_document")}
    if "visibility_scope" not in columns:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE kb_document ADD COLUMN visibility_scope "
                "VARCHAR(20) NOT NULL DEFAULT 'private'"
            ))
        print("[schema] 已添加 kb_document.visibility_scope")
    else:
        print("[schema] kb_document.visibility_scope 已存在")
    DocumentLabel.__table__.create(bind=engine, checkfirst=True)
    print("[schema] kb_document_label 已就绪")


def load_vector_texts():
    grouped = defaultdict(list)
    client = chromadb.PersistentClient(path=Config.CHROMA_PERSIST_DIR)
    for item in client.list_collections():
        collection = client.get_collection(item.name)
        batch_size = 500
        for offset in range(0, collection.count(), batch_size):
            data = collection.get(
                limit=batch_size, offset=offset, include=["documents", "metadatas"],
            )
            for content, metadata in zip(
                data.get("documents") or [], data.get("metadatas") or [],
            ):
                document_id = (metadata or {}).get("document_id")
                if document_id is not None and content:
                    grouped[int(document_id)].append(content)
    return grouped


def upsert_label(
    session: Session, document: Document, code: str, *, status: str,
    source: str, confidence=None, evidence=None,
) -> DocumentLabel:
    row = session.query(DocumentLabel).filter_by(
        document_id=document.id, label_code=code,
    ).first()
    if row is None:
        row = DocumentLabel(
            document_id=document.id,
            label_code=code,
            label_level=label_level(code),
            parent_code=parent_domain(code),
            create_by=document.create_by,
        )
        session.add(row)
    protected_review = (
        status == DocumentLabel.STATUS_PENDING
        and row.review_status in {
            DocumentLabel.STATUS_APPROVED, DocumentLabel.STATUS_REJECTED,
        }
    )
    if not protected_review:
        row.review_status = status
        row.assignment_source = source
        row.confidence = confidence
        row.evidence = list(evidence or [])
    return row


def migrate_content(engine, args) -> None:
    vector_texts = load_vector_texts() if args.propose_labels else {}
    with Session(engine) as session:
        documents = session.query(Document).order_by(Document.id).all()
        for document in documents:
            if args.refresh_proposals:
                session.query(DocumentLabel).filter_by(
                    document_id=document.id,
                    review_status=DocumentLabel.STATUS_PENDING,
                    assignment_source=DocumentLabel.SOURCE_AUTOMATIC,
                ).delete(synchronize_session=False)
            if args.publish_existing:
                document.visibility_scope = "public"
            if args.approve_domain:
                upsert_label(
                    session, document, args.approve_domain,
                    status=DocumentLabel.STATUS_APPROVED,
                    source=DocumentLabel.SOURCE_MIGRATION,
                    confidence=1.0,
                )
            if args.propose_labels:
                approved = {
                    row.label_code for row in document.labels
                    if row.review_status == DocumentLabel.STATUS_APPROVED
                }
                if args.approve_domain:
                    approved.add(args.approve_domain)
                content = "\n".join(vector_texts.get(document.id, []))
                for candidate in classify_label_candidates(content, exclude=approved):
                    upsert_label(
                        session, document, candidate["label_code"],
                        status=DocumentLabel.STATUS_PENDING,
                        source=DocumentLabel.SOURCE_AUTOMATIC,
                        confidence=candidate["confidence"],
                        evidence=candidate["evidence"],
                    )
        session.commit()
        print(f"[data] 已处理 {len(documents)} 份文档")


def sync_vectors(engine) -> None:
    from framework.knowledge.service import vector_access_metadata
    from framework.vector_store.chroma_store import vector_store

    total = 0
    with Session(engine) as session:
        for document in session.query(Document).order_by(Document.id):
            approved = [
                row.label_code for row in document.labels
                if row.review_status == DocumentLabel.STATUS_APPROVED
            ]
            total += vector_store.update_document_metadata(
                document.id,
                vector_access_metadata(document.visibility_scope, approved),
                owner_id=document.create_by,
                rebuild_indexes=False,
            )
    vector_store._rebuild_bm25_indexes()
    print(f"[vectors] 已同步 {total} 个分块")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish-existing", action="store_true")
    parser.add_argument("--approve-domain", choices=DOMAIN_CODES)
    parser.add_argument("--propose-labels", action="store_true")
    parser.add_argument("--refresh-proposals", action="store_true")
    parser.add_argument("--sync-vectors", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    ensure_schema(engine)
    if args.publish_existing or args.approve_domain or args.propose_labels:
        migrate_content(engine, args)
    if args.sync_vectors:
        sync_vectors(engine)
    with Session(engine) as session:
        print("[verify] public_documents=", session.query(Document).filter_by(
            visibility_scope="public",
        ).count())
        print("[verify] label_statuses=", session.query(
            DocumentLabel.review_status, db_count(DocumentLabel.id),
        ).group_by(DocumentLabel.review_status).all())
    return 0


def db_count(column):
    from sqlalchemy import func
    return func.count(column)


if __name__ == "__main__":
    raise SystemExit(main())
