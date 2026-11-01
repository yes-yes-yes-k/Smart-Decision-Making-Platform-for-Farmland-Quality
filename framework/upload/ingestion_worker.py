"""异步入库 worker：fire-and-forget 提交 + 状态机跟踪。

状态机: pending(0) → processing(2) → completed(1) 或 failed(3)。
worker 线程内推送独立 Flask app context（Flask-SQLAlchemy 需要）。
"""
from __future__ import annotations
import concurrent.futures
import traceback
import threading
from datetime import datetime, UTC
from typing import Iterable, Optional

from framework.models.user import db
from framework.models.document import Document
from framework.models.ingestion import IngestionItem
from framework.config import Config
from framework.upload.document_parser import parse_document
from framework.upload.chunker import split_text, split_text_with_pages
from framework.vector_store.chroma_store import vector_store
from framework.knowledge.service import assign_labels_for_ingestion, vector_access_metadata
from framework.knowledge.taxonomy import expand_with_parent_domains
from framework.knowledge_graph.jobs import enqueue_document_indexed
from framework.knowledge_graph.evidence_lifecycle import invalidate_document_evidence
from framework.rag.kg_runtime import stable_document_key

# 模块级 worker：与 data_trigger.py 的 ThreadPoolExecutor 模式同源
_WORKER = concurrent.futures.ThreadPoolExecutor(
    max_workers=Config.INGESTION_WORKERS, thread_name_prefix="ingest"
)
_SUBMISSION_SLOTS = threading.BoundedSemaphore(
    Config.INGESTION_WORKERS + Config.INGESTION_MAX_QUEUED
)


class QueueCapacityExceeded(RuntimeError):
    pass


def submit_ingest(
    document_id, file_path, file_type, doc_name, category, treatment_type, owner_id,
    visibility_scope="public", domain_labels: Optional[Iterable[str]] = None,
    ingestion_item_id=None,
):
    """非阻塞提交入库任务；立即返回。

    上传路由调用本函数后立即返回 202，状态机由 worker 内部推进。
    """
    if not _SUBMISSION_SLOTS.acquire(blocking=False):
        raise QueueCapacityExceeded('文献入库队列已满')
    try:
        future = _WORKER.submit(
            _ingest,
            document_id, file_path, file_type, doc_name, category, treatment_type, owner_id,
            visibility_scope, list(domain_labels or []), ingestion_item_id,
        )
    except Exception:
        _SUBMISSION_SLOTS.release()
        raise
    future.add_done_callback(lambda _future: _SUBMISSION_SLOTS.release())
    return future


