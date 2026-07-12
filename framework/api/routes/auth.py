import hashlib
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from framework.models.user import User, db

auth_bp = Blueprint('auth', __name__)

def md5_hash(password: str) -> str:
    return hashlib.md5(password.encode('utf-8')).hexdigest()

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
    if not user or user.password != md5_hash(password):
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
    new_user = User(username=username, password=md5_hash(password), nickname=data.get('nickname', username), role=data.get('role', 'user'))
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
    return jsonify({"status": "ok", "data": user.to_dict()})