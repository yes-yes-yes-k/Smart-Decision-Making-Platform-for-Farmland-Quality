"""专题模型数据导入脚本（V3.0）。

将 D:\\destkop\\模型1-5 路径中的 5 个专题模型数据导入到 V3.0 数据库对应的 5 张结果表。

用法:
    python scripts/import_model_data.py --model 1        # 导入模型1
    python scripts/import_model_data.py --model 2 3      # 导入模型2和3
    python scripts/import_model_data.py --all            # 导入全部5个模型

执行流程:
    1. 检查并填充 thematic_model_registry（FK 前置）
    2. 为每个模型创建 model_execution_log 记录（FK 前置）
    3. 读取数据文件 → 字段映射 → ORM 批量插入结果表
    4. 更新 execution log 状态和耗时
"""
import argparse
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# 加载 .env 配置
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from framework.api.app import create_app
from framework.models.user import db
import framework.models  # noqa: F401  触发模型注册
from framework.models.thematic_model import (
    ThematicModelRegistry,
    ModelExecutionLog,
    StabilityRiskResult,
    QualityGradeResult,
    ObstacleDiagnosisResult,
    AcidificationRemediationResult,
    OrganicMatterResult,
)
from scripts.model_field_mappings import (
    DATA_SOURCES,
    MODEL_REGISTRY,
    EXECUTION_META,
    MODEL1_MAPPING,
    MODEL1_INPUT_FIELDS,
    MODEL2_MAPPING,
    MODEL2_INPUT_FIELDS,
    MODEL3_MAPPING,
    MODEL4_MAPPING,
    MODEL5_MAPPING,
)

# agent_id 与命令行参数 --model 的映射
MODEL_ARG_MAP = {
    "1": "model-1",
    "2": "model-2",
    "3": "model-3",
    "4": "model-5",   # --model 4 导入数据文件"模型4" → organic_matter_result (agent_id=model-5)
    "5": "model-4",   # --model 5 导入数据文件"模型5" → acidification_remediation_result (agent_id=model-4)
}

# agent_id → 导入函数映射
IMPORT_FUNCTIONS = {}


def ensure_registry():
    """确保 thematic_model_registry 已注册 model-1 ~ model-6。"""
    existing = {r.agent_id for r in db.session.query(ThematicModelRegistry).all()}
    added = 0
    for meta in MODEL_REGISTRY:
        if meta["agent_id"] not in existing:
            db.session.add(ThematicModelRegistry(**meta))
            added += 1
    if added:
        db.session.commit()
        print(f"[registry] 新增 {added} 条注册记录（共 {len(MODEL_REGISTRY)} 个模型）")
    else:
        print(f"[registry] 已有全部 {len(MODEL_REGISTRY)} 个模型注册记录")


def create_execution_log(agent_id, parcel_id=None):
    """创建 model_execution_log 记录，返回 (log_id, start_time)。"""
    meta = EXECUTION_META[agent_id]
    trace_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    log = ModelExecutionLog(
        trace_id=trace_id,
        agent_id=agent_id,
        question_type=meta["question_type"],
        parcel_id=parcel_id,
        status="running",
        routing_mode=meta["routing_mode"],
        routing_status=meta["routing_status"],
        simulated=False,
        started_at=started_at,
    )
    db.session.add(log)
    db.session.commit()
    return log.id, started_at


def update_execution_log(log_id, started_at, status, row_count, error=None):
    """更新 model_execution_log 记录状态和耗时。"""
    completed_at = datetime.now(timezone.utc)
    duration_ms = (completed_at - started_at).total_seconds() * 1000
    log = db.session.get(ModelExecutionLog, log_id)
    log.status = status
    log.completed_at = completed_at
    log.duration_ms = duration_ms
    log.output_result = {"row_count": row_count}
    if error:
        log.error_message = str(error)
    db.session.commit()
    return duration_ms


