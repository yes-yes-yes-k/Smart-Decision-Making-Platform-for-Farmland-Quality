import os
import json
import re
from datetime import date, datetime, UTC
from flask import Blueprint, current_app, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import and_, inspect, or_
from sqlalchemy.exc import IntegrityError
from framework.config import Config
from framework.models.document import Document
from framework.models.document_label import DocumentLabel
from framework.models.ingestion import IngestionBatch, IngestionItem
from framework.models.knowledge_graph import KnowledgeGraphExtractionJob
from framework.models.data_file import DataFile
from framework.models.user import db, User
from framework.knowledge.service import approved_label_codes, vector_access_metadata
from framework.knowledge.taxonomy import (
    DOMAIN_CODES, DOMAIN_TAXONOMY, expand_with_parent_domains,
    label_level, normalize_label_codes, parent_domain,
)
from framework.upload.file_upload import (
    UploadValidationError, allowed_file, get_file_type, save_uploaded_file,
    validate_file_content,
)
from framework.upload.document_parser import caj_converter_is_available
from framework.upload import ingestion_worker
from framework.upload.literature_batch import (
    BatchValidationError, execute_manifest, preflight_manifest,
    refresh_batch_counters,
)
from framework.vector_store.chroma_store import vector_store

docs_bp = Blueprint('docs', __name__)

DATA_CATEGORIES = ['raw_data', 'improved_data']
DOCUMENT_KINDS = {
    'academic_paper', 'standard', 'policy', 'method_guideline', 'other',
}
AUTHORITY_STATUSES = {
    'unverified', 'reference_only', 'verified_current', 'superseded', 'draft',
}


def _current_user():
    return db.session.get(User, int(get_jwt_identity()))


def _upload_path(relative_path):
    return os.path.join(
        current_app.config.get('UPLOAD_FOLDER', Config.UPLOAD_FOLDER), relative_path,
    )


def _parse_domain_labels():
    values = request.form.getlist('domain_labels')
    if len(values) == 1:
        raw = values[0].strip()
        if raw.startswith('['):
            values = json.loads(raw)
        else:
            values = raw.split(',')
    labels = normalize_label_codes(values)
    non_domain_labels = [label for label in labels if label not in DOMAIN_CODES]
    if non_domain_labels:
        raise ValueError(
            "domain_labels 仅支持一级领域: " + ", ".join(non_domain_labels)
        )
    return labels


def _admin_required():
    user = _current_user()
    return user if user and user.is_admin() else None


def _error(error_code, message, status_code):
    return jsonify({
        "status": "error", "error_code": error_code, "message": message,
    }), status_code


def _parse_json_string_array(field_name):
    raw = request.form.get(field_name)
    if raw in (None, ''):
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} 必须是 JSON 字符串数组") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} 必须是 JSON 字符串数组")
    return [item.strip() for item in value if item.strip()]


def _normalize_doi(value):
    doi = (value or '').strip().lower()
    doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi)
    doi = re.sub(r'^doi:\s*', '', doi)
    return doi or None


def _normalize_standard_number(value):
    normalized = re.sub(r'\s+', '', (value or '').strip()).upper()
    return normalized or None


def _parse_literature_metadata():
    document_kind = request.form.get('document_kind', 'other').strip().lower()
    if document_kind not in DOCUMENT_KINDS:
        raise ValueError("document_kind 不受支持")
    authors = _parse_json_string_array('authors')
    cross_categories = _parse_json_string_array('cross_categories')
    publication_date = request.form.get('publication_date') or None
    if publication_date:
        try:
            date.fromisoformat(publication_date)
        except ValueError as exc:
            raise ValueError("publication_date 必须是 ISO 8601 日期") from exc
    idempotency_key = (request.form.get('idempotency_key') or '').strip() or None
    if idempotency_key and len(idempotency_key) > 128:
        raise ValueError("idempotency_key 长度不能超过 128")
    return {
        'document_kind': document_kind,
        'title': (request.form.get('title') or '').strip() or None,
        'language': (request.form.get('language') or '').strip() or None,
        'doi_normalized': _normalize_doi(request.form.get('doi')),
        'standard_number_normalized': _normalize_standard_number(
            request.form.get('standard_number')
        ),
        'issuing_authority': (
            request.form.get('issuing_authority') or ''
        ).strip() or None,
        'bibliographic_metadata': {
            'authors': authors,
            'journal': (request.form.get('journal') or '').strip() or None,
            'publication_date': publication_date,
        },
        'provenance_metadata': {
            'source_url': (request.form.get('source_url') or '').strip() or None,
            'source_category': (
                request.form.get('source_category') or ''
            ).strip() or None,
            'cross_categories': cross_categories,
        },
        'idempotency_key': idempotency_key,
    }


