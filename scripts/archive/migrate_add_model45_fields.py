"""增量迁移：创建 area_code_region_map 表 + 为现有土壤表添加 Model-4/5 字段。

采用 ALTER TABLE 而非 DROP+CREATE，保留现有数据。
- area_code_region_map: db.create_all() 创建（新表）
- third_survey_topsoils: ALTER TABLE 添加 5 列
- third_survey_profiles: ALTER TABLE 添加 3 列

用法:
    python scripts/migrate_add_model45_fields.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for _p in (str(PROJECT_ROOT), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
import framework.models  # noqa: E402,F401 触发所有模型注册

logger = logging.getLogger("migrate_model45")

# ALTER TABLE 语句
TOPSOIL_ALTERS = [
    "ALTER TABLE third_survey_topsoils ADD COLUMN IF NOT EXISTS exchangeable_hydrogen FLOAT",
    "ALTER TABLE third_survey_topsoils ADD COLUMN IF NOT EXISTS exchangeable_aluminum FLOAT",
    "ALTER TABLE third_survey_topsoils ADD COLUMN IF NOT EXISTS exchangeable_acid_total FLOAT",
    "ALTER TABLE third_survey_topsoils ADD COLUMN IF NOT EXISTS hydrolytic_total_acidity FLOAT",
    "ALTER TABLE third_survey_topsoils ADD COLUMN IF NOT EXISTS total_n FLOAT",
]

PROFILE_ALTERS = [
    "ALTER TABLE third_survey_profiles ADD COLUMN IF NOT EXISTS exchangeable_hydrogen FLOAT",
    "ALTER TABLE third_survey_profiles ADD COLUMN IF NOT EXISTS exchangeable_aluminum FLOAT",
    "ALTER TABLE third_survey_profiles ADD COLUMN IF NOT EXISTS hydrolytic_total_acidity FLOAT",
]


def run_migration() -> None:
    app = create_app()
    with app.app_context():
        # 1. db.create_all() 创建缺失的表（area_code_region_map 等）
        db.create_all()
        print("[1/3] db.create_all() 完成 — area_code_region_map 表已创建（如不存在）")

        # 2. ALTER TABLE third_survey_topsoils
        for sql in TOPSOIL_ALTERS:
            db.session.execute(text(sql))
        db.session.commit()
        print(f"[2/3] third_survey_topsoils 添加 {len(TOPSOIL_ALTERS)} 列完成")

        # 3. ALTER TABLE third_survey_profiles
        for sql in PROFILE_ALTERS:
            db.session.execute(text(sql))
        db.session.commit()
        print(f"[3/3] third_survey_profiles 添加 {len(PROFILE_ALTERS)} 列完成")

        # 验证
        print("\n=== 迁移后验证 ===")
        for table, fields in [
            ("third_survey_topsoils", ["exchangeable_hydrogen", "exchangeable_aluminum",
                                       "exchangeable_acid_total", "hydrolytic_total_acidity", "total_n"]),
            ("third_survey_profiles", ["exchangeable_hydrogen", "exchangeable_aluminum",
                                        "exchangeable_acid_total", "hydrolytic_total_acidity"]),
        ]:
            for field in fields:
                exists = db.session.execute(text(
                    f"SELECT count(*) FROM information_schema.columns WHERE table_name='{table}' AND column_name='{field}'"
                )).scalar()
                status = "OK" if exists else "FAIL"
                print(f"  [{status}] {table}.{field}")

        # 验证 area_code_region_map
        area_count = db.session.execute(text(
            "SELECT count(*) FROM information_schema.tables WHERE table_name='area_code_region_map'"
        )).scalar()
        print(f"  [{'OK' if area_count else 'FAIL'}] area_code_region_map 表")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_migration()
    print("\n[完成] 迁移成功，现有数据已保留")


if __name__ == "__main__":
    main()
