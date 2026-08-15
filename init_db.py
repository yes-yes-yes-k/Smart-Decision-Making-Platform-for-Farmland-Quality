import sys
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from werkzeug.security import generate_password_hash
from framework.api.app import create_app
from framework.models.user import db, User
import framework.models  # noqa: F401  触发 soil_data 等模型注册，使 db.create_all() 发现新表

app = create_app()

with app.app_context():
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']

    # PostGIS 扩展初始化（仅 PostgreSQL 路径）
    if db_uri.startswith('postgresql'):
        try:
            db.session.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            db.session.commit()
            print("[初始化] PostGIS 扩展已就绪")
        except ProgrammingError as e:
            print(f"[错误] PostGIS 扩展初始化失败：{e}", file=sys.stderr)
            print("[提示] 请在 PostgreSQL 实例安装 postgis 包", file=sys.stderr)
            print("[提示] 安装后重新运行 python init_db.py", file=sys.stderr)
            db.session.rollback()
            sys.exit(1)

    db.drop_all()
    db.create_all()
    
    admin = User(
        username='admin',
        password=generate_password_hash('admin123'),
        nickname='管理员',
        role='admin',
        status=1
    )
    db.session.add(admin)
    
    user = User(
        username='user',
        password=generate_password_hash('user123'),
        nickname='普通用户',
        role='user',
        status=1
    )
    db.session.add(user)
    
    db.session.commit()
    print("[初始化] 数据库表结构创建完成")
    print("[初始化] 管理员用户已创建: admin / admin123")
    print("[初始化] 普通用户已创建: user / user123")
    print("[提示] 运行 'python start_http_server.py' 启动服务")