def _ingest(
    document_id, file_path, file_type, doc_name, category, treatment_type, owner_id,
    visibility_scope="public", domain_labels: Optional[Iterable[str]] = None,
    ingestion_item_id=None,
):
    """入库 worker 主体。异常时记录 traceback 并推进到 failed，避免文档永久停留 processing。"""
    # 在 worker 线程内推送 app context（Flask-SQLAlchemy 需要）
    # 延迟导入避免循环依赖：docs.py → ingestion_worker → app.py → docs.py
    from framework.api.app import create_app
    app = create_app()
    with app.app_context():
        try:
            initial_doc = db.session.query(Document).get(document_id)
            if not initial_doc:
                raise ValueError('文档记录不存在')
            if getattr(initial_doc, 'review_status', Document.REVIEW_APPROVED) != Document.REVIEW_APPROVED:
                raise ValueError('文档尚未通过管理员审核')
            if not list(domain_labels or []):
                raise ValueError('文档没有管理员确认的领域标签')
            _set_progress(
                document_id, ingestion_item_id,
                status=Document.STATUS_PROCESSING,
                state='processing', stage='converting' if file_type == 'caj' else 'parsing',
                progress=10,
            )
            # 解析（parse_document 内部已调用 clean_text）
            pages = parse_document(file_path, file_type, page_aware=True)
            # 切分：page_aware 返回 List[(chunk, page)]；其他格式返回 str
            if isinstance(pages, list) and pages and isinstance(pages[0], tuple):
                chunks_with_pages = split_text_with_pages(pages)
                chunks = [c for c, _ in chunks_with_pages]
                pages_meta = [p for _, p in chunks_with_pages]
            else:
                # 非分页格式（txt/docx/xlsx）回退到普通切分
                chunks = split_text(pages or "")
                pages_meta = [None] * len(chunks)

            if not chunks:
                raise ValueError("文档解析后没有可索引内容")

            _set_progress(
                document_id, ingestion_item_id,
                status=Document.STATUS_PROCESSING,
                state='processing', stage='chunking', progress=70,
            )

            # Domain membership comes exclusively from the upload request.
            # ``category`` remains a physical collection/legacy grouping field
            # and must not silently grant a knowledge-domain label.
            explicit_labels = list(domain_labels or [])
            approved_labels = expand_with_parent_domains(explicit_labels)
            # 新 chunk 先以 private 暂存；全部写入成功后再一次性切换 public。
            access_metadata = vector_access_metadata('private', approved_labels)

            doc = db.session.query(Document).get(document_id)
            if not doc:
                raise RuntimeError(f"文档记录不存在: document_id={document_id}")
            ingestion_item = _get_item(ingestion_item_id, document_id)
            defer_bm25 = bool(ingestion_item and ingestion_item.batch_id)

            metadatas = []
            provenance = getattr(doc, 'provenance_metadata', None) or {}
            source_metadata = provenance.get('source_metadata') or {}
            bibliographic = getattr(doc, 'bibliographic_metadata', None) or {}
            authors = bibliographic.get('authors') or []
            authors_metadata = (
                authors if isinstance(authors, str)
                else "; ".join(str(author) for author in authors if str(author).strip())
            )
            for i in range(len(chunks)):
                metadata = {
                    "source": doc_name,
                    "doc_name": doc_name,
                    "document_id": int(document_id),
                    # Bind every published chunk to the immutable source bytes.
                    # Candidate extraction refuses chunks whose hash differs
                    # from the graph job, preventing stale-vector evidence.
                    "content_sha256": getattr(doc, 'file_hash', None) or '',
                    "document_key": stable_document_key(doc_name),
                    "owner_id": int(owner_id),
                    "category": category or "other",
                    "chunk_index": i,
                    "document_kind": getattr(doc, 'document_kind', None) or 'other',
                    "title": getattr(doc, 'title', None) or doc_name,
                    "language": getattr(doc, 'language', None) or '',
                    "doi": getattr(doc, 'doi_normalized', None) or '',
                    "standard_number": getattr(doc, 'standard_number_normalized', None) or '',
                    "issuing_authority": getattr(doc, 'issuing_authority', None) or '',
                    "authority_status": (
                        getattr(doc, 'authority_status', None) or 'unverified'
                    ),
                    "publication_date": bibliographic.get('publication_date') or '',
                    # Chroma metadata only accepts scalar values, so authors are
                    # stored as a semicolon-delimited string and normalized by
                    # the RAG citation formatter at read time.
                    "authors": authors_metadata,
                    "journal": bibliographic.get('journal') or '',
                    "volume": str(bibliographic.get('volume') or ''),
                    "issue": str(bibliographic.get('issue') or ''),
                    "pages": str(bibliographic.get('pages') or ''),
                    "source_category": provenance.get('source_category', ''),
                    "standard_category": source_metadata.get('standard_category') or '',
                    "source_catalog_status": source_metadata.get('source_catalog_status') or '',
                    **access_metadata,
                }
                if treatment_type:
                    metadata["treatment_type"] = treatment_type
                if pages_meta[i] is not None:
                    metadata["page"] = int(pages_meta[i])
                metadatas.append(metadata)

            chunk_ids = [f"doc-{document_id}-chunk-{i}" for i in range(len(chunks))]

            assign_labels_for_ingestion(
                int(document_id),
                explicit_labels=approved_labels,
                text="\n".join(chunks),
                actor_id=int(owner_id),
            )

            added_count = 0
            if chunks:
                _set_progress(
                    document_id, ingestion_item_id,
                    status=Document.STATUS_PROCESSING,
                    state='processing', stage='indexing', progress=85,
                )
                add_options = {'update_bm25': False} if defer_bm25 else {}
                added_count = vector_store.add_documents(
                    chunks, metadatas, ids=chunk_ids, category=category,
                    **add_options,
                )
            if added_count != len(chunks):
                raise RuntimeError(
                    f"知识库写入不完整: expected={len(chunks)}, actual={added_count}"
                )

            update_options = {'rebuild_indexes': False} if defer_bm25 else {}
            published_count = vector_store.update_document_metadata(
                int(document_id),
                vector_access_metadata(visibility_scope, approved_labels),
                owner_id=int(owner_id),
                **update_options,
            )
            if published_count != len(chunks):
                raise RuntimeError(
                    f"知识库发布不完整: expected={len(chunks)}, actual={published_count}"
                )

            # 更新 chunk_count + 推进到 completed
            doc.chunk_count = len(chunks)
            doc.status = Document.STATUS_COMPLETED
            doc.visibility_scope = 'public'
            doc.processing_stage = 'completed'
            doc.failure_code = None
            doc.failure_message = None
            doc.retryable = False
            page_count = len(pages) if isinstance(pages, list) else None
            parser_details = getattr(pages, 'parse_metadata', {})
            doc.parse_metadata = {
                **(getattr(doc, 'parse_metadata', None) or {}),
                **parser_details,
                'page_count': page_count,
                'character_count': sum(len(chunk) for chunk in chunks),
                'chunk_count': len(chunks),
                'retain_derived_pdf': bool(Config.LITERATURE_RETAIN_DERIVED_PDF),
            }
            item = ingestion_item
            batch_finished = False
            if item:
                item.state = 'completed'
                item.stage = 'completed'
                item.progress = 100
                item.failure_code = None
                item.failure_message = None
                item.retryable = False
                item.quality_summary = doc.parse_metadata
                item.finished_at = datetime.now(UTC)
                if item.batch_id:
                    db.session.flush()
                    from framework.upload.literature_batch import refresh_batch_counters
                    batch = refresh_batch_counters(item.batch_id)
                    batch_finished = bool(batch and batch.finished_at)
            # The graph pipeline is deliberately not executed here.  The
            # lightweight outbox row joins the document-completion transaction
            # and is dispatched asynchronously after commit.
            invalidate_document_evidence(
                db.session, document_id=doc.id,
                keep_content_sha256=doc.file_hash,
                reason="document_content_reparsed",
            )
            enqueue_document_indexed(db.session, doc)
            db.session.commit()
            if batch_finished:
                vector_store.rebuild_bm25_indexes()
        except Exception as exc:
            traceback.print_exc()
            try:
                db.session.rollback()
                vector_store.delete_by_document_id(int(document_id), int(owner_id))
                doc = db.session.query(Document).get(document_id)
                if doc:
                    doc.status = Document.STATUS_FAILED
                    doc.processing_stage = 'failed'
                    doc.failure_code = _failure_code(exc)
                    doc.failure_message = _safe_failure_message(exc, file_path)
                    doc.retryable = not isinstance(exc, ValueError)
                item = _get_item(ingestion_item_id, document_id)
                if item:
                    item.state = 'failed'
                    item.stage = 'failed'
                    item.failure_code = _failure_code(exc)
                    item.failure_message = _safe_failure_message(exc, file_path)
                    item.retryable = not isinstance(exc, ValueError)
                    item.finished_at = datetime.now(UTC)
                    if item.batch_id:
                        db.session.flush()
                        from framework.upload.literature_batch import refresh_batch_counters
                        refresh_batch_counters(item.batch_id)
                db.session.commit()
            except Exception:
                traceback.print_exc()


