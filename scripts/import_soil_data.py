"""从真实数据源导入土壤数据（填充 Model-4/5 新增字段）。

从 F:\\BaiduNetdiskDownload\\耕地质量大模型 目录导入：
- 04_ 表层土数据 → third_survey_topsoils 表（含 pH/CEC/SOM/TN/AP/AK 等）
- 05_ 剖面理化数据 → third_survey_profiles 表（含交换性氢离子/交换性铝离子/全氮等 Model-4 字段）

复用 import_lechang_data.py 的 _read_excel / _prepare_dataframe / import_one_source。
扩展 COLUMN_MAPS 已包含 exchangeable_hydrogen / exchangeable_aluminum /
hydrolytic_total_acidity / total_n 等新字段映射。

用法:
    python scripts/import_soil_data.py
    python scripts/import_soil_data.py --dry-run
    python scripts/import_soil_data.py --source-dir "F:\\BaiduNetdiskDownload\\耕地质量大模型"
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

# 确保 PROJECT_ROOT 与 src 在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for _p in (str(PROJECT_ROOT), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
from framework.models.soil_data import (  # noqa: E402
    ThirdSurveyTopsoil,
    ThirdSurveyProfile,
)
# 复用 import_lechang_data 的函数和扩展后的 COLUMN_MAPS
from scripts.import_lechang_data import (  # noqa: E402
    _read_excel,
    _prepare_dataframe,
    import_one_source,
    COLUMN_MAPS,
)

logger = logging.getLogger("import_soil_data")

# 真实数据源路径（子目录 → 文件相对路径）
DEFAULT_SOURCE_DIR = r"F:\BaiduNetdiskDownload\耕地质量大模型"

# 数据源配置：source_name -> (模型类, 子目录, 文件名)
REAL_DATA_SOURCES = {
    "third_survey_topsoil": (
        ThirdSurveyTopsoil,
        "04_乐昌市土壤三普表层土点数据2022",
        "01_乐昌市土壤三普表层土点位数据_fake.xlsx",
    ),
    "third_survey_profile": (
        ThirdSurveyProfile,
        "05_乐昌市土壤三普剖面理化和基本数据2022",
        "乐昌市土壤三普剖面理化和基本数据_fake.xlsx",
    ),
}


def run_import(
    source_dir: str = DEFAULT_SOURCE_DIR,
    dry_run: bool = False,
) -> Dict[str, int]:
    """从真实数据源导入 04_ 表层土和 05_ 剖面数据。

    返回 {source_name: rows}。
    """
    results: Dict[str, int] = {}
    for source_name, (model_class, subdir, filename) in REAL_DATA_SOURCES.items():
        filepath = Path(source_dir) / subdir / filename
        if not filepath.exists():
            logger.error("数据文件不存在: %s", filepath)
            results[source_name] = 0
            continue

        column_map = COLUMN_MAPS[source_name]
        try:
            count = import_one_source(
                model_class, column_map, [str(filepath)], dry_run=dry_run
            )
            results[source_name] = count
        except Exception as e:  # noqa: BLE001
            logger.exception("导入 %s 失败: %s", source_name, e)
            results[source_name] = 0

    return results


def verify_nonnull_rates() -> Dict[str, Dict[str, float]]:
    """验证导入后关键字段的非空率。"""
    checks = {
        "third_survey_profiles": ["exchangeable_hydrogen", "exchangeable_aluminum", "total_n"],
        "third_survey_topsoils": ["total_n", "ph", "som"],
    }
    model_map = {
        "third_survey_profiles": ThirdSurveyProfile,
        "third_survey_topsoils": ThirdSurveyTopsoil,
    }
    rates: Dict[str, Dict[str, float]] = {}
    for table, fields in checks.items():
        model = model_map[table]
        total = db.session.query(model).count()
        rates[table] = {}
        for field in fields:
            col = getattr(model, field)
            nonnull = db.session.query(model).filter(col.isnot(None)).count()
            rate = nonnull / total * 100 if total > 0 else 0.0
            rates[table][field] = rate
            status = "PASS" if rate > 90 else "FAIL"
            logger.info("[%s] %s.%s 非空率: %.1f%% (%d/%d)",
                        status, table, field, rate, nonnull, total)
    return rates


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="从真实数据源导入土壤数据（Model-4/5 字段）")
    parser.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR,
                        help=f"数据源根目录（默认 {DEFAULT_SOURCE_DIR}）")
    parser.add_argument("--dry-run", action="store_true", help="预览不写库")
    parser.add_argument("--verify", action="store_true", help="导入后验证非空率")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        results = run_import(source_dir=args.source_dir, dry_run=args.dry_run)
        print("\n=== 导入结果 ===")
        for name, count in results.items():
            print(f"  {name}: {count} 行")
        if args.verify and not args.dry_run:
            print("\n=== 非空率验证 ===")
            verify_nonnull_rates()


if __name__ == "__main__":
    main()
