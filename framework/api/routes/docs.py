import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.models.document import Document
from framework.models.data_file import DataFile
from framework.models.user import db
from framework.upload.file_upload import allowed_file, save_uploaded_file, get_file_type
from framework.upload.document_parser import parse_document
from framework.vector_store.chroma_store import vector_store

docs_bp = Blueprint('docs', __name__)

DATA_CATEGORIES = ['raw_data', 'improved_data']

@docs_bp.route('/', methods=['GET'])
@jwt_required()
def get_documents():
    user_id = get_jwt_identity()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    category = request.args.get('category')

    query = Document.query.filter_by(create_by=user_id)

    query = query.filter(Document.category.notin_(DATA_CATEGORIES))

    if category:
        category_list = [c.strip() for c in category.split(',') if c.strip()]
        if category_list:
            query = query.filter(Document.category.in_(category_list))

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
            return jsonify({"status": "ok", "data": data_file.to_dict(), "message": "数据文件上传成功"})

        content = parse_document(file_path, file_type)
        chunks = []
        if content:
            chunks = [content[i:i+800] for i in range(0, len(content), 800)]
            metadatas = [{"source": file.filename} for _ in chunks]
            added_count = vector_store.add_documents(chunks, metadatas)
            print(f"[上传接口] 向量库添加完成 - 分块数: {len(chunks)}, 成功添加: {added_count}", flush=True)
        else:
            print(f"[上传接口] 文档解析结果为空", flush=True)

        document = Document(
            doc_name=file.filename,
            file_path=new_filename,
            file_type=file_type,
            file_size=os.path.getsize(file_path),
            chunk_count=len(chunks) if content else 0,
            status=1,
            file_hash=file_hash,
            category=category,
            treatment_type=treatment_type,
            create_by=user_id,
        )
        db.session.add(document)
        db.session.commit()
        print(f"[上传接口] 成功 - 文档ID: {document.id}, 文件名: {file.filename}", flush=True)

        return jsonify({"status": "ok", "data": document.to_dict(), "message": "文档上传成功"})

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