def _set_status(document_id, status):
    doc = db.session.get(Document, document_id)
    if not doc:
        raise RuntimeError(f"文档记录不存在: document_id={document_id}")
    doc.status = status
    db.session.commit()


def _get_item(ingestion_item_id, document_id):
    if ingestion_item_id is None:
        return None
    return db.session.get(IngestionItem, ingestion_item_id)


def _set_progress(document_id, ingestion_item_id, *, status, state, stage, progress):
    _set_status(document_id, status)
    doc = db.session.query(Document).get(document_id)
    if doc:
        doc.processing_stage = stage
    item = _get_item(ingestion_item_id, document_id)
    if item:
        item.state = state
        item.stage = stage
        item.progress = progress
        if item.started_at is None:
            item.started_at = datetime.now(UTC)
    if doc or item:
        db.session.commit()


def _failure_code(exc):
    message = str(exc).lower()
    if 'caj' in message and ('转换器' in message or '转换失败' in message):
        return 'processor_unavailable'
    if isinstance(exc, ValueError) and '没有可索引内容' in str(exc):
        return 'empty_document'
    if isinstance(exc, ValueError) and '审核' in str(exc):
        return 'review_required'
    if 'ocr' in message:
        return 'ocr_failed'
    if '发布不完整' in str(exc) or '写入不完整' in str(exc):
        return 'indexing_incomplete'
    return 'ingestion_failed'


def _safe_failure_message(exc, file_path):
    message = str(exc).replace(str(file_path), '[document]')
    for sensitive in (Config.UPLOAD_FOLDER, Config.CAJ_CONVERTER_PATH):
        if sensitive:
            message = message.replace(str(sensitive), '[redacted]')
    return message[:1000]
