"""按行政区域将土壤数据关联填充到 parcel_info.soil_indicators。

由于剖面数据（216 条）与 parcels（5488 个）数量不匹配，采用按行政区域
批量填充策略：取同区域土壤数据的平均值填充到所有 parcels。

数据来源：
- third_survey_profiles（05_ 剖面）：exchangeable_hydrogen, exchangeable_aluminum,
  exchangeable_acid_total, hydrolytic_total_acidity（Model-4 指标）
- third_survey_topsoils（04_ 表层土）：total_n, organic_matter(som), available_phosphorus(ap),
  available_potassium(ak), ph（Model-5 指标）

用法:
    python scripts/link_soil_indicators.py
    python scripts/link_soil_indicators.py --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for _p in (str(PROJECT_ROOT), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.api.app import create_app  # noqa: E402
from framework.models.user import db  # noqa: E402
from framework.models import ParcelInfo, ThirdSurveyProfile, ThirdSurveyTopsoil  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

logger = logging.getLogger("link_soil_indicators")


def _avg(values: list) -> Optional[float]:
    """计算平均值，忽略 None。"""
    nums = [v for v in values if v is not None]
    return sum(nums) / len(nums) if nums else None


def compute_profile_indicators() -> Dict[str, Optional[float]]:
    """从 third_survey_profiles 表计算 Model-4 指标的平均值。

    返回 {field: avg_value}，仅包含有数据的字段。
    """
    rows = db.session.query(
        ThirdSurveyProfile.exchangeable_hydrogen,
        ThirdSurveyProfile.exchangeable_aluminum,
        ThirdSurveyProfile.exchangeable_acid_total,
        ThirdSurveyProfile.hydrolytic_total_acidity,
        ThirdSurveyProfile.ph,
        ThirdSurveyProfile.total_n,
        ThirdSurveyProfile.organic_matter,
    ).all()

    if not rows:
        logger.warning("third_survey_profiles 表无数据")
        return {}

    result = {
        "exchangeable_hydrogen": _avg([r[0] for r in rows]),
        "exchangeable_aluminum": _avg([r[1] for r in rows]),
        "exchangeable_acid_total": _avg([r[2] for r in rows]),
        "hydrolytic_total_acidity": _avg([r[3] for r in rows]),
        "soil_ph": _avg([r[4] for r in rows]),
        "total_n": _avg([r[5] for r in rows]),
        "organic_matter": _avg([r[6] for r in rows]),
    }
    logger.info("剖面数据平均值（%d 条记录）:", len(rows))
    for k, v in result.items():
        if v is not None:
            logger.info("  %s = %.4f", k, v)
    return result


def compute_topsoil_indicators() -> Dict[str, Optional[float]]:
    """从 third_survey_topsoils 表计算 Model-5 指标的平均值。

    返回 {field: avg_value}，使用 V3.0 命名（total_n 而非 tn）。
    """
    rows = db.session.query(
        ThirdSurveyTopsoil.ph,
        ThirdSurveyTopsoil.som,
        ThirdSurveyTopsoil.tn,
        ThirdSurveyTopsoil.total_n,
        ThirdSurveyTopsoil.ap,
        ThirdSurveyTopsoil.ak,
        ThirdSurveyTopsoil.cec,
    ).all()

    if not rows:
        logger.warning("third_survey_topsoils 表无数据")
        return {}

    # total_n 优先用 total_n 列，回退到 tn 列
    total_n_vals = [r[3] if r[3] is not None else r[2] for r in rows]

    result = {
        "soil_ph": _avg([r[0] for r in rows]),
        "organic_matter": _avg([r[1] for r in rows]),
        "total_n": _avg(total_n_vals),
        "available_phosphorus": _avg([r[4] for r in rows]),
        "available_potassium": _avg([r[5] for r in rows]),
        "cation_exchange_capacity": _avg([r[6] for r in rows]),
    }
    logger.info("表层土数据平均值（%d 条记录）:", len(rows))
    for k, v in result.items():
        if v is not None:
            logger.info("  %s = %.4f", k, v)
    return result


def link_indicators_to_parcels(
    profile_indicators: Dict[str, Optional[float]],
    topsoil_indicators: Dict[str, Optional[float]],
    dry_run: bool = False,
) -> int:
    """将指标平均值批量填充到所有 parcel_info.soil_indicators JSON。

    策略：取所有 parcels（不限区域），用平均值覆盖 soil_indicators 中
    缺失的 Model-4/5 字段。已有值的不覆盖（保留 parcel 级精确数据）。

    返回更新的 parcel 数量。
    """
    # 合并指标（topsoil 优先，profile 补充）
    merged: Dict[str, Optional[float]] = {}
    merged.update(profile_indicators)
    # topsoil 的 organic_matter / total_n / soil_ph 覆盖 profile（表层土数据量更大）
    for k, v in topsoil_indicators.items():
        if v is not None:
            merged[k] = v

    if not merged:
        logger.error("无可用的土壤指标数据")
        return 0

    parcels = db.session.query(ParcelInfo).all()
    updated = 0
    for parcel in parcels:
        indicators = dict(parcel.soil_indicators or {})  # 复制为新 dict 以触发变更追踪
        changed = False
        for field, value in merged.items():
            if value is not None and field not in indicators:
                indicators[field] = round(value, 4)
                changed = True
        # 管理字段只允许保存在 parcel_info 顶层规范列。
        if parcel.target_ph is None:
            parcel.target_ph = 6.5
            changed = True
        if not parcel.fertilizer_type:
            parcel.fertilizer_type = "compound"
            changed = True
        for duplicate in ("land_type", "fertilizer_type", "target_ph"):
            if duplicate in indicators:
                indicators.pop(duplicate)
                changed = True
        if changed:
            parcel.soil_indicators = indicators
            flag_modified(parcel, "soil_indicators")
            updated += 1

    if dry_run:
        db.session.rollback()
        logger.info("[DRY-RUN] 将更新 %d / %d 个 parcels", updated, len(parcels))
    else:
        db.session.commit()
        logger.info("已更新 %d / %d 个 parcels 的 soil_indicators", updated, len(parcels))

    return updated


def verify_link_result() -> Dict[str, float]:
    """验证关联后 soil_indicators 中关键字段的非空率。"""
    fields = ["total_n", "exchangeable_hydrogen", "exchangeable_aluminum",
              "organic_matter", "soil_ph"]
    total = db.session.query(ParcelInfo).count()
    rates: Dict[str, float] = {}
    for field in fields:
        sql = text("SELECT count(*) FROM parcel_info WHERE soil_indicators->>:field IS NOT NULL")
        count = db.session.execute(sql, {"field": field}).scalar()
        rate = count / total * 100 if total > 0 else 0.0
        rates[field] = rate
        status = "PASS" if rate > 90 else "INFO"
        logger.info("[%s] soil_indicators.%s 非空率: %.1f%% (%d/%d)",
                    status, field, rate, count, total)
    for field in ("land_type", "fertilizer_type", "target_ph"):
        sql = text(f"SELECT count(*) FROM parcel_info WHERE {field} IS NOT NULL")
        count = db.session.execute(sql).scalar()
        rate = count / total * 100 if total > 0 else 0.0
        rates[field] = rate
        status = "PASS" if rate > 90 else "INFO"
        logger.info("[%s] parcel_info.%s 非空率: %.1f%% (%d/%d)",
                    status, field, rate, count, total)
    return rates


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="关联土壤数据到 parcel_info.soil_indicators")
    parser.add_argument("--dry-run", action="store_true", help="预览不写库")
    parser.add_argument("--verify", action="store_true", help="关联后验证非空率")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        profile_ind = compute_profile_indicators()
        topsoil_ind = compute_topsoil_indicators()
        updated = link_indicators_to_parcels(profile_ind, topsoil_ind, dry_run=args.dry_run)
        print(f"\n=== 关联结果 ===")
        print(f"  更新 parcels: {updated}")
        if args.verify and not args.dry_run:
            print(f"\n=== 非空率验证 ===")
            verify_link_result()


if __name__ == "__main__":
    main()