def _latest_ingestion(document_id):
    return IngestionItem.query.filter_by(document_id=document_id).order_by(
        IngestionItem.attempt_no.desc(), IngestionItem.id.desc(),
    ).first()


def _knowledge_graph_status(document):
    """Return a client-safe status view with no extractor output or failure text."""
    job = None
    if inspect(db.engine).has_table(KnowledgeGraphExtractionJob.__tablename__):
        job = KnowledgeGraphExtractionJob.query.filter_by(
            document_id=document.id,
        ).order_by(
            KnowledgeGraphExtractionJob.created_at.desc(),
            KnowledgeGraphExtractionJob.id.desc(),
        ).first()
    if job is None:
        from framework.knowledge_graph.jobs import document_is_graph_eligible

        return {
            'state': (
                'not_started' if document_is_graph_eligible(document)
                else 'not_eligible'
            ),
            'latest_job_id': None,
            'schema_version': None,
            'backend_name': None,
            'extractor_version': None,
            'retryable': False,
            'failure_code': None,
        }
    return {
        'state': job.state,
        'latest_job_id': job.id,
        'schema_version': job.schema_version,
        'backend_name': job.backend_name,
        'extractor_version': job.extractor_version,
        'retryable': bool(job.retryable),
        'failure_code': job.failure_code,
    }


def _ingestion_response(document, item=None):
    item = item or _latest_ingestion(document.id)
    if item:
        ingestion = item.to_dict()
    else:
        ingestion = {
            'document_id': document.id,
            'state': 'completed' if document.status == Document.STATUS_COMPLETED else 'pending',
            'stage': document.processing_stage,
            'progress': 100 if document.status == Document.STATUS_COMPLETED else 0,
            'review_status': document.review_status,
            'failure_code': document.failure_code,
            'failure_message': document.failure_message,
            'retryable': bool(document.retryable),
        }
    ingestion['status_url'] = f"/api/v1/docs/{document.id}/ingestion"
    return {
        'document': document.to_dict(),
        'ingestion': ingestion,
        'knowledge_graph': _knowledge_graph_status(document),
    }


def _submit_document_ingestion(document, item, approved_labels):
    try:
        ingestion_worker.submit_ingest(
            document_id=document.id,
            file_path=_upload_path(document.file_path),
            file_type=document.file_type,
            doc_name=document.doc_name,
            category=document.category,
            treatment_type=document.treatment_type,
            owner_id=document.create_by,
            visibility_scope='public',
            domain_labels=approved_labels,
            ingestion_item_id=item.id if item else None,
        )
        return True
    except ingestion_worker.QueueCapacityExceeded:
        document.status = Document.STATUS_FAILED
        document.processing_stage = 'failed'
        document.failure_code = 'queue_capacity_exceeded'
        document.failure_message = '文献入库队列已满，请稍后重试'
        document.retryable = True
        if item:
            item.state = 'failed'
            item.stage = 'failed'
            item.failure_code = 'queue_capacity_exceeded'
            item.failure_message = document.failure_message
            item.retryable = True
            item.finished_at = datetime.now(UTC)
        db.session.commit()
        return False

@docs_bp.route('/', methods=['GET'])
@jwt_required()
def get_documents():
    user_id = get_jwt_identity()
    user = _current_user()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    category = request.args.get('category')

    category_list = [c.strip() for c in category.split(',') if c.strip()] if category else []

    # 数据文件分类（raw_data / improved_data）查 DataFile 表
    requested_data_categories = [c for c in category_list if c in DATA_CATEGORIES]
    if requested_data_categories:
        query = DataFile.query.filter_by(create_by=user_id)
        query = query.filter(DataFile.category.in_(requested_data_categories))
        query = query.order_by(DataFile.create_time.desc())
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)
        return jsonify({
            "status": "ok",
            "data": {
                "list": [f.to_dict() for f in pagination.items],
                "total": pagination.total
            }
        })

    # 文档分类查 Document 表，排除数据文件分类
    query = Document.query.filter(or_(
        Document.create_by == int(user_id),
        Document.visibility_scope == 'public',
    ))
    query = query.filter(Document.category.notin_(DATA_CATEGORIES))
    doc_categories = [c for c in category_list if c not in DATA_CATEGORIES]
    domain_categories = [c for c in doc_categories if c in DOMAIN_CODES]
    legacy_categories = [c for c in doc_categories if c not in DOMAIN_CODES]
    category_conditions = []
    if domain_categories:
        query = query.outerjoin(DocumentLabel)
        category_conditions.append(and_(
            DocumentLabel.review_status == DocumentLabel.STATUS_APPROVED,
            DocumentLabel.label_code.in_(domain_categories),
        ))
    if legacy_categories:
        category_conditions.append(Document.category.in_(legacy_categories))
    if category_conditions:
        query = query.filter(or_(*category_conditions))
    query = query.distinct()
    query = query.order_by(Document.create_time.desc())

    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "status": "ok",
        "data": {
            "list": [d.to_dict(include_pending=bool(user and user.is_admin())) for d in pagination.items],
            "total": pagination.total
        }
    })

