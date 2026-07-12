from functools import wraps
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import jsonify
from framework.models.user import User, db

def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user or not user.is_admin():
            return jsonify({"status": "error", "message": "权限不足"}), 403
        return fn(*args, **kwargs)
    return wrapper