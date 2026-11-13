"""建 Cd 通量表（阶段 5）。幂等可重跑，与项目既有手写迁移路线一致。

用法：
    python scripts/migrate_cd_flux_tables.py

只创建 ``cd_flux_input`` / ``cd_flux_output`` 两张表（checkfirst），不触碰其它表。
"""
from __future__ import annotations

import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(PROJECT, ".env"))

from framework.api.app import create_app  # noqa: E402
from framework.models import CdFluxInput, CdFluxOutput  # noqa: E402
from framework.models.user import db  # noqa: E402


def main() -> int:
    app = create_app()
    with app.app_context():
        for table in (CdFluxInput.__table__, CdFluxOutput.__table__):
            table.create(bind=db.engine, checkfirst=True)
            print(f"table ready: {table.name}")
        from sqlalchemy import inspect

        inspector = inspect(db.engine)
        for name in ("cd_flux_input", "cd_flux_output"):
            print(f"{name} exists={inspector.has_table(name)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