@docs_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_document():
    user_id = get_jwt_identity()
    saved_path = None
    try:
        if 'file' not in request.files:
            return _error('file_required', '未选择文件', 400)

        file = request.files['file']
        if file.filename == '':
            return _error('file_required', '未选择文件', 400)

        if not allowed_file(file.filename):
            return _error('unsupported_file_type', '不支持的文件类型', 415)

        category = request.form.get('category', 'other')
        treatment_type = request.form.get('treatment_type')
        is_data_file = category in DATA_CATEGORIES
        visibility_scope = request.form.get('visibility_scope', 'public').strip().lower()
        if not is_data_file and visibility_scope not in {'', 'public'}:
            return _error(
                'visibility_not_configurable',
                '审核通过的文献统一发布到公共知识库，不支持私有发布',
                422,
            )
        try:
            domain_labels = _parse_domain_labels()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return _error('invalid_metadata', str(exc), 422)
        if not is_data_file and not domain_labels:
            return _error(
                'domain_label_required',
                '文献上传必须选择至少一个一级领域标签',
                422,
            )
        try:
            metadata = _parse_literature_metadata() if not is_data_file else {}
        except ValueError as exc:
            return _error('invalid_metadata', str(exc), 422)

        new_filename, file_path, file_hash = save_uploaded_file(file)
        saved_path = file_path
        file_type = get_file_type(file.filename)
        try:
            validate_file_content(file_path, file_type)
        except UploadValidationError as exc:
            os.remove(file_path)
            saved_path = None
            return _error(exc.error_code, str(exc), exc.status_code)

        if file_type == 'caj':
            with open(file_path, 'rb') as stream:
                is_pdf_payload = stream.read(5) == b'%PDF-'
            if not is_pdf_payload and not caj_converter_is_available(
                Config.CAJ_CONVERTER_PATH
            ):
                os.remove(file_path)
                saved_path = None
                return _error(
                    'processor_unavailable',
                    'CAJ 转换器当前不可用，请稍后重试或联系管理员',
                    503,
                )

        if is_data_file:
            existing = Document.query.filter_by(
                file_hash=file_hash, create_by=user_id,
            ).first()
        else:
            idempotency_key = metadata.get('idempotency_key')
            existing_idempotent = None
            if idempotency_key:
                existing_idempotent = Document.query.filter_by(
                    create_by=int(user_id), idempotency_key=idempotency_key,
                ).first()
            if existing_idempotent:
                os.remove(file_path)
                saved_path = None
                if existing_idempotent.file_hash != file_hash:
                    return _error(
                        'idempotency_conflict',
                        '同一 idempotency_key 已用于不同文件',
                        409,
                    )
                return jsonify({
                    'status': 'ok',
                    'data': _ingestion_response(existing_idempotent),
                    'message': '返回已有上传结果',
                }), 202

            existing = Document.query.filter(
                Document.file_hash == file_hash,
                Document.status == Document.STATUS_COMPLETED,
                Document.visibility_scope == 'public',
            ).first()
            if not existing and metadata.get('doi_normalized'):
                existing = Document.query.filter(
                    Document.doi_normalized == metadata['doi_normalized'],
                    Document.status == Document.STATUS_COMPLETED,
                    Document.visibility_scope == 'public',
                ).first()
            if not existing and metadata.get('standard_number_normalized'):
                existing = Document.query.filter(
                    Document.standard_number_normalized == metadata['standard_number_normalized'],
                    Document.issuing_authority == metadata.get('issuing_authority'),
                    Document.status == Document.STATUS_COMPLETED,
                    Document.visibility_scope == 'public',
                ).first()
            if not existing:
                existing = Document.query.filter(
                    Document.file_hash == file_hash,
                    Document.create_by == int(user_id),
                    Document.status != Document.STATUS_REJECTED,
                ).first()

        if existing:
            os.remove(file_path)
            saved_path = None
            return jsonify({
                'status': 'error',
                'error_code': 'duplicate_document',
                'message': '文档内容已存在',
                'existing_document_id': existing.id,
            }), 409

        if is_data_file:
            data_file = DataFile(
                doc_name=file.filename,
                file_path=new_filename,
                file_type=file_type,
                file_size=os.path.getsize(file_path),
                category=category,
                treatment_type=treatment_type,
                status=1,
                create_by=user_id,
            )
            db.session.add(data_file)
            db.session.commit()
            saved_path = None
            return jsonify({"status": "ok", "data": data_file.to_dict(), "message": "数据文件上传成功"}), 200

        # 文献先持久化为待管理员审核；审核通过后才提交 worker。
        document = Document(
            doc_name=file.filename,
            file_path=new_filename,
            file_type=file_type,
            file_size=os.path.getsize(file_path),
            chunk_count=0,
            status=Document.STATUS_PENDING,
            file_hash=file_hash,
            category=category,
            treatment_type=treatment_type,
            visibility_scope='private',
            processing_stage='awaiting_admin_review',
            review_status=Document.REVIEW_PENDING,
            retryable=False,
            create_by=int(user_id),
            **metadata,
        )
        db.session.add(document)
        db.session.flush()
        for label_code in domain_labels:
            db.session.add(DocumentLabel(
                document_id=document.id,
                label_code=label_code,
                label_level=label_level(label_code),
                parent_code=parent_domain(label_code),
                review_status=DocumentLabel.STATUS_PENDING,
                assignment_source=DocumentLabel.SOURCE_MANUAL,
                create_by=int(user_id),
            ))
        item = IngestionItem(
            document_id=document.id,
            attempt_no=1,
            source_hash=file_hash,
            idempotency_key=metadata.get('idempotency_key'),
            state='pending',
            stage='awaiting_admin_review',
            progress=0,
            review_status='pending',
            submitted_domain_labels=domain_labels,
            config_snapshot={
                'retain_derived_pdf': Config.LITERATURE_RETAIN_DERIVED_PDF,
            },
        )
        db.session.add(item)
        db.session.commit()
        saved_path = None

        return jsonify({
            'status': 'ok',
            'data': _ingestion_response(document, item),
            'message': '文献上传成功，等待管理员审核',
        }), 202

    except IntegrityError:
        db.session.rollback()
        if saved_path and os.path.exists(saved_path):
            os.remove(saved_path)
        return _error('idempotency_conflict', '幂等键或文档记录冲突', 409)
    except Exception as e:
        db.session.rollback()
        if saved_path and os.path.exists(saved_path):
            os.remove(saved_path)
        import traceback
        traceback.print_exc()
        return _error('upload_failed', '上传处理失败，请稍后重试', 500)


