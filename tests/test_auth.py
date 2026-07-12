"""测试用户认证功能"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib
from framework.auth.jwt import md5_hash, generate_token, get_current_user_id

def test_md5_hash():
    """测试 MD5 哈希"""
    password = "test_password_123"
    hashed = md5_hash(password)
    expected = hashlib.md5(password.encode('utf-8')).hexdigest()
    assert hashed == expected
    assert hashed != password
    print(f"✓ MD5 哈希成功: {hashed}")

def test_md5_hash_empty():
    """测试空密码哈希"""
    hashed = md5_hash("")
    assert hashed == "d41d8cd98f00b204e9800998ecf8427e"
    print("✓ 空密码哈希正确")

def test_md5_hash_consistency():
    """测试哈希一致性"""
    password = "consistent_password"
    hash1 = md5_hash(password)
    hash2 = md5_hash(password)
    assert hash1 == hash2
    print("✓ 哈希一致性验证通过")

def test_user_model_fields():
    """测试用户模型字段定义"""
    from framework.models.user import User
    assert User.__tablename__ == 'sys_user'
    assert hasattr(User, 'username')
    assert hasattr(User, 'password')
    assert hasattr(User, 'role')
    assert hasattr(User, 'status')
    print("✓ 用户模型字段定义正确")

def test_user_to_dict():
    """测试用户模型 to_dict 方法"""
    from framework.models.user import User
    user = User()
    user.id = 1
    user.username = "testuser"
    user.nickname = "测试用户"
    user.role = "admin"
    user.status = 1
    result = user.to_dict()
    assert result["username"] == "testuser"
    assert result["role"] == "admin"
    assert result["status"] == 1
    print("✓ 用户模型 to_dict 方法正常")

def test_user_is_admin():
    """测试管理员判断"""
    from framework.models.user import User
    admin_user = User()
    admin_user.role = "admin"
    assert admin_user.is_admin() is True

    normal_user = User()
    normal_user.role = "user"
    assert normal_user.is_admin() is False
    print("✓ 管理员判断正确")

if __name__ == "__main__":
    test_md5_hash()
    test_md5_hash_empty()
    test_md5_hash_consistency()
    test_user_model_fields()
    test_user_to_dict()
    test_user_is_admin()
    print("\n所有用户认证功能测试通过！")
