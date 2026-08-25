"""异步入库 worker：fire-and-forget 提交 + 状态机跟踪。

状态机: pending(0) → processing(2) → completed(1) 或 failed(3)。
worker 线程内推送独立 Flask app context（Flask-SQLAlchemy 需要）。
"""
from __future__ import annotations
import concurrent.futures
import traceback

from framework.models.user import db
from framework.models.document import Document
from framework.upload.document_parser import parse_document
from framework.upload.chunker import split_text
from framework.vector_store.chroma_store import vector_store
from framework.api.app import create_app

# 模块级 worker：与 data_trigger.py 的 ThreadPoolExecutor 模式同源
_WORKER = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="ingest"
)


def submit_ingest(document_id, file_path, file_type, doc_name, category, treatment_type):
    """非阻塞提交入库任务；立即返回。

    上传路由调用本函数后立即返回 202，状态机由 worker 内部推进。
    """
    _WORKER.submit(
        _ingest,
        document_id, file_path, file_type, doc_name, category, treatment_type,
    )


def _ingest(document_id, file_path, file_type, doc_name, category, treatment_type):
    """入库 worker 主体。异常时记录 traceback 并推进到 failed，避免文档永久停留 processing。"""
    # 在 worker 线程内推送 app context（Flask-SQLAlchemy 需要）
    app = create_app()
    with app.app_context():
        try:
            _set_status(document_id, Document.STATUS_PROCESSING)
            # 解析（parse_document 内部已调用 clean_text）
            pages = parse_document(file_path, file_type, page_aware=True)
            # 切分：page_aware 返回 List[(chunk, page)]；其他格式返回 str
            if isinstance(pages, list) and pages and isinstance(pages[0], tuple):
                chunks_with_pages = _split_with_pages(pages)
                chunks = [c for c, _ in chunks_with_pages]
                pages_meta = [p for _, p in chunks_with_pages]
            else:
                # 非分页格式（txt/docx/xlsx）回退到普通切分
                chunks = split_text(pages or "")
                pages_meta = [None] * len(chunks)

            metadatas = [{
                "source": doc_name,
                "category": category,
                "treatment_type": treatment_type,
                "chunk_index": i,
                "page": pages_meta[i],
            } for i in range(len(chunks))]

            added_count = 0
            if chunks:
                added_count = vector_store.add_documents(chunks, metadatas, category=category)

            # 更新 chunk_count + 推进到 completed
            doc = db.session.query(Document).get(document_id)
            if doc:
                doc.chunk_count = len(chunks)
                doc.status = Document.STATUS_COMPLETED
                db.session.commit()
        except Exception:
            traceback.print_exc()
            try:
                doc = db.session.query(Document).get(document_id)
                if doc:
                    doc.status = Document.STATUS_FAILED
                    db.session.commit()
            except Exception:
                traceback.print_exc()


def _split_with_pages(pages):
    """临时包装：Task 7 完成后改为直接调用 chunker.split_text_with_pages。

    本函数在 Task 5 阶段返回 [(chunk, page)] 占位，Task 7 替换为真实切分。
    """
    # 占位：每页整体作为一个 chunk（Task 7 替换为 split_text_with_pages）
    result = []
    for page_num, page_text in pages:
        for c in split_text(page_text or ""):
            result.append((c, page_num))
    return result


def _set_status(document_id, status):
    doc = db.session.query(Document).get(document_id)
    if doc:
        doc.status = status
        db.session.commit()
