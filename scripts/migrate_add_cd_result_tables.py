"""幂等迁移：创建 Cd 双模型结果表（阶段 1）。

沿用项目既有迁移路线（不引入 Alembic）：`db.create_all()` 建缺失表 + 打印结构校验。
参考 `scripts/migrate_add_model45_fields.py`。

用法::

    python scripts/migrate_add_cd_result_tables.py
    python scripts/migrate_add_cd_result_tables.py --drop   # 回滚：删除这两张表

覆盖前备份 / 回滚命令见 docs/heavy-metal-cd-database-backend.md。
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for _p in (str(PROJECT_ROOT), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 项目惯例：入口脚本先加载 .env（否则 Config 使用默认旧库参数）
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:  # pragma: no cover - dotenv 缺失时依赖外部环境变量
    pass

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
import framework.models  # noqa: E402,F401  触发全部模型注册

logger = logging.getLogger("migrate_cd_result_tables")

TABLES = ("cd_crop_prediction_result", "cd_effective_prediction_result")


def drop_tables() -> None:
    app = create_app()
    with app.app_context():
        for table in TABLES:
            db.session.execute(text(f"DROP TABLE IF EXISTS {table}"))
        db.session.commit()
        print("[回滚] 已删除:", ", ".join(TABLES))


def run_migration() -> None:
    app = create_app()
    with app.app_context():
        before = set(inspect(db.engine).get_table_names())
        db.create_all()
        after = set(inspect(db.engine).get_table_names())
        created = sorted(after & set(TABLES) - before)
        print(f"[1/2] db.create_all() 完成；本次新建: {created or '无（表已存在）'}")

        inspector = inspect(db.engine)
        for table in TABLES:
            if table not in after:
                print(f"[错误] {table} 不存在", file=sys.stderr)
                sys.exit(1)
            columns = inspector.get_columns(table)
            names = [c["name"] for c in columns]
            uniques = inspector.get_unique_constraints(table)
            indexes = inspector.get_indexes(table)
            print(f"[2/2] {table}")
            print(f"      列: {names}")
            print(f"      注释: " + "; ".join(f"{c['name']}={c.get('comment')}" for c in columns))
            print(f"      唯一约束: {[u['column_names'] for u in uniques]}")
            print(f"      索引: {[i['column_names'] for i in indexes]}")
            expected = {"id", "parcel_id", "sample_id", "ln_crop_cd" if "crop" in table else "ln_eff_cd"}
            if set(names) != expected:
                print(f"[错误] {table} 列结构不符，期望 {sorted(expected)}", file=sys.stderr)
                sys.exit(1)
            if not any(u["column_names"] == ["parcel_id", "sample_id"] for u in uniques):
                print(f"[错误] {table} 缺少 (parcel_id, sample_id) 唯一约束", file=sys.stderr)
                sys.exit(1)
        print("[完成] 两张 Cd 结果表结构与约束校验通过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="创建 Cd 双模型结果表")
    parser.add_argument("--drop", action="store_true", help="回滚：删除两张结果表")
    args = parser.parse_args()
    if args.drop:
        drop_tables()
    else:
        run_migration()
