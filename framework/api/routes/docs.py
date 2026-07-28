import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.config import Config
from framework.models.document import Document
from framework.models.user import db
from framework.upload.file_upload import allowed_file, save_uploaded_file, get_file_type
from framework.upload.document_parser import parse_document
from framework.vector_store.chroma_store import vector_store

docs_bp = Blueprint('docs', __name__)

@docs_bp.route('/', methods=['GET'])
@jwt_required()
def get_documents():
    user_id = get_jwt_identity()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    category = request.args.get('category', '').strip()

    query = Document.query.filter_by(create_by=user_id)

    if category:
        categories = [c.strip() for c in category.split(',') if c.strip()]
        if categories:
            query = query.filter(Document.category.in_(categories))

    query = query.order_by(Document.create_time.desc())
    total = query.count()
    documents = query.offset((page - 1) * page_size).limit(page_size).all()

    return jsonify({
        "status": "ok",
        "data": {
            "list": [d.to_dict() for d in documents],
            "total": total,
            "page": page,
            "page_size": page_size
        }
    })

@docs_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_document():
    user_id = get_jwt_identity()
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    if not allowed_file(file.filename):
        return jsonify({"status": "error", "message": "不支持的文件类型"}), 400

    new_filename, file_path, file_hash = save_uploaded_file(file)
    file_type = get_file_type(file.filename)
    category = request.form.get('category', 'other').strip()
    treatment_type = request.form.get('treatment_type', '').strip() or None

    # 查重：同用户下相同 file_hash 视为重复
    existing = Document.query.filter_by(file_hash=file_hash, create_by=user_id).first()
    if existing:
        os.remove(file_path)
        return jsonify({
            "status": "error",
            "message": "文档内容已存在",
            "existing_document_id": existing.id
        }), 409

    # 数据文件（raw_data / improved_data）不进向量库，仅存数据库
    is_data_file = category in ('raw_data', 'improved_data')

    doc_status = 1
    chunk_count = 0
    fail_reason = None

    if not is_data_file:
        # 文本文档：解析 + 向量化
        try:
            content = parse_document(file_path, file_type)
            if content:
                chunks = [content[i:i+800] for i in range(0, len(content), 800)]
                metadatas = [{"source": file.filename} for _ in chunks]
                vector_store.add_documents(chunks, metadatas)
                chunk_count = len(chunks)
            else:
                # 解析返回空内容（一般不会到这里，解析函数失败会抛异常）
                fail_reason = "解析结果为空"
                doc_status = 2
        except ImportError as e:
            # 依赖缺失：明确告知用户去装包
            print(f"[Upload] 依赖缺失: {file.filename}, 错误: {e}")
            fail_reason = str(e)
            doc_status = 2
        except Exception as e:
            print(f"[Upload] 文档解析/向量化失败: {file.filename}, 错误类型={type(e).__name__}, 错误: {e}")
            fail_reason = f"{type(e).__name__}: {e}"
            doc_status = 2

    document = Document(
        doc_name=file.filename,
        file_path=new_filename,
        file_type=file_type,
        file_size=os.path.getsize(file_path),
        chunk_count=chunk_count,
        status=doc_status,
        file_hash=file_hash,
        create_by=user_id,
        category=category,
        treatment_type=treatment_type,
    )
    db.session.add(document)
    db.session.commit()

    if doc_status == 2:
        # 解析失败时记录原因，但保留文档记录（status=2）便于用户重试或排查
        reason = fail_reason or "未知原因"
        return jsonify({
            "status": "error",
            "message": f"文档解析失败：{reason}",
            "reason": reason,
            "data": document.to_dict()
        }), 500

    return jsonify({"status": "ok", "data": document.to_dict(), "message": "文档上传成功"})

@docs_bp.route('/<int:id>', methods=['GET'])
@jwt_required()
def get_document(id):
    user_id = get_jwt_identity()
    document = Document.query.filter_by(id=id, create_by=user_id).first()
    if not document:
        return jsonify({"status": "error", "message": "文档不存在"}), 404
    return jsonify({"status": "ok", "data": document.to_dict()})

@docs_bp.route('/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_document(id):
    user_id = get_jwt_identity()
    document = Document.query.filter_by(id=id, create_by=user_id).first()
    if not document:
        return jsonify({"status": "error", "message": "文档不存在"}), 404

    # 在数据库删除前保存物理文件路径，避免 commit 后访问 detached 对象
    file_path = os.path.join(Config.UPLOAD_FOLDER, document.file_path)

    # 1. 先删向量库（容错）
    try:
        vector_store.delete_by_source(document.doc_name)
    except Exception as e:
        print(f"向量库删除失败，已跳过: {e}")

    # 2. 再删数据库（事务）
    try:
        db.session.delete(document)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"数据库删除失败: {e}")
        return jsonify({"status": "error", "message": "文档删除失败"}), 500

    # 3. 最后删物理文件（容错）
    try:
        os.remove(file_path)
    except Exception as e:
        print(f"物理文件删除失败，已跳过: {e}")

    return jsonify({"status": "ok", "message": "文档删除成功"})