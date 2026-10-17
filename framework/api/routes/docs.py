import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.config import Config
from framework.models.document import Document
from framework.models.data_file import DataFile
from framework.models.user import db
from framework.upload.file_upload import allowed_file, save_uploaded_file, get_file_type
from framework.upload import ingestion_worker
from framework.vector_store.chroma_store import vector_store

docs_bp = Blueprint('docs', __name__)

DATA_CATEGORIES = ['raw_data', 'improved_data']

@docs_bp.route('/', methods=['GET'])
@jwt_required()
def get_documents():
    user_id = get_jwt_identity()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    doc_type = request.args.get('doc_type')
    category = request.args.get('category')

    # 展示分类过滤：传入 doc_type 时按 Document.doc_type 过滤（前端知识库列表）
    if doc_type is not None:
        doc_type_list = [dt.strip() for dt in doc_type.split(',') if dt.strip()] if doc_type else []
        query = Document.query.filter_by(create_by=user_id)
        if doc_type_list:
            query = query.filter(Document.doc_type.in_(doc_type_list))
        query = query.order_by(Document.create_time.desc())
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)
        return jsonify({
            "status": "ok",
            "data": {
                "list": [d.to_dict() for d in pagination.items],
                "total": pagination.total
            }
        })

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

    # 文档分类查 Document 表，排除数据文件分类（兼容旧 category 语义）
    query = Document.query.filter_by(create_by=user_id)
    query = query.filter(Document.category.notin_(DATA_CATEGORIES))
    doc_categories = [c for c in category_list if c not in DATA_CATEGORIES]
    if doc_categories:
        query = query.filter(Document.category.in_(doc_categories))
    query = query.order_by(Document.create_time.desc())

    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "status": "ok",
        "data": {
            "list": [d.to_dict() for d in pagination.items],
            "total": pagination.total
        }
    })

@docs_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_document():
    user_id = get_jwt_identity()
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
            doc_type=request.form.get('doc_type') or 'other',
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

    document = Document.query.filter_by(id=id, create_by=user_id).first()
    if document:
        return jsonify({"status": "ok", "data": document.to_dict()})

    data_file = DataFile.query.filter_by(id=id, create_by=user_id).first()
    if data_file:
        return jsonify({"status": "ok", "data": data_file.to_dict()})

    return jsonify({"status": "error", "message": "文档不存在"}), 404

@docs_bp.route('/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_document(id):
    user_id = get_jwt_identity()

    # 先查 Document 表
    document = Document.query.filter_by(id=id, create_by=user_id).first()
    if document:
        try:
            vector_store.delete_by_source(document.doc_name)
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
