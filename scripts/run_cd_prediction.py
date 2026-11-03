"""Cd 双模型批量预测入口（默认 dry-run）。

两种输入通道（二选一）：

- ``--rows-file``：完整特征行 JSON（数组，每行含 ``parcel_id`` / ``sample_id`` + 全部特征）。
  这是阶段 1 的主通道——当前库输入覆盖率为 0（docs/cd-input-coverage-report.md）。
- ``--parcel-ids`` / ``--all``：走当前库 ``parcel_info.soil_indicators`` 映射；
  只有能凑齐全部特征的地块才会执行，否则整批拒绝并列出缺口。

默认 dry-run（只打印预检与预测值），``--apply`` 才写库（地块级覆盖）。

用法::

    python scripts/run_cd_prediction.py --model crop_cd --rows-file D:/temp/cd_rows.json
    python scripts/run_cd_prediction.py --model crop_cd --rows-file D:/temp/cd_rows.json --apply
    python scripts/run_cd_prediction.py --model effective_cd --parcel-ids P0001,P0002
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for _p in (str(PROJECT_ROOT), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 项目惯例：入口脚本先加载 .env（否则 Config 使用默认旧库参数）
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:  # pragma: no cover - dotenv 缺失时依赖外部环境变量
    pass

from framework.api.app import create_app  # noqa: E402
from framework.domain.other_models.heavy_metal_cd_db import (  # noqa: E402
    CdDatabaseError,
    read_results,
    run,
)
import framework.models  # noqa: E402,F401  触发模型注册

MODELS = ("crop_cd", "effective_cd")


def _load_rows(path: str) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "rows" in payload:
        payload = payload["rows"]
    if not isinstance(payload, list) or not payload:
        raise SystemExit("rows-file 必须是 JSON 数组（或含 rows 键的对象），且非空")
    return payload


def _all_parcel_ids(limit: int | None) -> list[str]:
    from framework.models import ParcelInfo

    query = ParcelInfo.query.order_by(ParcelInfo.parcel_id)
    if limit:
        query = query.limit(limit)
    return [row.parcel_id for row in query.all()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Cd 双模型批量预测（默认 dry-run）")
    parser.add_argument("--model", required=True, choices=MODELS)
    parser.add_argument("--rows-file", help="完整特征行 JSON 文件（主通道）")
    parser.add_argument("--parcel-ids", help="逗号分隔的地块编号（走当前库映射）")
    parser.add_argument("--all", action="store_true", help="当前库全部地块（走映射，建议配合 --limit）")
    parser.add_argument("--limit", type=int, default=None, help="--all 时限制地块数量")
    parser.add_argument("--apply", action="store_true", help="写库（地块级覆盖）；默认只预览")
    parser.add_argument("--summary-limit", type=int, default=10, help="打印结果条数上限")
    args = parser.parse_args()

    sources = [bool(args.rows_file), bool(args.parcel_ids), bool(args.all)]
    if sum(sources) != 1:
        parser.error("必须且只能指定 --rows-file / --parcel-ids / --all 之一")

    app = create_app()
    with app.app_context():
        try:
            if args.rows_file:
                report = run(args.model, rows=_load_rows(args.rows_file), apply=args.apply)
            else:
                ids = (
                    [s.strip() for s in args.parcel_ids.split(",") if s.strip()]
                    if args.parcel_ids
                    else _all_parcel_ids(args.limit)
                )
                report = run(args.model, parcel_ids=ids, apply=args.apply)
        except CdDatabaseError as exc:
            print(f"[错误] {exc}", file=sys.stderr)
            return 1

        print(f"模型: {report['model_id']}  dry-run: {not report['applied']}")
        print(f"状态: {report['status']}  请求: {report['requested']}  入库: {report['stored']}  降级: {report.get('degraded', 0)}")
        if report["status"] != "ok":
            print(f"原因: {report.get('reason')}")
            for item in report.get("rejected", [])[: args.summary_limit]:
                print(f"  拒绝 {item['parcel_id']}/{item['sample_id']}: "
                      f"{item['status']} 缺失 {item['missing_fields']}")
            print("整批未写库（预检失败不产生部分写入）")
            return 0

        for item in report.get("results", [])[: args.summary_limit]:
            print(f"  {item['parcel_id']}/{item['sample_id']}: value={item['value']:.6f} "
                  f"ln={[v for k, v in item.items() if k.startswith('ln_')][0]:.6f} ({item['status']})")
        if report["applied"]:
            rows = read_results(args.model, [r["parcel_id"] for r in report["results"]])
            print(f"回读校验: {len(rows)} 行，示例 {rows[0] if rows else '无'}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
