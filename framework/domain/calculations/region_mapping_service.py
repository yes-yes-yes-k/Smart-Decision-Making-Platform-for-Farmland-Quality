"""区域代码 → 农业区映射服务层。

取代原硬编码 AREA_TO_REGION 字典的直接查询，提供带 DB 缓存和回退的统一入口。
优先级：DB 缓存（area_code_region_map 表） → 硬编码 AREA_TO_REGION → 默认降级值。

设计参照 framework/agents/exclusive_rules.py 的 from_database / _get_active_rules 模式：
- 模块级缓存避免每次路由判定查询 DB
- DB 异常时回退硬编码
- refresh_region_cache() 供运维调用使 DB 修改生效
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from .coefficients import (
    AREA_TO_REGION,
    MODEL2_COEFFICIENTS,
    MODEL3_COEFFICIENTS,
    MODEL3_WEIGHTS,
)

logger = logging.getLogger(__name__)

# 默认降级值（未知 area_code 或 DB/硬编码均无记录时使用）
DEFAULT_REGION_MAPPING: Dict[str, object] = {
    "primary": "HN",
    "secondary": "MNY",
    "ejnyq_idx": 0,
}

# 模块级缓存：area_code → {primary, secondary, ejnyq_idx}
# None 表示未加载，{} 表示已加载但 DB 不可用或表为空，非空 dict 表示缓存命中
_cache: Optional[Dict[str, dict]] = None


def _load_cache() -> Dict[str, dict]:
    """从 area_code_region_map 表加载 enabled=True 的映射到内存缓存。

    DB 异常时返回空 dict（由 get_region_mapping 回退到硬编码 AREA_TO_REGION）。
    """
    global _cache
    if _cache is not None:
        return _cache
    try:
        from framework.models import db, AreaCodeRegionMap
        rows = db.session.query(AreaCodeRegionMap).filter_by(enabled=True).all()
        _cache = {
            r.area_code: {
                "primary": r.primary,
                "secondary": r.secondary,
                "ejnyq_idx": r.ejnyq_idx,
            }
            for r in rows
        }
    except Exception as e:
        logger.warning(
            "area_code_region_map 表加载失败，回退硬编码 AREA_TO_REGION。reason=db_unavailable_fallback_to_hardcoded error=%s",
            e,
        )
        _cache = {}
    return _cache


def get_region_mapping(area_code: str) -> Dict[str, object]:
    """查询 area_code 对应的农业区映射。

    查询优先级：
    1. DB 缓存（area_code_region_map 表）
    2. 硬编码 AREA_TO_REGION 字典（DB 不可用或无记录时回退）
    3. 默认降级值 DEFAULT_REGION_MAPPING

    返回 dict 包含键：primary (str), secondary (str), ejnyq_idx (int)。
    """
    # 1. DB 缓存
    cache = _load_cache()
    mapping = cache.get(area_code)
    if mapping:
        return mapping

    # 2. 硬编码回退
    mapping = AREA_TO_REGION.get(area_code)
    if mapping:
        return mapping

    # 3. 默认降级
    logger.warning(
        "area_code=%s 不在映射表中，使用默认值。reason=unknown_area_code",
        area_code,
    )
    return dict(DEFAULT_REGION_MAPPING)


def refresh_region_cache() -> None:
    """清空缓存，下次 get_region_mapping() 调用重新从 DB 加载。

    场景：运维通过 DB 修改 area_code_region_map 表后，调用此函数使新映射生效。
    """
    global _cache
    _cache = None


def validate_region_mappings() -> Tuple[bool, List[str]]:
    """验证所有映射的 ejnyq_idx / primary / secondary 在系数配置中都有对应配置。

    检查项：
    - 每个映射的 ejnyq_idx 在 MODEL2_COEFFICIENTS 中存在
    - 每个映射的 secondary 在 MODEL3_WEIGHTS 中存在
    - 每个映射的 primary 在 MODEL3_COEFFICIENTS 中存在

    返回 (is_valid, issues)：is_valid=True 表示全部通过，issues 为不一致条目列表。
    """
    issues: List[str] = []
    # 合并 DB 缓存和硬编码字典中的所有映射
    all_mappings: Dict[str, dict] = {}
    all_mappings.update(AREA_TO_REGION)
    cache = _load_cache()
    all_mappings.update(cache)

    for area_code, mapping in all_mappings.items():
        ejnyq_idx = mapping.get("ejnyq_idx")
        primary = mapping.get("primary")
        secondary = mapping.get("secondary")

        if ejnyq_idx not in MODEL2_COEFFICIENTS:
            issues.append(
                f"area_code={area_code}: ejnyq_idx={ejnyq_idx} 在 MODEL2_COEFFICIENTS 中不存在"
            )
        if secondary not in MODEL3_WEIGHTS:
            issues.append(
                f"area_code={area_code}: secondary={secondary} 在 MODEL3_WEIGHTS 中不存在"
            )
        if primary not in MODEL3_COEFFICIENTS:
            issues.append(
                f"area_code={area_code}: primary={primary} 在 MODEL3_COEFFICIENTS 中不存在"
            )

    return (len(issues) == 0, issues)
