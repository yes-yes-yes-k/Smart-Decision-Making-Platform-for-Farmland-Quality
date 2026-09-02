import atexit

from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from framework.config import Config, config_map
from framework.models.user import db
from framework.api.routes.auth import auth_bp
from framework.api.routes.chat import chat_bp
from framework.api.routes.models import models_bp
from framework.api.routes.docs import docs_bp
from framework.api.routes.county import county_bp
from framework.api.routes.report import report_bp
from framework.api.routes.data_import import data_import_bp
from framework.api.routes.observability import observability_bp
from framework.agents.workflows.comprehensive.checkpointing import (
    PostgresCheckpointerRuntime,
)


def init_comprehensive_checkpointer(app: Flask) -> None:
    if app.config["COMPREHENSIVE_WORKFLOW_MODE"] != "enabled":
        return
    runtime = PostgresCheckpointerRuntime(
        app.config["LANGGRAPH_CHECKPOINT_URI"],
        auto_setup=app.config["LANGGRAPH_CHECKPOINT_AUTO_SETUP"],
    )
    saver = runtime.start()
    app.extensions["comprehensive_checkpointer_runtime"] = runtime
    app.extensions["comprehensive_checkpointer"] = saver
    atexit.register(runtime.close)


def init_comprehensive_workflow(app: Flask) -> None:
    """Compile the durable task graph only when execution is enabled."""
    if app.config["COMPREHENSIVE_WORKFLOW_MODE"] != "enabled":
        return
    from framework.agents.workflows.comprehensive.graph import (
        build_comprehensive_graph, build_default_comprehensive_services,
    )
    from framework.agents.workflows.comprehensive.runtime import ComprehensiveWorkflowRuntime
    saver = app.extensions.get("comprehensive_checkpointer")
    if saver is None:
        return
    services = build_default_comprehensive_services(app)
    app.extensions["comprehensive_runtime"] = ComprehensiveWorkflowRuntime(
        build_comprehensive_graph(services, saver)
    )


def _ensure_kb_message_columns(app: Flask):
    """启动时自动给 kb_message 补 agents_invoked / recommendations 列（无损，列已存在跳过）。

    SQLite / MySQL 都兼容；迁移脚本 migrate_add_message_agents.py 也做了同一件事，
    这里兜底避免用户漏跑迁移脚本导致 500 "no such column"。
    """
    from sqlalchemy import text as sa_text
    from sqlalchemy import inspect as sa_inspect

    with app.app_context():
        engine = db.engine
        dialect = engine.dialect.name

        # 表不存在时跳过（db.create_all() 会创建包含所有列的表）
        if not sa_inspect(engine).has_table("kb_message"):
            return

        def _has_column(table: str, column: str) -> bool:
            with engine.connect() as conn:
                if dialect == "mysql":
                    row = conn.execute(sa_text(
                        "SELECT COUNT(*) FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
                    ), {"t": table, "c": column}).fetchone()
                    return (row[0] if isinstance(row, tuple) else row[0]) > 0
                elif dialect == "postgresql":
                    row = conn.execute(sa_text(
                        "SELECT COUNT(*) FROM information_schema.COLUMNS "
                        "WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c"
                    ), {"t": table, "c": column}).fetchone()
                    return (row[0] if isinstance(row, tuple) else row[0]) > 0
                # sqlite
                rows = conn.execute(sa_text(f"PRAGMA table_info(`{table}`)")).fetchall()
                return any(str(r[1]).lower() == column.lower() for r in rows)

        specs = [
            (
                "agents_invoked",
                'ALTER TABLE kb_message ADD COLUMN agents_invoked JSON DEFAULT NULL',
                'ALTER TABLE kb_message ADD COLUMN agents_invoked JSON DEFAULT NULL COMMENT \'本次回答调用的专业模型ID列表\'',
            ),
            (
                "recommendations",
                'ALTER TABLE kb_message ADD COLUMN recommendations JSON DEFAULT NULL',
                'ALTER TABLE kb_message ADD COLUMN recommendations JSON DEFAULT NULL COMMENT \'综合建议列表\'',
            ),
        ]
        for col, ddl_sqlite, ddl_mysql in specs:
            if _has_column("kb_message", col):
                continue
            ddl = ddl_mysql if dialect == "mysql" else ddl_sqlite
            with engine.begin() as conn:
                conn.execute(sa_text(ddl))


def _ensure_analysis_context_compatibility(app: Flask):
    """启动期只补可空列和新表；约束替换留给正式迁移脚本。"""
    from scripts.migrate_analysis_context import (
        ensure_analysis_context_columns,
        ensure_execution_log_provenance,
        ensure_spatial_region_catalog,
    )

    with app.app_context():
        with db.engine.begin() as connection:
            ensure_analysis_context_columns(connection)
            ensure_spatial_region_catalog(connection)
            ensure_execution_log_provenance(connection)


def create_app(config_name: str = 'default') -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    CORS(app)
    JWTManager(app)
    db.init_app(app)
    init_comprehensive_checkpointer(app)
    init_comprehensive_workflow(app)

    # 注册蓝图之前先把 ORM 需要的列补齐，防止首次请求 SELECT 时爆 no such column
    _ensure_kb_message_columns(app)
    _ensure_analysis_context_compatibility(app)

    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(chat_bp, url_prefix='/api/v1/chat')
    app.register_blueprint(models_bp, url_prefix='/api/v1/models')
    app.register_blueprint(docs_bp, url_prefix='/api/v1/docs')
    app.register_blueprint(county_bp, url_prefix='/api/v1/county')
    app.register_blueprint(report_bp, url_prefix='/api/v1/report')
    app.register_blueprint(data_import_bp, url_prefix='/api/v1/data')
    app.register_blueprint(observability_bp, url_prefix='/api/v1/observability')

    @app.route('/')
    def index():
        return {"status": "ok", "message": "Unified Framework API"}

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000)