@docs_bp.route('/reviews', methods=['GET'])
@jwt_required()
def get_literature_reviews():
    if not _admin_required():
        return _error('forbidden', '权限不足', 403)
    state = request.args.get('state', Document.REVIEW_PENDING)
    if state not in {
        Document.REVIEW_PENDING, Document.REVIEW_APPROVED, Document.REVIEW_REJECTED,
    }:
        return _error('invalid_review_state', '无效审核状态', 400)
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    pagination = Document.query.filter_by(review_status=state).order_by(
        Document.create_time.asc(), Document.id.asc(),
    ).paginate(page=page, per_page=page_size, error_out=False)
    return jsonify({
        'status': 'ok',
        'data': {
            'list': [doc.to_dict(include_pending=True) for doc in pagination.items],
            'total': pagination.total,
        },
    })


@docs_bp.route('/batches', methods=['POST'])
@jwt_required()
def create_literature_batch():
    admin = _admin_required()
    if not admin:
        return _error('forbidden', '只有管理员可以创建文献批次', 403)
    payload = request.get_json(silent=True) or {}
    staging_token = str(payload.get('staging_token') or '').strip()
    manifest_path = str(payload.get('manifest_path') or '').strip()
    if not staging_token or not manifest_path:
        return _error(
            'invalid_manifest', 'staging_token 和 manifest_path 为必填项', 422,
        )
    try:
        if bool(payload.get('dry_run', False)):
            report, _ = preflight_manifest(staging_token, manifest_path)
            return jsonify({'status': 'ok', 'data': report})
        batch_key = str(payload.get('batch_key') or '').strip()
        if not batch_key:
            return _error('invalid_manifest', '正式执行必须提供 batch_key', 422)
        batch, created = execute_manifest(
            staging_token=staging_token,
            manifest_relative_path=manifest_path,
            batch_key=batch_key,
            name=str(payload.get('name') or batch_key),
            actor_id=admin.id,
        )
        return jsonify({
            'status': 'ok',
            'data': batch.to_dict(include_items=True),
            'message': '批次已创建' if created else '返回已有批次',
        }), 202 if created else 200
    except BatchValidationError as exc:
        return _error('invalid_manifest', str(exc), 422)


