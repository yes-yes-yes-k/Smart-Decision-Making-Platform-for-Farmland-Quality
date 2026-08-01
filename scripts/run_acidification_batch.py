"""批量酸化模型 CSV 计算工具（CLI）。

用法：
    python scripts/run_acidification_batch.py --input <input.csv> --output <output.csv> \
        --land <paddy|upland> --fertilizer <urea|compound>

注意：run_csv 不做输入数据越界校验，请自行检查输入数据质量。
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

from ai_culti_demo.farmland_diagnosis.acidification import run_csv


def main():
    parser = argparse.ArgumentParser(description="酸化模型批量 CSV 计算工具")
    parser.add_argument("--input", required=True, help="输入 CSV 路径（需含 SJD/pH、Hex、Alex 列）")
    parser.add_argument("--output", required=True, help="输出 CSV 路径")
    parser.add_argument("--land", required=True, choices=["paddy", "upland"], help="土地类型")
    parser.add_argument("--fertilizer", required=True, choices=["urea", "compound"], help="肥料类型")
    args = parser.parse_args()

    try:
        df = run_csv(args.input, args.output, args.land, args.fertilizer)
        print(f"批量计算完成：共处理 {len(df)} 行，输出写入 {args.output}")
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
