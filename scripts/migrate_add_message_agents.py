"""给 kb_message 表补 agents_invoked / recommendations 两列（无损迁移，兼容 SQLite + MySQL）。

用法：
    python migrate_add_message_agents.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv
load_dotenv()

from framework.api.app import create_app
from framework.models.user import db


def _column_exists(table: str, column: str) -> bool:
    """跨数据库检查表中是否存在指定列。"""
    engine = db.engine
    dialect = engine.dialect.name

    with engine.connect() as conn:
        if dialect == "mysql":
            row = conn.execute(db.text(
                "SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
            ), {"t": table, "c": column}).fetchone()
        elif dialect == "sqlite":
            row = conn.execute(db.text(f"PRAGMA table_info(`{table}`)")).fetchall()
            return any(str(r[1]).lower() == column.lower() for r in row)
        else:
            row = None
        if row is None:
            return False
        return (row[0] if isinstance(row, tuple) else row[0]) > 0


def main() -> int:
    app = create_app()
    with app.app_context():
        dialect = db.engine.dialect.name
        print(f"[migration] 当前数据库方言: {dialect}")

        for column, ddl_sqlite, ddl_mysql in [
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
        ]:
            if _column_exists("kb_message", column):
                print(f"[migration] 列 kb_message.{column} 已存在，跳过")
                continue
            ddl = ddl_mysql if dialect == "mysql" else ddl_sqlite
            with db.engine.begin() as conn:
                conn.execute(db.text(ddl))
            print(f"[migration] 已添加列 kb_message.{column}")

        print("[migration] 完成，历史消息的 agents_invoked/recommendations 默认为空列表（由 to_dict 兜底）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
