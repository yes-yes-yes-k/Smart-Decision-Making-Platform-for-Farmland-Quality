import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.models.data_file import DataFile
from framework.models.user import db
from framework.upload.file_upload import allowed_file, save_uploaded_file, get_file_type

data_files_bp = Blueprint('data_files', __name__)

DATA_CATEGORIES = ['raw_data', 'improved_data']

@data_files_bp.route('/', methods=['GET'])
@jwt_required()
def get_data_files():
    user_id = get_jwt_identity()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    category = request.args.get('category')

    query = DataFile.query.filter_by(create_by=user_id)

    if category:
        category_list = [c.strip() for c in category.split(',') if c.strip()]
        if category_list:
            query = query.filter(DataFile.category.in_(category_list))

    query = query.order_by(DataFile.create_time.desc())

    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "status": "ok",
        "data": {
            "list": [d.to_dict() for d in pagination.items],
            "total": pagination.total
        }
    })

@data_files_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_data_file():
    user_id = get_jwt_identity()
    print(f"[数据文件上传] 请求到达 - user_id: {user_id}", flush=True)

    try:
        if 'file' not in request.files:
            print(f"[数据文件上传] 失败 - 未找到文件字段", flush=True)
            return jsonify({"status": "error", "message": "未选择文件"}), 400

        file = request.files['file']
        if file.filename == '':
            print(f"[数据文件上传] 失败 - 文件名为空", flush=True)
            return jsonify({"status": "error", "message": "未选择文件"}), 400

        if not allowed_file(file.filename):
            print(f"[数据文件上传] 失败 - 不支持的文件类型: {file.filename}", flush=True)
            return jsonify({"status": "error", "message": "不支持的文件类型"}), 400

        category = request.form.get('category', 'raw_data')
        treatment_type = request.form.get('treatment_type')

        if category not in DATA_CATEGORIES:
            print(f"[数据文件上传] 失败 - 无效的数据分类: {category}", flush=True)
            return jsonify({"status": "error", "message": "无效的数据分类"}), 400

        print(f"[数据文件上传] 开始处理 - 文件名: {file.filename}, 大小: {file.content_length}, 分类: {category}, 治理类型: {treatment_type}", flush=True)

        new_filename, file_path = save_uploaded_file(file)
        file_type = get_file_type(file.filename)
        print(f"[数据文件上传] 文件已保存 - 新文件名: {new_filename}, 路径: {file_path}", flush=True)

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
        print(f"[数据文件上传] 成功 - 文件ID: {data_file.id}, 文件名: {file.filename}", flush=True)

        return jsonify({"status": "ok", "data": data_file.to_dict(), "message": "数据文件上传成功"})

    except Exception as e:
        print(f"[数据文件上传] 异常 - {type(e).__name__}: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"上传失败: {str(e)}"}), 500

@data_files_bp.route('/<int:id>', methods=['GET'])
@jwt_required()
def get_data_file(id):
    user_id = get_jwt_identity()
    data_file = DataFile.query.filter_by(id=id, create_by=user_id).first()
    if not data_file:
        return jsonify({"status": "error", "message": "数据文件不存在"}), 404
    return jsonify({"status": "ok", "data": data_file.to_dict()})

@data_files_bp.route('/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_data_file(id):
    user_id = get_jwt_identity()
    data_file = DataFile.query.filter_by(id=id, create_by=user_id).first()
    if not data_file:
        return jsonify({"status": "error", "message": "数据文件不存在"}), 404

    try:
        file_full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', data_file.file_path)
        if os.path.exists(file_full_path):
            os.remove(file_full_path)
            print(f"[数据文件删除] 文件已删除: {file_full_path}", flush=True)
    except Exception as e:
        print(f"[数据文件删除] 删除物理文件失败: {e}", flush=True)

    db.session.delete(data_file)
    db.session.commit()
    print(f"[数据文件删除] 成功 - 文件ID: {id}", flush=True)

    return jsonify({"status": "ok", "message": "数据文件删除成功"})