def finalize_model_logs(agent_id, model_started_at, row_count, status="ok", error=None):
    """批量更新某模型的全部 execution log 状态为 ok/error。

    每行数据创建了一条 execution log（status='running'），导入完成后批量更新。
    """
    import json
    from sqlalchemy import text
    completed_at = datetime.now(timezone.utc)
    duration_ms = (completed_at - model_started_at).total_seconds() * 1000
    output_json = json.dumps({"row_count": row_count}, ensure_ascii=False)
    error_msg = str(error) if error else None
    db.session.execute(text(
        "UPDATE model_execution_log "
        "SET status = :status, completed_at = :ct, duration_ms = :dm, "
        "output_result = CAST(:out AS jsonb), error_message = :err "
        "WHERE agent_id = :aid AND status = 'running'"
    ), {
        "status": status, "ct": completed_at, "dm": duration_ms,
        "out": output_json, "err": error_msg, "aid": agent_id,
    })
    db.session.commit()
    updated = db.session.execute(text(
        "SELECT count(*) FROM model_execution_log WHERE agent_id = :aid AND status = :st"
    ), {"aid": agent_id, "st": status}).scalar()
    print(f"  [finalize] {agent_id}: {updated} 条 log 更新为 {status}")
    return updated


def read_csv_auto(path):
    """自动检测编码读取 CSV。"""
    for enc in ("utf-8", "gbk", "gb18030", "utf-8-sig"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"无法解码 CSV: {path}")


