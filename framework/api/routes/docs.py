import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
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

    vector_store.delete_by_source(document.doc_name)
    db.session.delete(document)
    db.session.commit()

    return jsonify({"status": "ok", "message": "文档删除成功"})