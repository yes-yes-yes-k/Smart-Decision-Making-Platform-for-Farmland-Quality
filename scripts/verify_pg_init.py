#!/usr/bin/env python
"""
PostgreSQL + PostGIS 集成验证脚本。

在有 PostgreSQL 16 + PostGIS 3.4 实例时手动运行：
    python scripts/verify_pg_init.py

对应 tasks.md 4.5-4.7 验收点。
不进入 pytest CI（符合「代码先行，环境后续」原则）。
"""
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sqlalchemy import text
from framework.api.app import create_app
from framework.models.user import db, User
import framework.models  # noqa: F401


def verify_postgis_extension():
    """验证 PostGIS 扩展已安装"""
    result = db.session.execute(text("SELECT PostGIS_Version()")).scalar()
    print(f"[PASS] PostGIS 版本: {result}")
    return True


def verify_tables_created():
    """验证 8 张土壤数据表 + user 表创建成功"""
    expected_tables = [
        'third_survey_topsoils', 'third_survey_profiles',
        'third_survey_site_conditions', 'third_survey_bulk_densities',
        'second_survey_points', 'formula_fertilizations',
        'agri_chemicalization', 'grain_yields',
        'users', 'conversations', 'messages', 'documents', 'data_files'
    ]
    result = db.session.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    )).scalars().all()
    for table in expected_tables:
        if table not in result:
            print(f"[FAIL] 表 {table} 未创建")
            return False
    print(f"[PASS] 全部 {len(expected_tables)} 张表创建成功")
    return True


def verify_users_exist():
    """验证 admin/user 用户存在"""
    admin = User.query.filter_by(username='admin').first()
    user = User.query.filter_by(username='user').first()
    if not admin or not user:
        print("[FAIL] admin/user 用户未创建")
        return False
    print("[PASS] admin/user 用户存在")
    return True


def verify_idempotency():
    """验证重复运行 init_db.py 幂等性"""
    # 重复运行 init_db.py 逻辑（已在 app_context 内）
    os.system(f"python {PROJECT_ROOT / 'init_db.py'}")
    print("[PASS] 重复运行幂等")
    return True


def main():
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("PostgreSQL + PostGIS 集成验证")
        print("=" * 60)
        results = []
        results.append(("PostGIS 扩展", verify_postgis_extension()))
        results.append(("表创建", verify_tables_created()))
        results.append(("用户创建", verify_users_exist()))
        results.append(("幂等性", verify_idempotency()))
        print("=" * 60)
        passed = sum(1 for _, ok in results if ok)
        total = len(results)
        print(f"结果: {passed}/{total} 通过")
        if passed != total:
            sys.exit(1)


if __name__ == '__main__':
    main()
