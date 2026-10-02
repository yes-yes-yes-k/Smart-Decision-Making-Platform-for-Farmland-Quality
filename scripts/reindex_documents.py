"""Safely rebuild vector entries for documents registered in kb_document.

Unlike the legacy script, this command never indexes orphan files and never clears the
whole vector database. Each logical document is replaced by document_id + owner_id.
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.config import Config
from framework.upload.chunker import split_text, split_text_with_pages
from framework.upload.document_parser import parse_document
from framework.vector_store.chroma_store import vector_store
from framework.knowledge.service import vector_access_metadata

STATUS_COMPLETED = 1
STATUS_FAILED = 3


def _database_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "instance", "development.db",
    )


def _load_documents(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    columns = {row[1] for row in conn.execute("PRAGMA table_info(kb_document)")}
    visibility_expr = "visibility_scope" if "visibility_scope" in columns else "'private' AS visibility_scope"
    rows = conn.execute(
        f"""
        SELECT id, doc_name, file_path, file_type, category, treatment_type, create_by,
               {visibility_expr}
        FROM kb_document
        ORDER BY id
        """
    ).fetchall()
    has_labels = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='kb_document_label'"
    ).fetchone() is not None
    documents = []
    for row in rows:
        record = dict(row)
        record["approved_labels"] = []
        if has_labels:
            record["approved_labels"] = [
                item[0] for item in conn.execute(
                    "SELECT label_code FROM kb_document_label "
                    "WHERE document_id=? AND review_status='approved'",
                    (record["id"],),
                ).fetchall()
            ]
        documents.append(record)
    return documents


def _chunks_for(path: str, file_type: str):
    parsed = parse_document(path, file_type, page_aware=True)
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], tuple):
        chunks_with_pages = split_text_with_pages(parsed)
        return (
            [item[0] for item in chunks_with_pages],
            [item[1] for item in chunks_with_pages],
        )
    chunks = split_text(parsed or "")
    return chunks, [None] * len(chunks)


def reindex_documents() -> dict:
    db_path = _database_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"数据库不存在: {db_path}")

    conn = sqlite3.connect(db_path)
    documents = _load_documents(conn)
    if not documents:
        print("kb_document 中没有可重建的文档；未修改向量库。")
        conn.close()
        return {"indexed": 0, "failed": 0, "missing": 0}

    stats = {"indexed": 0, "failed": 0, "missing": 0}
    for record in documents:
        document_id = int(record["id"])
        owner_id = int(record["create_by"])
        stored_path = record["file_path"]
        file_path = stored_path if os.path.isabs(stored_path) else os.path.join(
            Config.UPLOAD_FOLDER, stored_path,
        )
        if not os.path.exists(file_path):
            print(f"[missing] id={document_id} path={file_path}")
            conn.execute(
                "UPDATE kb_document SET status=?, chunk_count=0 WHERE id=?",
                (STATUS_FAILED, document_id),
            )
            stats["missing"] += 1
            continue

        try:
            chunks, pages = _chunks_for(file_path, record["file_type"])
            if not chunks:
                raise ValueError("文档解析后没有可索引内容")
            metadatas = []
            access_metadata = vector_access_metadata(
                record["visibility_scope"], record["approved_labels"],
            )
            for index, page in enumerate(pages):
                metadata = {
                    "source": record["doc_name"],
                    "doc_name": record["doc_name"],
                    "document_id": document_id,
                    "owner_id": owner_id,
                    "category": record["category"] or "other",
                    "chunk_index": index,
                    **access_metadata,
                }
                if record["treatment_type"]:
                    metadata["treatment_type"] = record["treatment_type"]
                if page is not None:
                    metadata["page"] = int(page)
                metadatas.append(metadata)

            vector_store.delete_by_document_id(document_id, owner_id)
            added = vector_store.add_documents(
                chunks,
                metadatas,
                ids=[f"doc-{document_id}-chunk-{i}" for i in range(len(chunks))],
                category=record["category"],
            )
            if added != len(chunks):
                raise RuntimeError(
                    f"知识库写入不完整: expected={len(chunks)}, actual={added}"
                )
            conn.execute(
                "UPDATE kb_document SET status=?, chunk_count=? WHERE id=?",
                (STATUS_COMPLETED, added, document_id),
            )
            stats["indexed"] += 1
            print(f"[ok] id={document_id} {record['doc_name']} chunks={added}")
        except Exception as exc:
            vector_store.delete_by_document_id(document_id, owner_id)
            conn.execute(
                "UPDATE kb_document SET status=?, chunk_count=0 WHERE id=?",
                (STATUS_FAILED, document_id),
            )
            stats["failed"] += 1
            print(f"[failed] id={document_id} {record['doc_name']}: {exc}")

    conn.commit()
    conn.close()
    print(f"重建完成: {stats}")
    return stats


if __name__ == "__main__":
    reindex_documents()
