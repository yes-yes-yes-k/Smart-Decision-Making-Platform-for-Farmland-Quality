"""验证模型 1-5 数据是否已关联到 V3.0 ORM 表中。

检查维度：
1. 5 张结果表行数
2. model_execution_log 状态分布
3. thematic_model_registry 注册情况
4. v_model_execution_summary 视图
5. 外键完整性（execution_id → model_execution_log.id, agent_id → thematic_model_registry.agent_id）
6. 各表样本数据

用法: python scripts/verify_model_data.py
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# 加载 .env 配置
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from sqlalchemy import text
from framework.api.app import create_app
from framework.models.user import db
import framework.models  # noqa: F401  触发模型注册


RESULT_TABLES = {
    "stability_risk_result": "model-1",
    "quality_grade_result": "model-2",
    "obstacle_diagnosis_result": "model-3",
    "organic_matter_result": "model-5",
    "acidification_remediation_result": "model-4",
}

EXPECTED_ROWS = {
    "stability_risk_result": 5488,
    "quality_grade_result": 1107,
    "obstacle_diagnosis_result": 14585,
    "organic_matter_result": 232,
    "acidification_remediation_result": 393,
}


def run_query(sql, params=None):
    return db.session.execute(text(sql), params or {}).fetchall()


def run_scalar(sql, params=None):
    return db.session.execute(text(sql), params or {}).scalar()


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check_table_counts():
    section("1. 结果表行数")
    total = 0
    all_ok = True
    for table, agent_id in RESULT_TABLES.items():
        count = run_scalar(f"SELECT count(*) FROM {table}")
        expected = EXPECTED_ROWS[table]
        status = "OK" if count == expected else "MISMATCH"
        if count != expected:
            all_ok = False
        total += count
        print(f"  {table:40s} {count:>8d} rows (expected {expected:>5d}) [{status}]  agent_id={agent_id}")
    print(f"  {'TOTAL':40s} {total:>8d} rows")
    print(f"  Result: {'ALL OK' if all_ok else 'HAS MISMATCH'}")
    return all_ok


def check_execution_logs():
    section("2. model_execution_log 状态分布")
    rows = run_query("""
        SELECT agent_id, status, count(*) as cnt
        FROM model_execution_log
        GROUP BY agent_id, status
        ORDER BY agent_id, status
    """)
    all_ok = True
    print(f"  {'agent_id':15s} {'status':15s} {'count':>8s}")
    print(f"  {'-'*15} {'-'*15} {'-'*8}")
    for row in rows:
        if row.status != "ok":
            all_ok = False
        print(f"  {row.agent_id:15s} {row.status:15s} {row.cnt:>8d}")

    total = run_scalar("SELECT count(*) FROM model_execution_log")
    print(f"\n  Total execution logs: {total}")
    print(f"  Result: {'ALL OK' if all_ok else 'HAS NON-OK STATUS'}")
    return all_ok


def check_registry():
    section("3. thematic_model_registry 注册情况")
    rows = run_query("""
        SELECT agent_id, model_id, name, question_type, analysis_scale, status, version
        FROM thematic_model_registry
        ORDER BY question_type
    """)
    if not rows:
        print("  WARNING: No model registry entries found!")
        return False

    print(f"  {'agent_id':15s} {'model_id':30s} {'name':40s} {'q_type':>6s} {'scale':10s} {'status':10s} {'ver':6s}")
    print(f"  {'-'*15} {'-'*30} {'-'*40} {'-'*6} {'-'*10} {'-'*10} {'-'*6}")
    for r in rows:
        print(f"  {r.agent_id:15s} {r.model_id:30s} {r.name[:38]:40s} {r.question_type:>6d} {r.analysis_scale:10s} {r.status:10s} {r.version:6s}")
    print(f"\n  Registered models: {len(rows)}")
    return True


def check_summary_view():
    section("4. v_model_execution_summary 视图")
    try:
        rows = run_query("SELECT * FROM v_model_execution_summary ORDER BY agent_id")
        if not rows:
            print("  WARNING: View returned no rows!")
            return False
        cols = rows[0]._fields
        # Print header
        header = "  " + " | ".join(f"{c[:18]:>18s}" for c in cols)
        print(header)
        print("  " + "-" * (len(cols) * 20))
        for row in rows:
            vals = []
            for c in cols:
                v = getattr(row, c)
                vals.append(f"{str(v)[:18]:>18s}")
            print("  " + " | ".join(vals))
        print(f"\n  View rows: {len(rows)}")
        return True
    except Exception as e:
        print(f"  ERROR querying view: {e}")
        return False


def check_fk_integrity():
    section("5. 外键完整性检查")
    all_ok = True

    # Check execution_id FK in each result table
    print("\n  5a. execution_id → model_execution_log.id")
    for table, agent_id in RESULT_TABLES.items():
        # Count rows with valid execution_id
        valid = run_scalar(f"""
            SELECT count(*) FROM {table} r
            JOIN model_execution_log m ON r.execution_id = m.id
        """)
        total = run_scalar(f"SELECT count(*) FROM {table}")
        orphan = run_scalar(f"""
            SELECT count(*) FROM {table} r
            LEFT JOIN model_execution_log m ON r.execution_id = m.id
            WHERE m.id IS NULL
        """)
        status = "OK" if orphan == 0 else f"ORPHANS: {orphan}"
        if orphan > 0:
            all_ok = False
        print(f"    {table:40s} {valid:>8d}/{total:>8d} valid  [{status}]")

    # Check agent_id FK in model_execution_log → thematic_model_registry
    print("\n  5b. model_execution_log.agent_id → thematic_model_registry.agent_id")
    orphans = run_scalar("""
        SELECT count(*) FROM model_execution_log l
        LEFT JOIN thematic_model_registry r ON l.agent_id = r.agent_id
        WHERE r.agent_id IS NULL
    """)
    total_logs = run_scalar("SELECT count(*) FROM model_execution_log")
    if orphans == 0:
        print(f"    All {total_logs} logs have valid agent_id FK  [OK]")
    else:
        all_ok = False
        print(f"    {orphans}/{total_logs} logs have orphaned agent_id  [ORPHANS]")

    print(f"\n  Result: {'ALL FK OK' if all_ok else 'FK VIOLATIONS FOUND'}")
    return all_ok


def check_samples():
    section("6. 各结果表样本数据（前 2 行）")
    for table, agent_id in RESULT_TABLES.items():
        print(f"\n  --- {table} (agent_id={agent_id}) ---")
        try:
            rows = run_query(f"SELECT * FROM {table} LIMIT 2")
            if not rows:
                print("    (empty)")
                continue
            cols = rows[0]._fields
            for i, row in enumerate(rows):
                print(f"    Row {i+1}:")
                for col in cols:
                    val = getattr(row, col)
                    val_str = str(val)
                    if len(val_str) > 60:
                        val_str = val_str[:57] + "..."
                    print(f"      {col:30s} = {val_str}")
        except Exception as e:
            db.session.rollback()
            print(f"    ERROR: {e}")


def check_parcel_id_consistency():
    section("7. parcel_id 一致性（V3.0 命名规范）")
    # model-5 (organic_matter_result) 是县级分析，无 parcel_id 列（V3.0 设计）
    county_level = {"organic_matter_result"}
    for table, agent_id in RESULT_TABLES.items():
        if table in county_level:
            print(f"  {table:40s} 县级分析表，无 parcel_id 列（V3.0 设计）  [SKIP]")
            continue
        try:
            total = run_scalar(f"SELECT count(*) FROM {table}")
            non_null = run_scalar(f"SELECT count(*) FROM {table} WHERE parcel_id IS NOT NULL")
            pct = (non_null / total * 100) if total > 0 else 0
            status = "OK" if pct == 100 else f"NULL: {total - non_null}"
            print(f"  {table:40s} {non_null:>8d}/{total:>8d} non-null parcel_id ({pct:.1f}%)  [{status}]")
        except Exception as e:
            db.session.rollback()
            print(f"  {table:40s} ERROR: {e}")


def main():
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("  V3.0 ORM 数据验证报告")
        print(f"  Database: {db.engine.url}")
        print("=" * 60)

        results = {}
        results["table_counts"] = check_table_counts()
        results["exec_logs"] = check_execution_logs()
        results["registry"] = check_registry()
        results["summary_view"] = check_summary_view()
        results["fk_integrity"] = check_fk_integrity()
        check_parcel_id_consistency()
        check_samples()

        section("总结")
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        for name, ok in results.items():
            print(f"  {name:25s} {'PASS' if ok else 'FAIL'}")
        print(f"\n  {passed}/{total} checks passed")

        if passed == total:
            print("\n  *** ALL CHECKS PASSED — 数据已正确关联到 V3.0 ORM 表 ***")
        else:
            print("\n  *** SOME CHECKS FAILED — 请检查上述详细信息 ***")


if __name__ == "__main__":
    main()
