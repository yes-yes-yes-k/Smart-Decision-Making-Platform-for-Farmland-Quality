"""按来源台账标注 `parcel_info.soil_indicators` 中字段的来源。

来源由**写入方**决定，不由数值分布推断：

- `scripts/import_real_parcels.py` 从 2024 年测试地块 shp 逐地块映射的字段 -> `measured`；
- `scripts/link_soil_indicators.py` 用三普采样表平均值批量填充的字段 -> `region_mean_backfill`；
- 导入脚本写入的固定默认值（`target_ph`、`fertilizer_type`） -> `default`。

台账定义在 ``framework/domain/provenance.SOURCE_MANIFEST``，本脚本只负责把它写入数据库。

用法：
    python scripts/annotate_soil_indicator_provenance.py                 # 只读预览
    python scripts/annotate_soil_indicator_provenance.py --apply         # 写入来源标记
    python scripts/annotate_soil_indicator_provenance.py --revert        # 移除本脚本写入的标记
    python scripts/annotate_soil_indicator_provenance.py --field total_n --apply

默认只读；``--apply`` 才写入，重复运行不会修改已标注字段；``--revert`` 只移除台账中
字段的来源标记，不触碰指标数值与其他字段。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.domain.provenance import (  # noqa: E402
    MANIFEST_BASIS,
    SOURCE_MANIFEST,
    SOURCE_MEASURED,
    manifest_for,
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


def count_parcels(cur) -> tuple[int, int]:
    """返回（地块总数，已带 provenance 的地块数）。"""
    cur.execute("select count(*) from parcel_info")
    total = cur.fetchone()[0]
    cur.execute("select count(*) from parcel_info where (soil_indicators::jsonb) ? 'provenance'")
    return total, cur.fetchone()[0]


def count_field(cur, field: str) -> tuple[int, int]:
    """返回（该字段有值的地块数，该字段已标注来源的地块数）。"""
    cur.execute(
        """
        select count(*) as present,
               count(*) filter (where (soil_indicators::jsonb -> 'provenance') ? %s) as marked
        from parcel_info
        where (soil_indicators::jsonb) ? %s
        """,
        (field, field),
    )
    present, marked = cur.fetchone()
    return present, marked


def preview(cur, sources: dict[str, str]) -> None:
    total, marked_total = count_parcels(cur)
    print(f"地块总数 {total}，已带来源标记 {marked_total}")
    print("\n来源台账依据：")
    for source, basis in MANIFEST_BASIS:
        print(f"  - {source}: {basis}")
    print(f"\n{'字段':<28}{'来源':<22}{'有值地块':>10}{'已标注':>10}")
    for field, source in sources.items():
        present, marked = count_field(cur, field)
        print(f"{field:<28}{source:<22}{present:>10}{marked:>10}")


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
            """,
            (field, field),
        )
        affected[field] = cur.rowcount
    return affected


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按来源台账标注字段来源（默认只读）")
    parser.add_argument("--apply", action="store_true", help="写入来源标记")
    parser.add_argument("--revert", action="store_true", help="移除本脚本写入的来源标记")
    parser.add_argument("--field", action="append", default=None, help="只处理指定字段，可重复")
    parser.add_argument("--json-out", default=None, help="把台账与写入结果写入 JSON 文件")
    args = parser.parse_args(argv)

    if args.apply and args.revert:
        parser.error("--apply 与 --revert 不能同时使用")

    sources = manifest_for(args.field)
    if not sources:
        parser.error("指定字段不在来源台账中")

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    conn = db_connection()
    try:
        cur = conn.cursor()
        preview(cur, sources)

        result: dict[str, object] = {
            "manifest_basis": [{"source": s, "basis": b} for s, b in MANIFEST_BASIS],
            "planned": sources,
        }

        if args.revert:
            affected = revert_marks(cur, list(sources))
            conn.commit()
            result["reverted"] = affected
            for field, count in affected.items():
                logger.info("已移除来源标记 %s：%d 行", field, count)
        elif args.apply:
            affected = apply_marks(cur, sources)
            conn.commit()
            result["applied"] = affected
            for field, count in affected.items():
                logger.info("已标注 %s = %s：%d 行", field, sources[field], count)
        else:
            print("\n默认只读，未写入数据库。确认无误后使用 --apply 写入。")
            result["applied"] = None

        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"结果 -> {args.json_out}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
