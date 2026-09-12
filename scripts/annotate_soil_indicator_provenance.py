"""标注 `parcel_info.soil_indicators` 中回填字段的来源。

背景：Model-4/5 需要的交换性氢、交换性铝、全氮等字段由
``scripts/link_soil_indicators.py`` 用三普采样表的全局平均值批量回填，字段“有值”
但并非地块实测值。本脚本识别这类“跨地块常量”字段，并把来源写入
``soil_indicators.provenance``，使模型守卫和对外展示能够区分实测值与回填值。

判定条件（见 openspec/changes/add-input-provenance-and-report-number-audit/design.md）：
不同取值数不超过 ``--max-distinct``（默认 3），且最高频取值占比不低于
``--min-share``（默认 0.95）。结构性枚举字段（地类、质地、灌溉条件等）不参与判定。

用法：
    python scripts/annotate_soil_indicator_provenance.py                  # 只读预览
    python scripts/annotate_soil_indicator_provenance.py --apply          # 写入来源标记
    python scripts/annotate_soil_indicator_provenance.py --revert         # 移除本脚本写入的标记
    python scripts/annotate_soil_indicator_provenance.py --field total_n  # 只处理指定字段

默认只读；``--apply`` 才写入。重复运行不会修改已标注字段；``--revert`` 只移除
``region_mean_backfill`` / ``default`` 两类来源标记，不触碰指标数值与其他字段。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.domain.provenance import (  # noqa: E402
    PROVENANCE_KEY,
    SOURCE_MEASURED,
    SOURCE_REGION_MEAN_BACKFILL,
    detect_constant_fields,
    source_for_field,
)

logger = logging.getLogger("annotate_soil_indicator_provenance")


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


def fetch_snapshots(cur) -> list[dict[str, Any]]:
    cur.execute("SELECT soil_indicators FROM parcel_info WHERE soil_indicators IS NOT NULL")
    return [row[0] or {} for row in cur.fetchall()]


def preview(candidates: Sequence[dict[str, Any]], total_parcels: int) -> None:
    if not candidates:
        print("未发现符合条件（跨地块常量）的未标注字段。")
        return
    print(f"共 {total_parcels} 个地块，识别到 {len(candidates)} 个候选回填字段：")
    print(f"{'字段':<28}{'不同取值':>8}{'最高频占比':>12}{'众数值':>20}")
    for item in candidates:
        print(
            f"{item['field']:<28}{item['distinct']:>8}{item['top_share']:>11.1%}"
            f"{str(item['top_value'])[:18]:>20}"
        )


def apply_marks(cur, sources: dict[str, str]) -> dict[str, int]:
    """逐字段写入来源标记，跳过已标注字段。返回 {字段: 受影响行数}。"""
    affected: dict[str, int] = {}
    for field, source in sources.items():
        cur.execute(
            """
            UPDATE parcel_info
            SET soil_indicators = jsonb_set(
                    soil_indicators::jsonb,
                    ARRAY['provenance', %s],
                    to_jsonb(%s::text),
                    true
                )::json
            WHERE (soil_indicators::jsonb) ? %s
              AND NOT ((soil_indicators::jsonb -> 'provenance') ? %s)
            """,
            (field, source, field, field),
        )
        affected[field] = cur.rowcount
    return affected


def revert_marks(cur, fields: Sequence[str]) -> dict[str, int]:
    """移除本脚本写入的来源标记，不触碰其他字段。"""
    affected: dict[str, int] = {}
    for field in fields:
        cur.execute(
            """
            UPDATE parcel_info
            SET soil_indicators = (soil_indicators::jsonb #- ARRAY['provenance', %s])::json
            WHERE (soil_indicators::jsonb -> 'provenance') ? %s
              AND (soil_indicators::jsonb -> 'provenance' ->> %s) <> %s
            """,
            (field, field, field, SOURCE_MEASURED),
        )
        affected[field] = cur.rowcount
    return affected


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="标注回填指标来源（默认只读）")
    parser.add_argument("--apply", action="store_true", help="写入来源标记")
    parser.add_argument("--revert", action="store_true", help="移除本脚本写入的来源标记")
    parser.add_argument("--field", action="append", default=None, help="只处理指定字段，可重复")
    parser.add_argument(
        "--source",
        default=None,
        help="统一指定来源取值；缺省时按字段推断（目标 pH、肥料类型记为 default）",
    )
    parser.add_argument("--max-others", type=int, default=10, help="允许的离群地块数上限")
    parser.add_argument("--min-share", type=float, default=0.95, help="最高频取值占比下限")
    parser.add_argument("--json-out", default=None, help="把候选清单写入 JSON 文件")
    args = parser.parse_args(argv)

    if args.apply and args.revert:
        parser.error("--apply 与 --revert 不能同时使用")

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    conn = db_connection()
    try:
        cur = conn.cursor()
        snapshots = fetch_snapshots(cur)
        candidates = detect_constant_fields(
            snapshots, max_others=args.max_others, min_share=args.min_share
        )
        if args.field:
            wanted = set(args.field)
            candidates = [item for item in candidates if item["field"] in wanted]

        preview(candidates, len(snapshots))
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(
                    {
                        "parcels": len(snapshots),
                        "max_others": args.max_others,
                        "min_share": args.min_share,
                        "candidates": candidates,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"候选清单 -> {args.json_out}")

        if args.revert:
            fields = args.field or [item["field"] for item in candidates]
            affected = revert_marks(cur, fields)
            conn.commit()
            for field, count in affected.items():
                logger.info("已移除来源标记 %s：%d 行", field, count)
            return 0

        if not args.apply:
            print("\n默认只读，未写入数据库。确认无误后使用 --apply 写入。")
            return 0

        fields = args.field or [item["field"] for item in candidates]
        sources = {field: (args.source or source_for_field(field)) for field in fields}
        affected = apply_marks(cur, sources)
        conn.commit()
        for field, count in affected.items():
            logger.info("已标注 %s = %s：%d 行", field, sources[field], count)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
