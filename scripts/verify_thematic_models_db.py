"""验证专题模型从数据库计算的流程：每个专题模型挑选三个地块计算，输出验证报告。"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime

# 确保项目根目录在 Python 路径中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 加载 .env 环境变量
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def check_db_tables():
    """检查数据库表和数据量。"""
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    tables = [r[0] for r in cur.fetchall()]
    print("=== 数据库表清单 ===")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        count = cur.fetchone()[0]
        print(f"  {t}: {count} rows")

    # 检查 parcel_info 表的列
    if "parcel_info" in tables:
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='parcel_info' ORDER BY ordinal_position"
        )
        cols = cur.fetchall()
        print("\n=== parcel_info 表结构 ===")
        for col in cols:
            print(f"  {col[0]}: {col[1]}")

    conn.close()
    return tables


def seed_registry():
    """如果 thematic_model_registry 为空，插入 6 个模型注册条目（FK 前置条件）。"""
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
    )
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM thematic_model_registry")
    count = cur.fetchone()[0]

    if count > 0:
        print(f"thematic_model_registry 已有 {count} 条数据，跳过种子数据插入")
        conn.close()
        return

    print("\nthematic_model_registry 表为空，插入 6 个模型注册条目...")
    models = [
        ("model-1", "stability-risk", "稳定性风险评价", "stability", 1, "parcel"),
        ("model-2", "farmland-grade", "耕地质量等级评价", "grade", 2, "parcel"),
        ("model-3", "obstacle-diagnosis", "障碍诊断", "problem", 3, "parcel"),
        ("model-4", "acidification-remediation", "酸化改良", "acidification", 4, "parcel"),
        ("model-5", "organic-matter-improvement", "有机质培肥", "organic_matter", 5, "county"),
        ("model-6", "comprehensive-fertility", "综合 fertility", "fertility", 6, "county"),
    ]
    for agent_id, model_id, name, domain, q_type, scale in models:
        cur.execute(
            """
            INSERT INTO thematic_model_registry
                (agent_id, model_id, name, domain, question_type,
                 analysis_scale, data_type, input_format, output_format,
                 version, status)
            VALUES (%s, %s, %s, %s, %s, %s, '指标数据', 'json', 'json', '1.0', 'active')
            ON CONFLICT (agent_id) DO NOTHING
            """,
            (agent_id, model_id, name, domain, q_type, scale),
        )
    conn.commit()
    print(f"已插入 {len(models)} 个模型注册条目")
    conn.close()


def seed_parcel_data():
    """如果 parcel_info 表为空，插入 3 个测试地块。"""
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
    )
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM parcel_info")
    count = cur.fetchone()[0]

    if count > 0:
        print(f"\nparcel_info 已有 {count} 条数据，跳过种子数据插入")
        conn.close()
        return

    print("\nparcel_info 表为空，插入 3 个测试地块...")

    # 3 个代表性地块：酸性旱地、中性水田、低有机质旱地
    parcels = [
        {
            "parcel_id": "P-VERIFY-001",
            "area_code": "440281",
            "land_type": "upland",
            "fertilizer_type": "compound",
            "target_ph": 6.5,
            "soil_indicators": {
                "soil_ph": 4.8,
                "organic_matter": 15.0,
                "total_nitrogen": 1.0,
                "available_phosphorus": 8.0,
                "available_potassium": 60.0,
                "exchangeable_hydrogen": 5.0,
                "cation_exchange_capacity": 8.0,
                "clay_content": 30.0,
                "sand_content": 40.0,
                "silt_content": 30.0,
                "bulk_density": 1.35,
                "topsoil_thickness": 20.0,
                "slope": 8.0,
                "irrigation_condition": "dry",
                "terrain_position": "lower",
                "soil_texture": "loam",
                "obstacle_factors": ["acidification", "low_organic_matter"],
            },
        },
        {
            "parcel_id": "P-VERIFY-002",
            "area_code": "440281",
            "land_type": "paddy",
            "fertilizer_type": "urea",
            "target_ph": 6.0,
            "soil_indicators": {
                "soil_ph": 5.8,
                "organic_matter": 28.0,
                "total_nitrogen": 1.8,
                "available_phosphorus": 15.0,
                "available_potassium": 120.0,
                "exchangeable_hydrogen": 2.0,
                "cation_exchange_capacity": 15.0,
                "clay_content": 45.0,
                "sand_content": 20.0,
                "silt_content": 35.0,
                "bulk_density": 1.20,
                "topsoil_thickness": 25.0,
                "slope": 3.0,
                "irrigation_condition": "irrigated",
                "terrain_position": "middle",
                "soil_texture": "clay_loam",
                "obstacle_factors": [],
            },
        },
        {
            "parcel_id": "P-VERIFY-003",
            "area_code": "440281",
            "land_type": "upland",
            "fertilizer_type": "organic",
            "target_ph": 5.5,
            "soil_indicators": {
                "soil_ph": 5.2,
                "organic_matter": 8.0,
                "total_nitrogen": 0.6,
                "available_phosphorus": 5.0,
                "available_potassium": 40.0,
                "exchangeable_hydrogen": 4.0,
                "cation_exchange_capacity": 6.0,
                "clay_content": 25.0,
                "sand_content": 50.0,
                "silt_content": 25.0,
                "bulk_density": 1.45,
                "topsoil_thickness": 15.0,
                "slope": 12.0,
                "irrigation_condition": "dry",
                "terrain_position": "upper",
                "soil_texture": "sandy_loam",
                "obstacle_factors": ["low_organic_matter", "shallow_topsoil"],
            },
        },
    ]

    for p in parcels:
        # 使用 WKT 表示一个简单多边形（约 100m x 100m 的地块）
        lon = 113.35 + int(p["parcel_id"][-3:]) * 0.001
        lat = 25.15 + int(p["parcel_id"][-3:]) * 0.001
        wkt = (
            f"POLYGON(({lon} {lat},{lon+0.001} {lat},"
            f"{lon+0.001} {lat+0.001},{lon} {lat+0.001},{lon} {lat}))"
        )
        cur.execute(
            """
            INSERT INTO parcel_info
                (parcel_id, geom, area_code, land_type, fertilizer_type,
                 target_ph, soil_indicators, centroid_lon, centroid_lat)
            VALUES
                (%s, ST_GeomFromText(%s, 4326), %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (parcel_id) DO NOTHING
            """,
            (
                p["parcel_id"],
                wkt,
                p["area_code"],
                p["land_type"],
                p["fertilizer_type"],
                p["target_ph"],
                json.dumps(p["soil_indicators"]),
                lon,
                lat,
            ),
        )

    conn.commit()
    print(f"已插入 {len(parcels)} 个测试地块")
    conn.close()


def run_model_for_parcel(agent_id: str, parcel_id: str) -> dict:
    """通过 Flask app context 调用 Agent execute，返回结果。"""
    from framework.api.app import create_app
    from framework.models.user import db

    app = create_app("default")
    app.config["TESTING"] = True
    ctx = app.app_context()
    ctx.push()

    try:
        from framework.agents.manager import AgentManager

        mgr = AgentManager()
        agent = mgr.agents.get(agent_id)
        if agent is None:
            return {"error": f"Agent {agent_id} not found"}

        task = {"parcel_id": parcel_id}
        result = agent.execute(task)
        return result
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}
    finally:
        db.session.remove()
        ctx.pop()


def verify_parcel_in_db(parcel_id: str) -> dict | None:
    """验证 parcel_id 在数据库中存在，返回 soil_indicators。"""
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT parcel_id, area_code, land_type, fertilizer_type, target_ph, "
        "soil_indicators FROM parcel_info WHERE parcel_id = %s",
        (parcel_id,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "parcel_id": row[0],
        "area_code": row[1],
        "land_type": row[2],
        "fertilizer_type": row[3],
        "target_ph": row[4],
        "soil_indicators": row[5],
    }


def main():
    print("=" * 80)
    print("专题模型数据库计算流程验证报告")
    print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Step 1: 检查数据库表
    check_db_tables()

    # Step 2: 确保有测试地块和模型注册
    seed_registry()
    seed_parcel_data()

    # Step 3: 验证地块数据
    parcel_ids = ["P-VERIFY-001", "P-VERIFY-002", "P-VERIFY-003"]
    print("\n=== 地块数据验证 ===")
    for pid in parcel_ids:
        info = verify_parcel_in_db(pid)
        if info:
            print(f"\n  [{pid}]")
            print(f"    area_code: {info['area_code']}")
            print(f"    land_type: {info['land_type']}")
            print(f"    fertilizer_type: {info['fertilizer_type']}")
            print(f"    target_ph: {info['target_ph']}")
            si = info["soil_indicators"]
            if si:
                print(f"    soil_ph: {si.get('soil_ph')}")
                print(f"    organic_matter: {si.get('organic_matter')}")
                print(f"    available_phosphorus: {si.get('available_phosphorus')}")
                print(f"    available_potassium: {si.get('available_potassium')}")
        else:
            print(f"\n  [{pid}] NOT FOUND in database!")

    # Step 4: 逐模型调用
    models = [
        ("model-1", "Model-1 稳定性风险评价"),
        ("model-2", "Model-2 耕地质量等级评价"),
        ("model-3", "Model-3 障碍诊断"),
        ("model-4", "Model-4 酸化改良"),
        ("model-5", "Model-5 有机质培肥"),
    ]

    report = {
        "generated_at": datetime.now().isoformat(),
        "parcels": {},
        "models": {},
    }

    # 收集每个 parcel 的数据
    for pid in parcel_ids:
        info = verify_parcel_in_db(pid)
        if info:
            report["parcels"][pid] = info

    # 逐模型逐地块调用
    for agent_id, model_name in models:
        print(f"\n{'=' * 80}")
        print(f"  {model_name} ({agent_id})")
        print(f"{'=' * 80}")

        report["models"][agent_id] = {
            "name": model_name,
            "parcels": {},
        }

        for pid in parcel_ids:
            print(f"\n  --- Parcel: {pid} ---")
            result = run_model_for_parcel(agent_id, pid)

            # 打印结果摘要
            if "error" in result:
                print(f"  [ERROR] {result['error']}")
                report["models"][agent_id]["parcels"][pid] = {
                    "status": "error",
                    "error": result["error"],
                }
            else:
                status = result.get("status", "unknown")
                data_source = result.get("data_source", "unknown")
                simulated = result.get("simulated", None)
                persisted = result.get("persisted", None)
                print(f"  status: {status}")
                print(f"  data_source: {data_source}")
                print(f"  simulated: {simulated}")
                print(f"  persisted: {persisted}")

                # 打印 result 详情
                res = result.get("result", {})
                if res:
                    print(f"  result keys: {list(res.keys()) if isinstance(res, dict) else type(res)}")
                    # 打印关键字段
                    for key in ["risk_level", "grade", "obstacle_type", "obstacle_degree",
                                "amendment_dose", "manure_dosage", "organic_matter_grade",
                                "stability_level", "quality_grade"]:
                        if isinstance(res, dict) and key in res:
                            print(f"  {key}: {res[key]}")

                report["models"][agent_id]["parcels"][pid] = {
                    "status": status,
                    "data_source": data_source,
                    "simulated": simulated,
                    "persisted": persisted,
                    "result": res if isinstance(res, dict) else str(res),
                    "metadata": result.get("metadata", {}),
                }

    # Step 5: 持久化验证
    print(f"\n{'=' * 80}")
    print("  持久化验证（model_execution_log + 结果表）")
    print(f"{'=' * 80}")

    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
    )
    cur = conn.cursor()

    # 检查 model_execution_log
    cur.execute(
        "SELECT agent_id, parcel_id, status, id, created_at "
        "FROM model_execution_log ORDER BY created_at DESC LIMIT 30"
    )
    logs = cur.fetchall()
    print(f"\n  model_execution_log: {len(logs)} 条记录")
    for log in logs[:15]:
        print(f"    agent={log[0]}, parcel={log[1]}, status={log[2]}, exec_id={log[3]}, time={log[4]}")
    report["execution_logs"] = [
        {"agent_id": l[0], "parcel_id": l[1], "status": l[2], "execution_id": l[3]}
        for l in logs
    ]

    # 检查各结果表
    result_tables = [
        "stability_risk_result",
        "quality_grade_result",
        "obstacle_diagnosis_result",
        "acidification_remediation_result",
        "organic_matter_result",
        "comprehensive_fertility_result",
    ]
    report["result_tables"] = {}
    for table in result_tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"\n  {table}: {count} rows")
            if count > 0:
                cur.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 3")
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                for row in rows:
                    print(f"    {dict(zip(cols, row))}")
            report["result_tables"][table] = count
        except Exception as e:
            print(f"\n  {table}: ERROR - {e}")
            report["result_tables"][table] = f"error: {e}"

    conn.close()

    # Step 6: 输出 JSON 报告
    report_path = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "reports" / "2026-08-18-thematic-models-db-calculation-verify.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n{'=' * 80}")
    print(f"  JSON 报告已保存: {report_path}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
