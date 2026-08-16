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

    # 先删除 V3.0 视图（若存在），避免 db.drop_all() 因视图依赖表而失败
    if db_uri.startswith('postgresql'):
        db.session.execute(text(
            "DROP VIEW IF EXISTS v_model_execution_summary, "
            "v_parcel_stability_spatial, v_confusion_matrix_latest CASCADE"
        ))
        db.session.commit()

    db.drop_all()
    db.create_all()

    # 执行 V3.0 视图脚本（依赖 15 张新表已通过 db.create_all() 创建）
    if db_uri.startswith('postgresql'):
        views_path = PROJECT_ROOT / "scripts" / "v3_views.sql"
        if views_path.exists():
            with open(views_path, encoding="utf-8") as f:
                db.session.execute(text(f.read()))
            db.session.commit()
            print("[初始化] V3.0 视图创建完成（v_model_execution_summary / v_parcel_stability_spatial / v_confusion_matrix_latest）")
        else:
            print(f"[警告] 视图脚本不存在：{views_path}", file=sys.stderr)

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