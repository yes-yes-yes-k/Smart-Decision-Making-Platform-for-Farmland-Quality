from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import check_password_hash, generate_password_hash
from framework.models.user import User, db

auth_bp = Blueprint('auth', __name__)
users_bp = Blueprint('users', __name__)

def _admin():
    user_id = get_jwt_identity()
    user = db.session.get(User, int(user_id)) if user_id else None
    return user if user and user.status == 1 and user.is_admin() else None

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "请求参数不能为空"}), 400
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({"status": "error", "message": "用户名和密码不能为空"}), 400
    user = User.query.filter_by(username=username).first()
    if not user or user.status != 1 or user.role not in {'admin', 'user'} or not check_password_hash(user.password, password):
        return jsonify({"status": "error", "message": "用户名或密码错误"}), 401
    access_token = create_access_token(identity=str(user.id))
    return jsonify({"status": "ok", "data": {"token": access_token, "user": user.to_dict()}, "message": "登录成功"})

@auth_bp.route('/register', methods=['POST'])
@jwt_required()
def register():
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id)
    if not current_user or not current_user.is_admin():
        return jsonify({"status": "error", "message": "权限不足"}), 403
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "请求参数不能为空"}), 400
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({"status": "error", "message": "用户名和密码不能为空"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"status": "error", "message": "用户名已存在"}), 400
    role = data.get('role', 'user')
    if role not in {'admin', 'user'}:
        return jsonify({"status": "error", "message": "角色仅支持 admin/user"}), 400
    new_user = User(username=username, password=generate_password_hash(password), nickname=data.get('nickname', username), role=role)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"status": "ok", "data": new_user.to_dict(), "message": "用户创建成功"})

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"status": "error", "message": "用户不存在"}), 404
    if user.status != 1 or user.role not in {'admin', 'user'}:
        return jsonify({"status": "error", "message": "账号不可用或角色无效"}), 403
    return jsonify({"status": "ok", "data": user.to_dict()})

@auth_bp.route('/me', methods=['PUT'])
@jwt_required()
def update_me():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or user.status != 1 or user.role not in {'admin', 'user'}:
        return jsonify({"status": "error", "message": "账号不可用"}), 403
    data = request.get_json(silent=True) or {}
    if 'nickname' in data:
        nickname = str(data['nickname']).strip()
        if len(nickname) > 50:
            return jsonify({"status": "error", "message": "昵称不能超过50个字符"}), 400
        user.nickname = nickname
    db.session.commit()
    return jsonify({"status": "ok", "data": user.to_dict()})

@users_bp.route('', methods=['GET', 'POST'])
@jwt_required()
def users_collection():
    from sqlalchemy import or_
    if not _admin():
        return jsonify({"status": "error", "message": "权限不足"}), 403
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        username, password = str(data.get('username') or '').strip(), str(data.get('password') or '').strip()
        role = str(data.get('role') or 'user').strip()
        if not username or not password or role not in {'admin', 'user'}:
            return jsonify({"status": "error", "message": "用户名、密码必填且角色必须为 admin/user"}), 400
        if User.query.filter_by(username=username).first():
            return jsonify({"status": "error", "message": "用户名已存在"}), 409
        user = User(username=username, password=generate_password_hash(password), nickname=str(data.get('nickname') or username).strip(), role=role)
        db.session.add(user); db.session.commit()
        return jsonify({"status": "ok", "data": user.to_dict()}), 201
    page = max(1, request.args.get('page', 1, type=int))
    page_size = max(1, min(100, request.args.get('page_size', 20, type=int)))
    query = User.query
    keyword = str(request.args.get('keyword') or '').strip()
    if keyword:
        query = query.filter(or_(User.username.contains(keyword), User.nickname.contains(keyword)))
    result = query.order_by(User.id.asc()).paginate(page=page, per_page=page_size, error_out=False)
    return jsonify({"status": "ok", "data": {"list": [u.to_dict() for u in result.items], "total": result.total, "page": page, "page_size": page_size}})

@users_bp.route('/<int:user_id>', methods=['PUT', 'DELETE'])
@jwt_required()
def user_item(user_id):
    actor = _admin()
    if not actor:
        return jsonify({"status": "error", "message": "权限不足"}), 403
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"status": "error", "message": "用户不存在"}), 404
    if request.method == 'DELETE':
        if actor.id == user.id:
            return jsonify({"status": "error", "message": "不能删除当前登录账号"}), 400
        db.session.delete(user); db.session.commit()
        return jsonify({"status": "ok", "message": "用户已删除"})
    data = request.get_json(silent=True) or {}
    if 'role' in data:
        if data['role'] not in {'admin', 'user'}:
            return jsonify({"status": "error", "message": "角色仅支持 admin/user"}), 400
        if user.id == actor.id and data['role'] != 'admin':
            return jsonify({"status": "error", "message": "不能移除自己的管理员权限"}), 400
        user.role = data['role']
    if 'nickname' in data:
        user.nickname = str(data['nickname']).strip()[:50]
    if 'status' in data:
        if data['status'] not in (0, 1):
            return jsonify({"status": "error", "message": "账号状态无效"}), 400
        if user.id == actor.id and data['status'] == 0:
            return jsonify({"status": "error", "message": "不能禁用当前登录账号"}), 400
        user.status = data['status']
    if data.get('password'):
        user.password = generate_password_hash(str(data['password']))
    db.session.commit()
    return jsonify({"status": "ok", "data": user.to_dict()})
