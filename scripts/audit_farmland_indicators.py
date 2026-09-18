"""Generate a JSON or Markdown audit of the eight canonical indicators."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from framework.domain.statistics import audit_indicator_rows
from scripts.migrate_indicator_provenance import db_connection, load_dotenv


def as_markdown(report: dict) -> str:
    lines = [
        "# 耕地指标质量审计报告",
        "",
        f"- 生成时间：{report['generatedAt']}",
        f"- 数据时间：{report['dataAsOf'] or '未知'}",
        f"- 地块数量：{report['parcelCount']}",
        f"- 分级版本：{report['classificationVersion']}",
        "",
        "| 指标 | 非空率 | 可解析 | 最小值 | 最大值 | 唯一值数 | 异常/未分类 | 质量标记 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for metric in report["metrics"]:
        lines.append(
            f"| {metric['label']}（{metric['metricKey']}） | "
            f"{metric['nonEmptyRate']:.4f}% | {metric['parseableCount']} | "
            f"{metric['min']} | {metric['max']} | {metric['uniqueValueCount']} | "
            f"{metric['unclassifiedCount'] + metric['parseFailureCount']} | "
            f"{', '.join(metric['qualityFlags']) or 'none'} |"
        )
    lines.extend([
        "",
        "> `isImputed=false` 仅表示后端未执行回填，不等同于已确认是田间实测；"
        "`source_unverified` 表示仍需业务方核实源数据采集方式。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    load_dotenv()
    connection = db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT soil_indicators, updated_at FROM parcel_info ORDER BY id")
            rows = [
                {"soil_indicators": soil_indicators, "updated_at": updated_at}
                for soil_indicators, updated_at in cursor.fetchall()
            ]
    finally:
        connection.close()

    report = audit_indicator_rows(rows)
    content = (
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.format == "json"
        else as_markdown(report)
    )
    if args.output:
        output = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content + "\n", encoding="utf-8")
        print(output)
    else:
        print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
