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
    documents = Document.query.filter_by(create_by=user_id).all()
    return jsonify({"status": "ok", "data": [d.to_dict() for d in documents]})

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

    # 查重：同用户下相同 file_hash 视为重复
    existing = Document.query.filter_by(file_hash=file_hash, create_by=user_id).first()
    if existing:
        os.remove(file_path)
        return jsonify({
            "status": "error",
            "message": "文档内容已存在",
            "existing_document_id": existing.id
        }), 409

    content = parse_document(file_path, file_type)
    chunks = []
    if content:
        chunks = [content[i:i+800] for i in range(0, len(content), 800)]
        metadatas = [{"source": file.filename} for _ in chunks]
        vector_store.add_documents(chunks, metadatas)

    document = Document(
        doc_name=file.filename,
        file_path=new_filename,
        file_type=file_type,
        file_size=os.path.getsize(file_path),
        chunk_count=len(chunks) if content else 0,
        status=1,
        file_hash=file_hash,
        create_by=user_id,
    )
    db.session.add(document)
    db.session.commit()

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
    file_path = os.path.join(Config.UPLOAD_FOLDER, document.file_path)
    try:
        os.remove(file_path)
    except Exception as e:
        print(f"物理文件删除失败，已跳过: {e}")

    return jsonify({"status": "ok", "message": "文档删除成功"})