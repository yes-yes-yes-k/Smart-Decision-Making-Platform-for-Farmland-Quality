"""迁移 MySQL 数据库表结构

从 org-backend 源项目迁移数据库表结构到统一框架。
此脚本创建所有必要的数据库表。

使用方法:
    python scripts/migrate_mysql.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.config import Config
from framework.models.user import db, User
from framework.models.conversation import Conversation
from framework.models.message import Message
from framework.models.document import Document

def create_tables():
    """创建所有数据库表"""
    from flask import Flask
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        print("✓ 所有数据库表创建成功")

        # 检查表是否存在
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        expected_tables = ['sys_user', 'kb_conversation', 'kb_message', 'kb_document']
        for table in expected_tables:
            if table in tables:
                print(f"  ✓ 表 {table} 存在")
            else:
                print(f"  ✗ 表 {table} 不存在")

def create_default_admin():
    """创建默认管理员账户"""
    from flask import Flask
    import hashlib
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        existing = User.query.filter_by(username='admin').first()
        if existing:
            print("  管理员账户已存在，跳过创建")
            return

        admin = User(
            username='admin',
            password=hashlib.md5('admin123'.encode('utf-8')).hexdigest(),
            nickname='系统管理员',
            role='admin',
            status=1,
        )
        db.session.add(admin)
        db.session.commit()
        print("✓ 默认管理员账户创建成功 (admin/admin123)")

if __name__ == "__main__":
    print("=" * 50)
    print("MySQL 数据库迁移脚本")
    print("=" * 50)

    try:
        create_tables()
    except Exception as e:
        print(f"✗ 创建表失败: {e}")
        print("  请确保 MySQL 服务已启动且配置正确")
        sys.exit(1)

    try:
        create_default_admin()
    except Exception as e:
        print(f"⚠ 创建默认管理员失败: {e}")

    print("\n数据库迁移完成！")
