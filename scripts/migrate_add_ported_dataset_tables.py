"""幂等迁移：创建移植数据集所需的表（阶段 D1）。

沿用项目既有迁移路线（不引入 Alembic）：`db.create_all()` 建缺失表 + 结构校验。

用法::

    python scripts/migrate_add_ported_dataset_tables.py
    python scripts/migrate_add_ported_dataset_tables.py --drop   # 回滚：删除归属表
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for _p in (str(PROJECT_ROOT), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
import framework.models  # noqa: E402,F401

TABLE = "cd_ported_parcel_township"
EXPECTED_COLUMNS = {"parcel_id", "township_id", "township_name", "distance_m", "assigned_at"}


def drop_table() -> None:
    app = create_app()
    with app.app_context():
        db.session.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        db.session.commit()
        print(f"[回滚] 已删除 {TABLE}")


def run_migration() -> None:
    app = create_app()
    with app.app_context():
        before = set(inspect(db.engine).get_table_names())
        db.create_all()
        after = set(inspect(db.engine).get_table_names())
        print(f"[1/2] db.create_all() 完成；本次新建: {sorted(after - before) or '无（表已存在）'}")

        if TABLE not in after:
            print(f"[错误] {TABLE} 不存在", file=sys.stderr)
            sys.exit(1)
        inspector = inspect(db.engine)
        columns = {c["name"] for c in inspector.get_columns(TABLE)}
        pk = inspector.get_pk_constraint(TABLE).get("constrained_columns") or []
        print(f"[2/2] {TABLE}")
        print(f"      列: {sorted(columns)}")
        print(f"      主键: {pk}")
        if columns != EXPECTED_COLUMNS:
            print(f"[错误] 列结构不符，期望 {sorted(EXPECTED_COLUMNS)}", file=sys.stderr)
            sys.exit(1)
        if pk != ["parcel_id"]:
            print("[错误] 主键应为 parcel_id", file=sys.stderr)
            sys.exit(1)
        print("[完成] 移植归属表结构校验通过")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="创建移植数据集归属表")
    parser.add_argument("--drop", action="store_true", help="回滚：删除归属表")
    args = parser.parse_args()
    if args.drop:
        drop_table()
    else:
        run_migration()