@docs_bp.route('/batches/<int:batch_id>', methods=['GET'])
@jwt_required()
def get_literature_batch(batch_id):
    if not _admin_required():
        return _error('forbidden', '只有管理员可以查看文献批次', 403)
    batch = db.session.get(IngestionBatch, batch_id)
    if not batch:
        return _error('not_found', '批次不存在', 404)
    refresh_batch_counters(batch.id)
    db.session.commit()
    return jsonify({'status': 'ok', 'data': batch.to_dict(include_items=True)})


@docs_bp.route('/batches/<int:batch_id>/retry', methods=['POST'])
@jwt_required()
def retry_literature_batch(batch_id):
    if not _admin_required():
        return _error('forbidden', '只有管理员可以重试文献批次', 403)
    batch = db.session.get(IngestionBatch, batch_id)
    if not batch:
        return _error('not_found', '批次不存在', 404)
    jobs = []
    for previous in list(batch.items):
        if previous.state != 'failed' or not previous.retryable or not previous.document:
            continue
        document = previous.document
        attempt_no = max(
            item.attempt_no for item in document.ingestion_items
        ) + 1
        item = IngestionItem(
            batch_id=batch.id,
            document_id=document.id,
            attempt_no=attempt_no,
            source_relative_path=previous.source_relative_path,
            source_hash=previous.source_hash,
            idempotency_key=previous.idempotency_key,
            state='pending', stage='accepted', progress=0,
            review_status='approved',
            submitted_domain_labels=previous.submitted_domain_labels,
            approved_domain_labels=previous.approved_domain_labels,
            reviewed_by=previous.reviewed_by,
            reviewed_at=previous.reviewed_at,
            config_snapshot=batch.config_snapshot,
        )
        document.status = Document.STATUS_PENDING
        document.processing_stage = 'accepted'
        document.failure_code = None
        document.failure_message = None
        document.retryable = False
        db.session.add(item)
        db.session.flush()
        jobs.append((document, item))
    if not jobs:
        return _error('batch_not_retryable', '批次中没有可重试项目', 409)
    batch.state = 'processing'
    batch.finished_at = None
    db.session.commit()
    submitted_count = 0
    for document, item in jobs:
        if _submit_document_ingestion(
            document, item, item.approved_domain_labels or [],
        ):
            submitted_count += 1
    return jsonify({
        'status': 'ok', 'data': batch.to_dict(include_items=True),
        'message': f'已提交 {submitted_count}/{len(jobs)} 个重试项目',
    }), 202


