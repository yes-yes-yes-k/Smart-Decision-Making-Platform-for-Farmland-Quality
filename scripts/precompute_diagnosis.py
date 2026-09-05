"""耕地质量评价与障碍诊断预计算入口。

从 CSV 输入生成仍在使用的 evaluation_results；酸化改良由正式 Python
过程模型按需计算，不再创建或填充 acidification_results。

用法：
    python scripts/precompute_diagnosis.py
    python scripts/precompute_diagnosis.py --csv data/farmland_diagnosis/test.csv
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("PYTHONPATH", str(PROJECT_ROOT / "src"))


DEFAULT_CSV = "data/farmland_diagnosis/test.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="耕地质量评价预计算")
    parser.add_argument(
        "--csv",
        default=DEFAULT_CSV,
        help=f"输入 CSV 路径（默认 {DEFAULT_CSV}）",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="输出 SQLite 数据库路径（默认由 DiagnosisStorage 决定）",
    )
    args = parser.parse_args()

    csv_path = args.csv
    if not os.path.exists(csv_path):
        print(f"错误：CSV 文件不存在: {csv_path}")
        return 1

    # 1. 批量评价（生成 evaluation_results 表）
    from ai_culti_demo.farmland_diagnosis.evaluation import bulk_evaluate

    print(f"批量评价: {csv_path}")
    eval_result = bulk_evaluate(csv_path, args.db)
    if eval_result.get("status") != "ok":
        print(f"批量评价失败: {eval_result}")
        return 1
    print(f"  处理 {eval_result['processed']} 条记录, 错误 {len(eval_result['errors'])} 条")
    if eval_result["errors"]:
        for err in eval_result["errors"][:5]:
            print(f"    - {err}")

    # 显示输出 DB 路径
    from ai_culti_demo.farmland_diagnosis.storage import DiagnosisStorage

    storage = DiagnosisStorage(args.db)
    print(f"\n输出数据库: {storage.db_path}")
    if os.path.exists(storage.db_path):
        size_kb = os.path.getsize(storage.db_path) / 1024
        print(f"  大小: {size_kb:.1f} KB")

    print("\n预计算完成。model-3 可使用评价数据；model-4 继续按需调用正式过程模型。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
