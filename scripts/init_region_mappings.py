"""区域代码 → 农业区映射初始化脚本。

向 area_code_region_map 表插入初始映射记录。幂等：已存在的 area_code 跳过。

用法:
    python scripts/init_region_mappings.py
    python scripts/init_region_mappings.py --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 确保 PROJECT_ROOT 与 src 在 sys.path（与 import_lechang_data.py 同模式）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for _p in (str(PROJECT_ROOT), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
from framework.models import AreaCodeRegionMap  # noqa: E402

logger = logging.getLogger("init_region_mappings")

# 初始映射数据：area_code → {region_name, primary, secondary, ejnyq_idx}
# 与模型 2 原始 CSV 的 XQMCcode/EJNYQcode 对照一致。
INITIAL_REGION_MAPPINGS = [
    {"area_code": "440203", "region_name": "武江区", "primary": "HN", "secondary": "MNY", "ejnyq_idx": 0},
    {"area_code": "440204", "region_name": "浈江区", "primary": "HN", "secondary": "NL", "ejnyq_idx": 3},
    {"area_code": "440205", "region_name": "曲江区", "primary": "HN", "secondary": "NL", "ejnyq_idx": 3},
    {"area_code": "440222", "region_name": "始兴县", "primary": "HN", "secondary": "NL", "ejnyq_idx": 3},
    {"area_code": "440224", "region_name": "仁化县", "primary": "HN", "secondary": "NL", "ejnyq_idx": 3},
    {"area_code": "440229", "region_name": "翁源县", "primary": "HN", "secondary": "NL", "ejnyq_idx": 3},
    {"area_code": "440232", "region_name": "乳源瑶族自治县", "primary": "HN", "secondary": "NL", "ejnyq_idx": 3},
    {"area_code": "440233", "region_name": "新丰县", "primary": "HN", "secondary": "NL", "ejnyq_idx": 3},
    {"area_code": "440281", "region_name": "乐昌市", "primary": "HN", "secondary": "NL", "ejnyq_idx": 3},
    {"area_code": "440282", "region_name": "南雄市", "primary": "HN", "secondary": "NL", "ejnyq_idx": 3},
]


def init_region_mappings(dry_run: bool = False) -> None:
    """插入初始映射记录。已存在的 area_code 跳过（幂等）。"""
    app = create_app()
    with app.app_context():
        inserted = 0
        skipped = 0
        for item in INITIAL_REGION_MAPPINGS:
            existing = (
                db.session.query(AreaCodeRegionMap)
                .filter_by(area_code=item["area_code"])
                .first()
            )
            if existing is not None:
                logger.info("跳过（已存在）: area_code=%s %s", item["area_code"], item["region_name"])
                skipped += 1
                continue
            record = AreaCodeRegionMap(
                area_code=item["area_code"],
                region_name=item["region_name"],
                primary=item["primary"],
                secondary=item["secondary"],
                ejnyq_idx=item["ejnyq_idx"],
                enabled=True,
            )
            db.session.add(record)
            inserted += 1
            logger.info("待插入: area_code=%s %s → primary=%s secondary=%s ejnyq_idx=%s",
                        item["area_code"], item["region_name"],
                        item["primary"], item["secondary"], item["ejnyq_idx"])

        if dry_run:
            db.session.rollback()
            print(f"[DRY-RUN] 将插入 {inserted} 条，跳过 {skipped} 条已存在记录")
        else:
            db.session.commit()
            print(f"[完成] 插入 {inserted} 条区域映射，跳过 {skipped} 条已存在记录")
            print("[提示] 调用 region_mapping_service.refresh_region_cache() 使新映射生效")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="初始化 area_code_region_map 表数据")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将插入的记录，不写库")
    args = parser.parse_args()
    init_region_mappings(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
