"""把原系统（soilgd）整套 Cd 数据集移植进本项目（阶段 D1）。

用法::

    # dry-run（默认）：只统计源表规模、预检可导入行数、打印前 5 行预测
    python scripts/import_ported_cd_dataset.py --model crop_cd --limit 200

    # 正式导入（写 parcel_info + 归属表 + 结果表）
    python scripts/import_ported_cd_dataset.py --model all --apply

    # 只重算乡镇归属
    python scripts/import_ported_cd_dataset.py --assign-townships

    # 回归比对（导入后验收）
    python scripts/import_ported_cd_dataset.py --compare --model all

    # 回滚（只删 SGD_ 前缀数据，不动自有数据）
    python scripts/import_ported_cd_dataset.py --rollback

命名空间：``SGD_<Farmland_ID>`` / ``SGD_<id>_<Sample_ID>``，与自有纯数字 parcel_id 隔离。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for _p in (str(PROJECT_ROOT), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

from framework.api.app import create_app  # noqa: E402
from framework.domain.other_models import heavy_metal_cd_ported as ported  # noqa: E402
from framework.domain.other_models.heavy_metal_cd_db import run  # noqa: E402
import framework.models  # noqa: E402,F401

MODELS = ("crop_cd", "effective_cd")


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def do_import(model_id: str, limit: int | None, apply: bool) -> int:
    items = ported.fetch_feature_rows(model_id, limit=limit)
    rows = ported.rows_from_items(model_id, items)
    print(f"[{model_id}] 源表可导入行数: {len(rows)}（limit={limit}）")
    if not rows:
        print("[错误] 没有可导入的行", file=sys.stderr)
        return 1

    report = run(model_id, rows=rows, apply=False)
    if report["status"] != "ok":
        _print({k: report.get(k) for k in ("status", "reason", "requested", "rejected")})
        print("[错误] 预检未通过（源表可能存在空值特征）", file=sys.stderr)
        return 1

    preview = report["results"][:5]
    for item in preview:
        print(f"  预览 {item['parcel_id']}/{item['sample_id']}: value={item['value']:.6f} status={item['status']}")

    if not apply:
        print(f"[dry-run] 未写库。正式执行请在命令后加 --apply")
        return 0

    inserted = ported.upsert_parcel_info(rows, items)
    print(f"  parcel_info 新增 {inserted} 行（SGD_ 前缀，geom/area_code 留空）")
    townships = ported.assign_townships()
    print(f"  乡镇归属: 点面包含 {townships['inside']} 行，回退最近 {townships['fallback']} 行")

    written = run(model_id, rows=rows, apply=True)
    print(f"  结果入库: {written['stored']} 行（status={written['status']}）")

    comparison = ported.compare_with_source(model_id)
    _print({"回归比对": comparison})
    if not comparison["passed"]:
        print("[错误] 回归比对未通过，请检查列映射或资产版本", file=sys.stderr)
        return 2
    print(f"[完成] {model_id} 导入并通过回归比对")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="移植原系统 Cd 数据集")
    parser.add_argument("--model", choices=MODELS + ("all",), default="all")
    parser.add_argument("--limit", type=int, default=None, help="只取前 N 行（试点用）")
    parser.add_argument("--apply", action="store_true", help="写库；默认 dry-run")
    parser.add_argument("--assign-townships", action="store_true", help="只重算移植地块的乡镇归属")
    parser.add_argument("--compare", action="store_true", help="只做回归比对")
    parser.add_argument("--rollback", action="store_true", help="删除全部 SGD_ 移植数据")
    args = parser.parse_args()

    models = MODELS if args.model == "all" else (args.model,)
    app = create_app()
    with app.app_context():
        if args.rollback:
            _print({"回滚": ported.rollback()})
            return 0
        if args.assign_townships:
            _print({"乡镇归属": ported.assign_townships()})
            return 0
        if args.compare:
            exit_code = 0
            for model_id in models:
                result = ported.compare_with_source(model_id)
                _print({"回归比对": result})
                if not result["passed"]:
                    exit_code = 2
            return exit_code

        if not args.apply:
            for model_id in models:
                _print({"源表规模": ported.source_summary(model_id)})

        exit_code = 0
        for model_id in models:
            code = do_import(model_id, args.limit, args.apply)
            exit_code = max(exit_code, code)
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