@docs_bp.route('/batches/<int:batch_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_literature_batch(batch_id):
    if not _admin_required():
        return _error('forbidden', '只有管理员可以取消文献批次', 403)
    batch = db.session.get(IngestionBatch, batch_id)
    if not batch:
        return _error('not_found', '批次不存在', 404)
    cancelled = 0
    for item in batch.items:
        if item.state == 'pending':
            item.state = 'cancelled'
            item.stage = 'cancelled'
            item.progress = 100
            item.finished_at = datetime.now(UTC)
            cancelled += 1
            if item.document and item.document.status == Document.STATUS_PENDING:
                item.document.status = Document.STATUS_FAILED
                item.document.processing_stage = 'cancelled'
                item.document.failure_code = 'cancelled'
                item.document.failure_message = '批次已由管理员取消'
                item.document.retryable = False
    refresh_batch_counters(batch.id)
    if cancelled:
        batch.state = 'cancelled'
    db.session.commit()
    return jsonify({
        'status': 'ok', 'data': batch.to_dict(include_items=True),
        'message': f'已取消 {cancelled} 个尚未开始的项目',
    })


@docs_bp.route('/<int:id>/review', methods=['POST'])
@jwt_required()
def review_literature(id):
    reviewer = _admin_required()
    if not reviewer:
        return _error('forbidden', '只有管理员可以审核文献', 403)
    document = db.session.get(Document, id)
    if not document:
        return _error('not_found', '文档不存在', 404)

    payload = request.get_json(silent=True) or {}
    decision = str(payload.get('decision') or '').strip().lower()
    if decision not in {'approve', 'reject'}:
        return _error('invalid_review_decision', 'decision 仅支持 approve/reject', 422)
    review_key = str(payload.get('idempotency_key') or '').strip() or None
    if not review_key:
        return _error(
            'idempotency_key_required', '管理员审核必须提供 idempotency_key', 422,
        )
    if len(review_key) > 128:
        return _error('invalid_metadata', 'idempotency_key 长度不能超过 128', 422)
    expected_status = (
        Document.REVIEW_APPROVED if decision == 'approve'
        else Document.REVIEW_REJECTED
    )
    if document.review_status != Document.REVIEW_PENDING:
        if (
            document.review_status == expected_status
            and document.review_idempotency_key == review_key
        ):
            return jsonify({
                'status': 'ok', 'data': _ingestion_response(document),
                'message': '返回已有审核结果',
            })
        return _error(
            'review_already_finalized', '审核结果已终结，不能通过普通接口覆盖', 409,
        )

    note = str(payload.get('review_note') or '').strip() or None
    if note and len(note) > 1000:
        return _error('invalid_metadata', 'review_note 长度不能超过 1000', 422)
    item = _latest_ingestion(document.id)
    now = datetime.now(UTC)

    if decision == 'reject':
        if not note:
            return _error('review_note_required', '驳回时必须填写审核原因', 422)
        document.review_status = Document.REVIEW_REJECTED
        document.reviewed_by = reviewer.id
        document.reviewed_at = now
        document.review_note = note
        document.review_idempotency_key = review_key
        document.status = Document.STATUS_REJECTED
        document.processing_stage = 'rejected'
        document.failure_code = None
        document.failure_message = None
        document.retryable = False
        for label in document.labels:
            if label.review_status == DocumentLabel.STATUS_PENDING:
                label.reject(reviewer.id)
        if item:
            item.review_status = 'rejected'
            item.reviewed_by = reviewer.id
            item.reviewed_at = now
            item.review_note = note
            item.state = 'rejected'
            item.stage = 'rejected'
            item.progress = 100
            item.finished_at = now
        db.session.commit()
        return jsonify({
            'status': 'ok', 'data': _ingestion_response(document, item),
            'message': '文献已驳回',
        })

    raw_labels = payload.get('domain_labels')
    if raw_labels is None:
        raw_labels = [
            label.label_code for label in document.labels
            if label.review_status == DocumentLabel.STATUS_PENDING
            and label.label_level == 'domain'
        ]
    if not isinstance(raw_labels, list):
        return _error('invalid_metadata', 'domain_labels 必须是字符串数组', 422)
    try:
        approved_labels = normalize_label_codes(raw_labels)
    except (TypeError, ValueError) as exc:
        return _error('invalid_metadata', str(exc), 422)
    approved_labels = [label for label in approved_labels if label in DOMAIN_CODES]
    if not approved_labels:
        return _error(
            'domain_label_required', '批准时必须确认至少一个一级领域标签', 422,
        )

    authority_status = str(
        payload.get('authority_status') or document.authority_status or 'unverified'
    ).strip().lower()
    if authority_status not in AUTHORITY_STATUSES:
        return _error('invalid_metadata', 'authority_status 不受支持', 422)
    authority_source = str(payload.get('authority_verification_source') or '').strip()
    if authority_status == 'verified_current' and not authority_source:
        return _error(
            'authority_source_required',
            '确认现行有效时必须提供 authority_verification_source',
            422,
        )
    if (
        document.document_kind not in {'standard', 'policy', 'method_guideline'}
        and authority_status != 'unverified'
    ):
        return _error(
            'invalid_metadata', '仅标准、政策或方法指南可设置权威状态', 422,
        )

    assignments = {label.label_code: label for label in document.labels}
    for code, label in assignments.items():
        if label.label_level != 'domain':
            continue
        if code in approved_labels:
            label.assignment_source = DocumentLabel.SOURCE_MANUAL
            label.approve(reviewer.id)
        elif label.review_status == DocumentLabel.STATUS_PENDING:
            label.reject(reviewer.id)
    for code in approved_labels:
        if code not in assignments:
            row = DocumentLabel(
                document_id=document.id,
                label_code=code,
                label_level='domain',
                assignment_source=DocumentLabel.SOURCE_MANUAL,
                create_by=reviewer.id,
            )
            row.approve(reviewer.id)
            db.session.add(row)

    document.review_status = Document.REVIEW_APPROVED
    document.reviewed_by = reviewer.id
    document.reviewed_at = now
    document.review_note = note
    document.review_idempotency_key = review_key
    document.authority_status = authority_status
    provenance = dict(document.provenance_metadata or {})
    if authority_status != 'unverified':
        provenance['authority_verification'] = {
            'source': authority_source or None,
            'reviewed_by': reviewer.id,
            'reviewed_at': now.isoformat(),
        }
    document.provenance_metadata = provenance
    document.status = Document.STATUS_PENDING
    document.processing_stage = 'accepted'
    document.failure_code = None
    document.failure_message = None
    document.retryable = False
    if item:
        item.review_status = 'approved'
        item.approved_domain_labels = approved_labels
        item.reviewed_by = reviewer.id
        item.reviewed_at = now
        item.review_note = note
        item.state = 'pending'
        item.stage = 'accepted'
        item.progress = 0
    db.session.commit()

    if not _submit_document_ingestion(document, item, approved_labels):
        return jsonify({
            'status': 'error',
            'error_code': 'queue_capacity_exceeded',
            'message': '文献入库队列已满，请稍后重试',
            'data': _ingestion_response(document, item),
        }), 503
    return jsonify({
        'status': 'ok', 'data': _ingestion_response(document, item),
        'message': '审核通过，已提交入库处理',
    })


@docs_bp.route('/<int:id>/ingestion', methods=['GET'])
@jwt_required()
def get_ingestion_status(id):
    user_id = int(get_jwt_identity())
    user = _current_user()
    document = db.session.get(Document, id)
    if not document or (
        document.create_by != user_id and not (user and user.is_admin())
    ):
        return _error('not_found', '文档不存在', 404)
    return jsonify({
        'status': 'ok', 'data': _ingestion_response(document),
    })


@docs_bp.route('/<int:id>/retry', methods=['POST'])
@jwt_required()
def retry_ingestion(id):
    user_id = int(get_jwt_identity())
    user = _current_user()
    document = db.session.get(Document, id)
    if not document or (
        document.create_by != user_id and not (user and user.is_admin())
    ):
        return _error('not_found', '文档不存在', 404)
    if document.status != Document.STATUS_FAILED or not document.retryable:
        return _error('ingestion_not_retryable', '当前文档不可重试', 409)
    if document.review_status != Document.REVIEW_APPROVED:
        return _error('review_required', '文档尚未通过管理员审核', 409)

    previous = _latest_ingestion(document.id)
    attempt_no = (previous.attempt_no if previous else 0) + 1
    approved_labels = [
        code for code in approved_label_codes(document.id) if code in DOMAIN_CODES
    ]
    item = IngestionItem(
        document_id=document.id,
        attempt_no=attempt_no,
        source_hash=document.file_hash,
        state='pending',
        stage='accepted',
        progress=0,
        review_status='approved',
        submitted_domain_labels=approved_labels,
        approved_domain_labels=approved_labels,
        reviewed_by=document.reviewed_by,
        reviewed_at=document.reviewed_at,
        config_snapshot={
            'retain_derived_pdf': Config.LITERATURE_RETAIN_DERIVED_PDF,
        },
    )
    document.status = Document.STATUS_PENDING
    document.processing_stage = 'accepted'
    document.failure_code = None
    document.failure_message = None
    document.retryable = False
    db.session.add(item)
    db.session.commit()
    if not _submit_document_ingestion(document, item, approved_labels):
        return jsonify({
            'status': 'error',
            'error_code': 'queue_capacity_exceeded',
            'message': '文献入库队列已满，请稍后重试',
            'data': _ingestion_response(document, item),
        }), 503
    return jsonify({
        'status': 'ok', 'data': _ingestion_response(document, item),
        'message': '已重新提交入库处理',
    }), 202

@docs_bp.route('/<int:id>', methods=['GET'])
@jwt_required()
def get_document(id):
    user_id = get_jwt_identity()
    user = _current_user()

    document = Document.query.filter(
        Document.id == id,
        or_(Document.create_by == int(user_id), Document.visibility_scope == 'public'),
    ).first()
    if document:
        return jsonify({
            "status": "ok",
            "data": document.to_dict(include_pending=bool(user and user.is_admin())),
        })

    data_file = DataFile.query.filter_by(id=id, create_by=user_id).first()
    if data_file:
        return jsonify({"status": "ok", "data": data_file.to_dict()})

    return jsonify({"status": "error", "message": "文档不存在"}), 404


@docs_bp.route('/taxonomy', methods=['GET'])
@jwt_required()
def get_taxonomy():
    return jsonify({"status": "ok", "data": DOMAIN_TAXONOMY})


@docs_bp.route('/label-reviews', methods=['GET'])
@jwt_required()
def get_label_reviews():
    if not _admin_required():
        return jsonify({"status": "error", "message": "权限不足"}), 403
    status = request.args.get('status', DocumentLabel.STATUS_PENDING)
    if status not in {
        DocumentLabel.STATUS_PENDING,
        DocumentLabel.STATUS_APPROVED,
        DocumentLabel.STATUS_REJECTED,
    }:
        return jsonify({"status": "error", "message": "无效审核状态"}), 400
    level = request.args.get('level', 'domain')
    if level not in {'domain', 'topic', 'all'}:
        return jsonify({"status": "error", "message": "level 仅支持 domain/topic/all"}), 400
    query = DocumentLabel.query.filter_by(review_status=status)
    if level != 'all':
        query = query.filter_by(label_level=level)
    rows = query.order_by(
        DocumentLabel.confidence.desc(), DocumentLabel.id.asc(),
    ).all()
    return jsonify({
        "status": "ok",
        "data": [{**row.to_dict(), "doc_name": row.document.doc_name} for row in rows],
    })


@docs_bp.route('/<int:id>/labels', methods=['PUT'])
@jwt_required()
def review_document_labels(id):
    reviewer = _admin_required()
    if not reviewer:
        return jsonify({"status": "error", "message": "权限不足"}), 403
    document = db.session.get(Document, id)
    if not document:
        return jsonify({"status": "error", "message": "文档不存在"}), 404
    payload = request.get_json(silent=True) or {}
    try:
        approved = expand_with_parent_domains(payload.get('approved_labels') or [])
        rejected = normalize_label_codes(payload.get('rejected_labels') or [])
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    if set(approved) & set(rejected):
        return jsonify({"status": "error", "message": "同一标签不能同时通过和驳回"}), 400

    assignments = {label.label_code: label for label in document.labels}
    for code in approved:
        row = assignments.get(code)
        if row is None:
            row = DocumentLabel(
                document_id=document.id,
                label_code=code,
                label_level=label_level(code),
                parent_code=parent_domain(code),
                assignment_source=DocumentLabel.SOURCE_MANUAL,
                create_by=reviewer.id,
            )
            db.session.add(row)
            assignments[code] = row
        row.assignment_source = DocumentLabel.SOURCE_MANUAL
        row.approve(reviewer.id)
    for code in rejected:
        row = assignments.get(code)
        if row is None:
            row = DocumentLabel(
                document_id=document.id,
                label_code=code,
                label_level=label_level(code),
                parent_code=parent_domain(code),
                assignment_source=DocumentLabel.SOURCE_MANUAL,
                create_by=reviewer.id,
            )
            db.session.add(row)
            assignments[code] = row
        row.reject(reviewer.id)
    db.session.commit()

    metadata = vector_access_metadata(
        document.visibility_scope, approved_label_codes(document.id),
    )
    vector_store.update_document_metadata(
        document.id, metadata, owner_id=document.create_by,
    )
    db.session.refresh(document)
    return jsonify({"status": "ok", "data": document.to_dict(include_pending=True)})

@docs_bp.route('/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_document(id):
    user_id = get_jwt_identity()
    user = _current_user()

    # 先查 Document 表
    document = Document.query.filter_by(id=id, create_by=user_id).first()
    if document:
        if (
            document.status == Document.STATUS_COMPLETED
            and document.visibility_scope == 'public'
            and not (user and user.is_admin())
        ):
            return _error(
                'public_document_managed_by_admin',
                '已发布公共文献只能由管理员撤下',
                403,
            )
        lifecycle = None
        if inspect(db.engine).has_table('kg_candidate_evidence'):
            from framework.knowledge_graph.evidence_lifecycle import (
                invalidate_document_evidence,
            )
            lifecycle = invalidate_document_evidence(
                db.session, document_id=document.id,
                reason='document_withdrawn',
            )

        try:
            vector_store.delete_by_document_id(document.id, int(user_id))
        except Exception:
            pass

        try:
            if document.file_path:
                file_full_path = _upload_path(document.file_path)
                if os.path.exists(file_full_path):
                    os.remove(file_full_path)
            derived_name = (document.parse_metadata or {}).get('derived_pdf_name')
            if derived_name and os.path.basename(derived_name) == derived_name:
                derived_path = _upload_path(os.path.join('derived', derived_name))
                if os.path.exists(derived_path):
                    os.remove(derived_path)
        except Exception:
            pass

        if lifecycle and (
            lifecycle['relation_evidence_invalidated']
            or lifecycle['claim_evidence_invalidated']
        ):
            document.status = Document.STATUS_REJECTED
            document.review_status = Document.REVIEW_REJECTED
            document.visibility_scope = 'private'
            document.processing_stage = 'withdrawn'
            document.failure_code = 'document_withdrawn'
            document.failure_message = None
            document.retryable = False
            db.session.commit()
            return jsonify({
                "status": "ok", "message": "文档已撤回，图谱证据已失效",
                "knowledge_graph": lifecycle,
            })
        db.session.delete(document)
        db.session.commit()
        return jsonify({"status": "ok", "message": "文档删除成功"})

    # 再查 DataFile 表
    data_file = DataFile.query.filter_by(id=id, create_by=user_id).first()
    if data_file:
        try:
            if data_file.file_path:
                file_full_path = _upload_path(data_file.file_path)
                if os.path.exists(file_full_path):
                    os.remove(file_full_path)
        except Exception:
            pass

        db.session.delete(data_file)
        db.session.commit()
        return jsonify({"status": "ok", "message": "数据文件删除成功"})

    return jsonify({"status": "error", "message": "文档不存在"}), 404
