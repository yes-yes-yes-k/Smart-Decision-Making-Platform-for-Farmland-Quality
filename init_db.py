import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# 与 start_http_server.py 保持一致：先加载 .env，否则 DB_* 配置会退回 config.py 的默认值。
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from werkzeug.security import generate_password_hash
from framework.api.app import create_app
from framework.models.user import db, User
import framework.models  # noqa: F401  触发 soil_data 等模型注册，使元数据包含新表

# 支持通过 FLASK_ENV 选择配置；未设置时使用 'default'（PostgreSQL）
config_name = os.environ.get('FLASK_ENV') or 'default'

from framework.config import config_map

# PostGIS 扩展必须在 create_app() 之前就绪：启动期补丁会直接创建带 geometry 列的表，
# 否则会报 “类型 geometry 不存在”。
db_uri = config_map[config_name].SQLALCHEMY_DATABASE_URI
if db_uri.startswith('postgresql'):
    try:
        _ext_engine = create_engine(db_uri)
        with _ext_engine.begin() as _conn:
            _conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        _ext_engine.dispose()
        print("[初始化] PostGIS 扩展已就绪")
    except Exception as e:  # noqa: BLE001 - 启动前置检查，失败直接退出
        print(f"[错误] PostGIS 扩展初始化失败：{e}", file=sys.stderr)
        print("[提示] 请用超级用户执行：psql -U postgres -d <库名> -c \"CREATE EXTENSION postgis\"", file=sys.stderr)
        sys.exit(1)

app = create_app(config_name)

with app.app_context():
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    is_pg = db_uri.startswith('postgresql')

    # ------------------------------------------------------------------
    # 1) 清理：先删视图，再删残留表/索引（带 schema 限定，避免 search_path 陷阱）
    # ------------------------------------------------------------------
    if is_pg:
        with db.engine.begin() as conn:
            conn.execute(text(
                "DROP VIEW IF EXISTS v_model_execution_summary, "
                "v_parcel_stability_spatial, v_confusion_matrix_latest CASCADE"
            ))

    _model_tables = {t.name for t in db.metadata.sorted_tables}
    _model_indexes = {i.name for t in db.metadata.sorted_tables for i in t.indexes if i.name}

    if is_pg:
        # 从 pg_catalog 查出残留对象的真实 schema，带限定符删除，
        # 避免 inspector 只看默认 schema 导致的漏删。
        with db.engine.begin() as conn:
            _residuals = conn.execute(
                text(
                    "SELECT n.nspname, c.relname, c.relkind FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
                    "AND c.relname = ANY(:names)"
                ),
                {"names": list(_model_tables | _model_indexes)},
            ).fetchall()
            for _nsp, _rel, _kind in _residuals:
                if _kind in ("r", "p") and _rel in _model_tables:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{_nsp}"."{_rel}" CASCADE'))
                elif _kind == "i" and _rel in _model_indexes:
                    conn.execute(text(f'DROP INDEX IF EXISTS "{_nsp}"."{_rel}"'))
    else:
        # 非 PostgreSQL（如 SQLite）走原有 drop_all 逻辑
        db.drop_all()

    # ------------------------------------------------------------------
    # 2) 建表：只建表，不建索引
    #    用 CreateTable(if_not_exists=True) 生成纯 CREATE TABLE IF NOT EXISTS，
    #    不触发索引创建，避免同一事务内同一索引被建两次。
    # ------------------------------------------------------------------
    from sqlalchemy.schema import CreateTable, CreateIndex

    with db.engine.begin() as conn:
        for table in db.metadata.sorted_tables:
            conn.execute(CreateTable(table, if_not_exists=True))

    # ------------------------------------------------------------------
    # 3) 幂等建索引：逐个用 CREATE INDEX IF NOT EXISTS 创建
    #    此时表已建好，索引在事务内尚未创建过，IF NOT EXISTS 不会误判。
    # ------------------------------------------------------------------
    if is_pg:
        with db.engine.begin() as conn:
            for table in db.metadata.sorted_tables:
                for index in table.indexes:
                    if not index.name:
                        continue
                    ddl = str(CreateIndex(index).compile(dialect=conn.dialect))
                    # 形如：CREATE [UNIQUE] INDEX idx_xxx ON tbl (...)
                    if ddl.upper().startswith("CREATE UNIQUE INDEX"):
                        ddl = "CREATE UNIQUE INDEX IF NOT EXISTS" + ddl[len("CREATE UNIQUE INDEX"):]
                    else:
                        ddl = "CREATE INDEX IF NOT EXISTS" + ddl[len("CREATE INDEX"):]
                    try:
                        conn.execute(text(ddl))
                    except Exception as e:  # noqa: BLE001 - 单个索引失败不阻塞整体初始化
                        print(f"[警告] 索引创建失败 {index.name}: {e}", file=sys.stderr)
    else:
        # 非 PostgreSQL：表建完后补建索引（SQLite 不支持 IF NOT EXISTS 建索引，用 try 兜底）
        with db.engine.begin() as conn:
            for table in db.metadata.sorted_tables:
                for index in table.indexes:
                    if not index.name:
                        continue
                    try:
                        conn.execute(CreateIndex(index))
                    except Exception as e:  # noqa: BLE001
                        print(f"[警告] 索引创建失败 {index.name}: {e}", file=sys.stderr)

    # ------------------------------------------------------------------
    # 4) 执行 V3.0 视图脚本（依赖新表已创建）
    # ------------------------------------------------------------------
    if is_pg:
        views_path = PROJECT_ROOT / "scripts" / "v3_views.sql"
        if views_path.exists():
            with db.engine.begin() as conn:
                conn.execute(text(views_path.read_text(encoding="utf-8")))
            print("[初始化] V3.0 视图创建完成（v_model_execution_summary / v_parcel_stability_spatial / v_confusion_matrix_latest）")
        else:
            print(f"[警告] 视图脚本不存在：{views_path}", file=sys.stderr)

    # ------------------------------------------------------------------
    # 5) 创建默认用户（幂等：已存在则跳过，避免重复运行报唯一约束）
    # ------------------------------------------------------------------
    for username, password, nickname, role in [
        ('admin', 'admin123', '管理员', 'admin'),
        ('user', 'user123', '普通用户', 'user'),
    ]:
        existing = User.query.filter_by(username=username).first()
        if existing:
            print(f"[初始化] 用户已存在，跳过: {username}")
            continue
        db.session.add(User(
            username=username,
            password=generate_password_hash(password),
            nickname=nickname,
            role=role,
            status=1,
        ))
    db.session.commit()

    print("[初始化] 数据库表结构创建完成")
    print("[初始化] 管理员用户: admin / admin123")
    print("[初始化] 普通用户: user / user123")
    print("[提示] 运行 'python start_http_server.py' 启动服务")