def safe_float(val):
    """安全转换为 float，失败返回 None。"""
    if pd.isna(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_str(val, max_len=None):
    """安全转换为 str，NaN/None 返回 None；可选截断到 max_len。"""
    if pd.isna(val):
        return None
    s = str(val).strip() if isinstance(val, str) else str(val)
    if max_len and len(s) > max_len:
        s = s[:max_len]
    return s


# ============================================================================
# 各模型导入函数
# ============================================================================

def import_model1():
    """模型1：耕地质量稳定性与退化风险结果.xlsx → stability_risk_result (agent_id=model-1)。"""
    src = DATA_SOURCES["model-1"]
    print(f"\n[模型1] 读取 {src['file']}")
    df = pd.read_excel(src["file"], sheet_name=src["sheet"])
    print(f"  数据: {len(df)} 行, {len(df.columns)} 列")

    # 每行单独创建 execution log（因为 stability_risk_result.execution_id 唯一）
    # 但数据行数多时开销大；改为每行一个 execution_id
    rows_inserted = 0
    for _, row in df.iterrows():
        parcel_id = safe_str(row.get("TYBH"))
        log_id, started_at = create_execution_log("model-1", parcel_id=parcel_id)

        # 构建结果列
        result = {"execution_id": log_id, "parcel_id": parcel_id}
        for src_col, tgt_col in MODEL1_MAPPING.items():
            if src_col == "TYBH":
                continue
            val = row.get(src_col)
            if tgt_col.endswith(("_type", "_factor")):
                result[tgt_col] = safe_str(val)
            else:
                result[tgt_col] = safe_float(val)

        # 构建 input_snapshot
        input_snapshot = {}
        for field in MODEL1_INPUT_FIELDS:
            if field in row.index:
                val = row[field]
                if pd.notna(val):
                    input_snapshot[field] = val.item() if hasattr(val, "item") else val
        result["input_snapshot"] = input_snapshot

        db.session.add(StabilityRiskResult(**result))
        rows_inserted += 1

    db.session.commit()
    return rows_inserted


def import_model2():
    """模型2：Farmland_quality_Level_Database.csv → quality_grade_result (agent_id=model-2)。"""
    src = DATA_SOURCES["model-2"]
    print(f"\n[模型2] 读取 {src['file']}")
    df = read_csv_auto(src["file"])
    print(f"  数据: {len(df)} 行, {len(df.columns)} 列")

    # 模型2是输入数据库，无直接结果列；每行一条 execution log + 结果记录
    rows_inserted = 0
    for _, row in df.iterrows():
        parcel_id = safe_str(row.get("SiteID"))
        log_id, started_at = create_execution_log("model-2", parcel_id=parcel_id)

        # 构建结果记录（quality_grade 和 composite_index 是 NOT NULL，用占位值）
        result = {
            "execution_id": log_id,
            "parcel_id": parcel_id,
            "quality_grade": "0",          # 占位：待模型计算
            "composite_index": 0.0,        # 占位：待模型计算
            "simulated": True,             # 标记为模拟（输入数据未计算结果）
        }

        # 构建指标列表和 input_snapshot
        indicators = []
        input_snapshot = {}
        indicator_names = {
            "SJD": "soil_ph", "YJZ": "organic_matter", "YXL": "available_phosphorus",
            "SXJ": "available_potassium", "TRRZ": "soil_bulk_density",
            "YXTCHD": "topsoil_thickness", "GCHD": "effective_soil_depth",
        }
        for src_col, eng_name in indicator_names.items():
            if src_col in row.index:
                raw_val = safe_float(row[src_col])
                if raw_val is not None:
                    indicators.append({"name": eng_name, "raw_value": raw_val})
                    input_snapshot[eng_name] = raw_val

        # 其他输入字段
        for field in MODEL2_INPUT_FIELDS:
            if field in row.index and field not in indicator_names:
                val = row[field]
                if pd.notna(val):
                    input_snapshot[field] = val.item() if hasattr(val, "item") else val

        result["indicators"] = indicators
        result["input_snapshot"] = input_snapshot

        db.session.add(QualityGradeResult(**result))
        rows_inserted += 1

    db.session.commit()
    return rows_inserted


def import_model3():
    """模型3：test_result.csv → obstacle_diagnosis_result (agent_id=model-3)。"""
    src = DATA_SOURCES["model-3"]
    print(f"\n[模型3] 读取 {src['file']}")
    df = read_csv_auto(src["file"])
    print(f"  数据: {len(df)} 行, {len(df.columns)} 列")

    rows_inserted = 0
    for _, row in df.iterrows():
        # 模型3 CSV 无 parcel_id 列，使用行号作为占位
        parcel_id = f"model3-row-{rows_inserted + 1}"
        log_id, started_at = create_execution_log("model-3", parcel_id=parcel_id)

        result = {"execution_id": log_id, "parcel_id": parcel_id}
        for src_col, tgt_col in MODEL3_MAPPING.items():
            val = row.get(src_col)
            if tgt_col.endswith(("_type", "_factor", "quality_grade")):
                # VARCHAR(64) 列需截断
                result[tgt_col] = safe_str(val, max_len=64)
            else:
                result[tgt_col] = safe_float(val)

        db.session.add(ObstacleDiagnosisResult(**result))
        rows_inserted += 1

    db.session.commit()
    return rows_inserted


def import_model4():
    """模型4（agent_id=model-5）：SG旱地-Dose-RF_Manual_splits.xlsx → organic_matter_result。"""
    src = DATA_SOURCES["model-5"]
    print(f"\n[模型4→model-5] 读取 {src['file']}")
    # 合并 Xtrain 和 Xtest sheets
    frames = []
    for sheet in src["sheets"]:
        df_part = pd.read_excel(src["file"], sheet_name=sheet)
        df_part["_source_sheet"] = sheet
        frames.append(df_part)
    df = pd.concat(frames, ignore_index=True)
    # 去除列名尾随空格
    df.columns = df.columns.str.strip()
    print(f"  数据: {len(df)} 行, {len(df.columns)} 列（合并 {src['sheets']}）")

    # organic_matter_result.execution_id 唯一约束，每行一条 execution log
    rows_inserted = 0
    for _, row in df.iterrows():
        log_id, started_at = create_execution_log("model-5")

        result = {"execution_id": log_id}
        for src_col, tgt_col in MODEL4_MAPPING.items():
            # src_col 也需 strip（Excel 列名 'TN ' 等）
            val = row.get(src_col.strip())
            if tgt_col == "organic_fertilizer_type":
                result[tgt_col] = safe_str(val)
            else:
                result[tgt_col] = safe_float(val)

        db.session.add(OrganicMatterResult(**result))
        rows_inserted += 1

    db.session.commit()
    return rows_inserted


def import_model5():
    """模型5（agent_id=model-4）：04_旱地复合肥计算结果.csv → acidification_remediation_result。"""
    src = DATA_SOURCES["model-4"]
    print(f"\n[模型5→model-4] 读取 {src['file']}")
    df = read_csv_auto(src["file"])
    print(f"  数据: {len(df)} 行, {len(df.columns)} 列")

    rows_inserted = 0
    for _, row in df.iterrows():
        parcel_id = safe_str(row.get("TYBH"))
        log_id, started_at = create_execution_log("model-4", parcel_id=parcel_id)

        result = {"execution_id": log_id, "parcel_id": parcel_id}
        for src_col, tgt_col in MODEL5_MAPPING.items():
            if src_col == "TYBH":
                continue
            result[tgt_col] = safe_float(row.get(src_col))

        # 设置模型版本
        result["model_version"] = "process_v2_20260801"

        db.session.add(AcidificationRemediationResult(**result))
        rows_inserted += 1

    db.session.commit()
    return rows_inserted


# 注册导入函数
IMPORT_FUNCTIONS = {
    "model-1": import_model1,
    "model-2": import_model2,
    "model-3": import_model3,
    "model-5": import_model4,   # 数据文件模型4 → agent_id=model-5
    "model-4": import_model5,   # 数据文件模型5 → agent_id=model-4
}


def verify_import(agent_id, expected_rows):
    """验证导入结果。"""
    table_map = {
        "model-1": "stability_risk_result",
        "model-2": "quality_grade_result",
        "model-3": "obstacle_diagnosis_result",
        "model-4": "acidification_remediation_result",
        "model-5": "organic_matter_result",
    }
    table = table_map[agent_id]
    from sqlalchemy import text
    count = db.session.execute(text(f"SELECT count(*) FROM {table}")).scalar()
    status = "OK" if count == expected_rows else "MISMATCH"
    print(f"  [验证] {table}: {count} 行（预期 {expected_rows}）{status}")
    return count == expected_rows


def main():
    parser = argparse.ArgumentParser(description="导入专题模型数据到 V3.0 数据库")
    parser.add_argument("--model", nargs="+", help="导入指定模型（1-5），可多选")
    parser.add_argument("--all", action="store_true", help="导入全部 5 个模型")
    args = parser.parse_args()

    if not args.model and not args.all:
        parser.print_help()
        sys.exit(1)

    if args.all:
        agent_ids = ["model-1", "model-2", "model-3", "model-5", "model-4"]
    else:
        agent_ids = []
        for m in args.model:
            if m not in MODEL_ARG_MAP:
                print(f"错误：未知模型编号 '{m}'，可选 1-5")
                sys.exit(1)
            agent_ids.append(MODEL_ARG_MAP[m])

    # 初始化 Flask 应用
    config_name = os.environ.get("FLASK_ENV") or "default"
    app = create_app(config_name)

    with app.app_context():
        # Step 1: 确保注册表已填充
        ensure_registry()

        # Step 2: 逐个导入
        results = {}
        for agent_id in agent_ids:
            func = IMPORT_FUNCTIONS.get(agent_id)
            if not func:
                print(f"[跳过] 无导入函数: {agent_id}")
                continue

            print(f"\n{'='*60}")
            print(f"开始导入 {agent_id}")
            start = time.time()
            try:
                row_count = func()
                elapsed = time.time() - start
                print(f"  导入完成: {row_count} 行, 耗时 {elapsed:.2f}s")
                # 批量更新 execution log 状态为 ok
                finalize_model_logs(agent_id, start, row_count, status="ok")
                results[agent_id] = row_count
            except Exception as e:
                print(f"  导入失败: {e}")
                db.session.rollback()
                finalize_model_logs(agent_id, start, 0, status="error", error=e)
                results[agent_id] = -1

        # Step 3: 验证
        print(f"\n{'='*60}")
        print("验证导入结果:")
        all_ok = True
        for agent_id, expected in results.items():
            if expected < 0:
                print(f"  {agent_id}: 导入失败，跳过验证")
                all_ok = False
                continue
            ok = verify_import(agent_id, expected)
            if not ok:
                all_ok = False

        # 验证 execution log
        from sqlalchemy import text
        log_count = db.session.execute(
            text("SELECT count(*) FROM model_execution_log")
        ).scalar()
        print(f"\n[验证] model_execution_log: {log_count} 条记录")

        # 验证视图
        try:
            view_count = db.session.execute(
                text("SELECT count(*) FROM v_model_execution_summary")
            ).scalar()
            print(f"[验证] v_model_execution_summary 视图: {view_count} 行")
        except Exception as e:
            print(f"[警告] 视图查询失败: {e}")

        print(f"\n{'='*60}")
        if all_ok:
            print("全部导入验证通过！")
        else:
            print("部分导入存在问题，请检查上方日志。")


if __name__ == "__main__":
    main()
