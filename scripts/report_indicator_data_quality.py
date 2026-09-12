"""耕地统计指标数据质量报告（只读）。

用途：核对「一张图」8 项统计指标在当前数据库中的可用程度，输出：
- 每项指标的填充率、缺失/无法解析/不在有效值域的数量（即 unclassified 构成）
- 数值分布（min / max / 均值 / 中位数）与各等级档位的地块数、占比
- 数值集中度（distinct 值数量、最高频值占比），用于识别「区域平均值回填」造成的同值堆积
- 按县（area_code）的指标均值与地块数，用于判断空间分布是否可信
- soil_indicators 中全部键的填充率清单（含 Model-4/5 所需字段）

默认只读，不做任何写入。分档定义直接取自
framework.domain.statistics.indicator_definitions，避免与统计接口口径漂移。

用法：
    python scripts/report_indicator_data_quality.py
    python scripts/report_indicator_data_quality.py --json-out docs/generated/indicator-data-quality.json
    python scripts/report_indicator_data_quality.py --md-out docs/generated/indicator-data-quality.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.domain.statistics.indicator_definitions import (  # noqa: E402
    INDICATOR_DEFINITIONS,
)


def load_dotenv() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def db_connection():
    import psycopg2

    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
        connect_timeout=10,
    )


def fetch_parcels() -> list[dict[str, Any]]:
    conn = db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT parcel_id, area_code, soil_indicators, "
            "       (geom IS NOT NULL) AS has_geom "
            "FROM parcel_info ORDER BY parcel_id"
        )
        rows = [
            {
                "parcel_id": row[0],
                "area_code": row[1],
                "indicators": row[2] or {},
                "has_geom": bool(row[3]),
            }
            for row in cur.fetchall()
        ]
        cur.close()
        return rows
    finally:
        conn.close()


def _reason(definition, raw: Any) -> str | None:
    """分类 unclassified 的具体原因，None 表示归类成功。"""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return "missing"
    parsed = definition.parse(raw)
    if parsed is None:
        return "unparsable"
    return "out_of_range"


def analyse_indicator(definition, parcels: list[dict[str, Any]]) -> dict[str, Any]:
    values: list[float] = []
    bucket_counts: Counter = Counter()
    reasons: Counter = Counter()
    parsed_raw: list[Any] = []
    samples: list[dict[str, Any]] = []
    value_counter: Counter = Counter()

    for parcel in parcels:
        raw = parcel["indicators"].get(definition.source_field)
        parsed = definition.parse(raw)
        if parsed is None:
            reasons[_reason(definition, raw)] += 1
            if len(samples) < 5:
                samples.append({"parcel_id": parcel["parcel_id"], "value": raw})
            continue
        values.append(parsed)
        value_counter[round(parsed, 6)] += 1
        parsed_raw.append(raw)
        bucket = definition.classify(raw)
        if bucket is None:
            reasons["out_of_range"] += 1
            if len(samples) < 5:
                samples.append({"parcel_id": parcel["parcel_id"], "value": raw})
        else:
            bucket_counts[bucket.key] += 1

    total = len(parcels)
    classified = sum(bucket_counts.values())
    distinct = len(value_counter)
    top_value = value_counter.most_common(1)[0] if value_counter else (None, 0)
    return {
        "key": definition.key,
        "label": definition.label,
        "source_field": definition.source_field,
        "unit": definition.unit,
        "total": total,
        "filled": len(values),
        "fill_rate": round(len(values) / total, 4) if total else 0.0,
        "classified": classified,
        "unclassified": total - classified,
        "unclassified_reasons": dict(reasons),
        "unclassified_samples": samples,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "mean": round(sum(values) / len(values), 4) if values else None,
        "median": round(median(values), 4) if values else None,
        "distinct_values": distinct,
        "top_value": top_value[0],
        "top_value_share": round(top_value[1] / len(values), 4) if values else None,
        "buckets": [
            {
                "key": bucket.key,
                "label": bucket.label,
                "range": bucket.range_label,
                "parcels": bucket_counts.get(bucket.key, 0),
                "share_of_classified": (
                    round(bucket_counts.get(bucket.key, 0) / classified, 4) if classified else 0.0
                ),
            }
            for bucket in definition.buckets
        ],
    }


def analyse_indicator_keys(parcels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """soil_indicators 中出现的全部键及填充率（含非统计指标字段）。"""
    total = len(parcels)
    filled_key: Counter = Counter()
    non_null: Counter = Counter()
    for parcel in parcels:
        for key, value in parcel["indicators"].items():
            filled_key[key] += 1
            if value is not None and value != "":
                non_null[key] += 1
    return [
        {
            "key": key,
            "present": filled_key[key],
            "non_null": non_null[key],
            "non_null_rate": round(non_null[key] / total, 4) if total else 0.0,
        }
        for key in sorted(filled_key, key=lambda k: (-non_null[k], k))
    ]


def analyse_by_county(parcels: list[dict[str, Any]], min_parcels: int = 50) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for parcel in parcels:
        grouped.setdefault(parcel["area_code"] or "(空)", []).append(parcel)
    rows = []
    for area_code, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        if len(items) < min_parcels:
            continue
        entry: dict[str, Any] = {"area_code": area_code, "parcels": len(items), "means": {}}
        for definition in INDICATOR_DEFINITIONS.values():
            nums = [
                parsed
                for parsed in (definition.parse(item["indicators"].get(definition.source_field)) for item in items)
                if parsed is not None
            ]
            entry["means"][definition.key] = round(sum(nums) / len(nums), 4) if nums else None
        rows.append(entry)
    return rows


def build_report() -> dict[str, Any]:
    parcels = fetch_parcels()
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "database": {
            "host": os.environ.get("DB_HOST"),
            "port": os.environ.get("DB_PORT"),
            "name": os.environ.get("DB_NAME"),
        },
        "parcels": {
            "total": len(parcels),
            "with_geometry": sum(1 for item in parcels if item["has_geom"]),
        },
        "indicators": [analyse_indicator(definition, parcels) for definition in INDICATOR_DEFINITIONS.values()],
        "indicator_keys": analyse_indicator_keys(parcels),
        "by_county": analyse_by_county(parcels),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 耕地统计指标数据质量报告")
    lines.append("")
    lines.append(f"- 生成时间：{report['generated_at']}")
    db = report["database"]
    lines.append(f"- 数据库：{db['host']}:{db['port']}/{db['name']}")
    lines.append(f"- 地块总数：{report['parcels']['total']}，有几何：{report['parcels']['with_geometry']}")
    lines.append("")
    lines.append("## 1. 概览")
    lines.append("")
    lines.append("| 指标 | 字段 | 填充率 | 已归类 | 未归类 | 未归类原因 | min | max | 均值 | 中位数 | 不同值 | 最高频值占比 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for item in report["indicators"]:
        reasons = "、".join(f"{k}={v}" for k, v in item["unclassified_reasons"].items()) or "-"
        lines.append(
            "| {label} | `{field}` | {rate:.1%} | {cls} | {un} | {reasons} | {mn} | {mx} | {mean} | {med} | {dv} | {top:.1%} |".format(
                label=item["label"], field=item["source_field"], rate=item["fill_rate"],
                cls=item["classified"], un=item["unclassified"], reasons=reasons,
                mn=item["min"], mx=item["max"], mean=item["mean"], med=item["median"],
                dv=item["distinct_values"],
                top=(item["top_value_share"] or 0.0),
            )
        )
    lines.append("")
    lines.append("> 「最高频值占比」接近 100% 说明该指标在同一值上高度堆积，通常来自按区域平均值回填，而不是地块级实测。")
    lines.append("")
    lines.append("## 2. 各指标等级分布")
    for item in report["indicators"]:
        lines.append("")
        lines.append(f"### {item['label']}（{item['unit']}）")
        lines.append("")
        if item["unclassified"]:
            reasons = "、".join(f"{k}={v}" for k, v in item["unclassified_reasons"].items())
            lines.append(f"未归类 {item['unclassified']} 个（{reasons}）。")
            lines.append("")
        lines.append("| 等级 | 区间 | 地块数 | 占已归类 |")
        lines.append("| --- | --- | --- | --- |")
        for bucket in item["buckets"]:
            lines.append(
                f"| {bucket['label']} | {bucket['range']} | {bucket['parcels']} | {bucket['share_of_classified']:.1%} |"
            )
    lines.append("")
    lines.append("## 3. soil_indicators 全部字段填充率")
    lines.append("")
    lines.append("| 字段 | 出现 | 非空 | 非空占比 |")
    lines.append("| --- | --- | --- | --- |")
    for row in report["indicator_keys"]:
        lines.append(f"| `{row['key']}` | {row['present']} | {row['non_null']} | {row['non_null_rate']:.1%} |")
    lines.append("")
    lines.append("## 4. 按县（area_code）指标均值")
    lines.append("")
    keys = [item["key"] for item in report["indicators"]]
    lines.append("| area_code | 地块数 | " + " | ".join(keys) + " |")
    lines.append("| --- | --- | " + " | ".join("---" for _ in keys) + " |")
    for row in report["by_county"]:
        cells = " | ".join(str(row["means"].get(key)) for key in keys)
        lines.append(f"| {row['area_code']} | {row['parcels']} | {cells} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="耕地统计指标数据质量报告（只读）")
    parser.add_argument("--json-out", default=None, help="JSON 输出路径")
    parser.add_argument("--md-out", default=None, help="Markdown 输出路径")
    parser.add_argument("--quiet", action="store_true", help="只写文件，不打印摘要")
    args = parser.parse_args()

    load_dotenv()
    report = build_report()

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.md_out:
        Path(args.md_out).write_text(render_markdown(report), encoding="utf-8")

    if not args.quiet:
        print(f"地块总数 {report['parcels']['total']}，有几何 {report['parcels']['with_geometry']}")
        for item in report["indicators"]:
            print(
                "  {label:<8} 填充 {rate:>6.1%}  已归类 {cls:>5}  未归类 {un:>4}  "
                "min={mn} max={mx} 均值={mean} 不同值={dv} 最高频占比={top:.1%}".format(
                    label=item["label"], rate=item["fill_rate"], cls=item["classified"],
                    un=item["unclassified"], mn=item["min"], mx=item["max"],
                    mean=item["mean"], dv=item["distinct_values"],
                    top=(item["top_value_share"] or 0.0),
                )
            )
        if args.json_out:
            print(f"JSON -> {args.json_out}")
        if args.md_out:
            print(f"Markdown -> {args.md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
