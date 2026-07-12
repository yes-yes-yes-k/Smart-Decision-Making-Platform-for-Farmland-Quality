import hashlib
from flask_jwt_extended import create_access_token, verify_jwt_in_request, get_jwt_identity

def md5_hash(password: str) -> str:
    return hashlib.md5(password.encode('utf-8')).hexdigest()

def generate_token(user_id: int) -> str:
    return create_access_token(identity=str(user_id))

def get_current_user_id() -> int:
    verify_jwt_in_request()
    return int(get_jwt_identity())