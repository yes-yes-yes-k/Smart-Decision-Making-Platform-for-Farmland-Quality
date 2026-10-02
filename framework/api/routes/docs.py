import os
import json
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import and_, or_
from framework.config import Config
from framework.models.document import Document
from framework.models.document_label import DocumentLabel
from framework.models.data_file import DataFile
from framework.models.user import db, User
from framework.knowledge.service import approved_label_codes, vector_access_metadata
from framework.knowledge.taxonomy import (
    DOMAIN_CODES, DOMAIN_TAXONOMY, expand_with_parent_domains,
    label_level, normalize_label_codes, parent_domain,
)
from framework.upload.file_upload import allowed_file, save_uploaded_file, get_file_type
from framework.upload import ingestion_worker
from framework.vector_store.chroma_store import vector_store

docs_bp = Blueprint('docs', __name__)

DATA_CATEGORIES = ['raw_data', 'improved_data']


def _current_user():
    return db.session.get(User, int(get_jwt_identity()))


def _parse_domain_labels():
    values = request.form.getlist('domain_labels')
    if len(values) == 1:
        raw = values[0].strip()
        if raw.startswith('['):
            values = json.loads(raw)
        else:
            values = raw.split(',')
    return normalize_label_codes(values)


def _admin_required():
    user = _current_user()
    return user if user and user.is_admin() else None

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
    user = _current_user()
    print(f"[上传接口] 请求到达 - user_id: {user_id}, method: {request.method}, path: {request.path}", flush=True)

    try:
        if 'file' not in request.files:
            print(f"[上传接口] 失败 - 未找到文件字段", flush=True)
            return jsonify({"status": "error", "message": "未选择文件"}), 400

        file = request.files['file']
        if file.filename == '':
            print(f"[上传接口] 失败 - 文件名为空", flush=True)
            return jsonify({"status": "error", "message": "未选择文件"}), 400

        if not allowed_file(file.filename):
            print(f"[上传接口] 失败 - 不支持的文件类型: {file.filename}", flush=True)
            return jsonify({"status": "error", "message": "不支持的文件类型"}), 400

        category = request.form.get('category', 'other')
        treatment_type = request.form.get('treatment_type')
        visibility_scope = request.form.get('visibility_scope', 'private').strip().lower()
        if visibility_scope not in {'public', 'private'}:
            return jsonify({"status": "error", "message": "visibility_scope 仅支持 public/private"}), 400
        if visibility_scope == 'public' and (not user or not user.is_admin()):
            return jsonify({"status": "error", "message": "只有管理员可以发布公共知识"}), 403
        try:
            domain_labels = _parse_domain_labels()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400
        print(f"[上传接口] 开始处理 - 文件名: {file.filename}, 大小: {file.content_length}, 分类: {category}, 治理类型: {treatment_type}", flush=True)

        new_filename, file_path, file_hash = save_uploaded_file(file)
        file_type = get_file_type(file.filename)
        print(f"[上传接口] 文件已保存 - 新文件名: {new_filename}, 路径: {file_path}", flush=True)

        # 查重：同用户下相同 file_hash 视为重复
        existing = Document.query.filter_by(file_hash=file_hash, create_by=user_id).first()
        if existing:
            os.remove(file_path)
            print(f"[上传接口] 失败 - 文档内容已存在，file_hash: {file_hash}", flush=True)
            return jsonify({
                "status": "error",
                "message": "文档内容已存在",
                "existing_document_id": existing.id
            }), 409

        if category in DATA_CATEGORIES:
            print(f"[上传接口] 数据文件，存储到 kb_data_file 表", flush=True)
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
            print(f"[上传接口] 数据文件保存成功 - 文件ID: {data_file.id}, 文件名: {file.filename}", flush=True)
            return jsonify({"status": "ok", "data": data_file.to_dict(), "message": "数据文件上传成功"}), 200

        # 文档类：异步 fire-and-forget —— 立即落库 status=PENDING，提交 worker，返回 202
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
            visibility_scope=visibility_scope,
            create_by=user_id,
        )
        db.session.add(document)
        db.session.commit()
        print(f"[上传接口] 文档已入库（待处理） - 文档ID: {document.id}, 文件名: {file.filename}", flush=True)

        ingestion_worker.submit_ingest(
            document_id=document.id,
            file_path=file_path,
            file_type=file_type,
            doc_name=file.filename,
            category=category,
            treatment_type=treatment_type,
            owner_id=int(user_id),
            visibility_scope=visibility_scope,
            domain_labels=domain_labels,
        )

        return jsonify({"status": "ok", "data": document.to_dict(), "message": "文档上传成功，正在后台处理"}), 202

    except Exception as e:
        print(f"[上传接口] 异常 - {type(e).__name__}: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"上传失败: {str(e)}"}), 500

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

    # 先查 Document 表
    document = Document.query.filter_by(id=id, create_by=user_id).first()
    if document:
        try:
            vector_store.delete_by_document_id(document.id, int(user_id))
        except Exception:
            pass

        try:
            if document.file_path:
                file_full_path = os.path.join(Config.UPLOAD_FOLDER, document.file_path)
                if os.path.exists(file_full_path):
                    os.remove(file_full_path)
        except Exception:
            pass

        db.session.delete(document)
        db.session.commit()
        return jsonify({"status": "ok", "message": "文档删除成功"})

    # 再查 DataFile 表
    data_file = DataFile.query.filter_by(id=id, create_by=user_id).first()
    if data_file:
        try:
            if data_file.file_path:
                file_full_path = os.path.join(Config.UPLOAD_FOLDER, data_file.file_path)
                if os.path.exists(file_full_path):
                    os.remove(file_full_path)
        except Exception:
            pass

        db.session.delete(data_file)
        db.session.commit()
        return jsonify({"status": "ok", "message": "数据文件删除成功"})

    return jsonify({"status": "error", "message": "文档不存在"}), 404
