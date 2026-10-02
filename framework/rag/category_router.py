"""耕地领域查询分类路由：关键词规则 + 全库回退（无 LLM）。"""
from __future__ import annotations

from typing import Optional

from framework.agents.routing import (
    QUESTION_TYPE_1_KEYWORDS,
    QUESTION_TYPE_2_KEYWORDS,
    QUESTION_TYPE_3_KEYWORDS,
    QUESTION_TYPE_4_KEYWORDS,
    QUESTION_TYPE_5_KEYWORDS,
    QUESTION_TYPE_6_KEYWORDS,
)

_DIRECT_DOMAIN_KEYWORDS = (
    ("heavy_metal", (
        "重金属", "镉污染", "铅污染", "砷污染", "汞污染", "铬污染",
        "污染来源解析", "污染源解析", "空间风险评估",
    )),
    ("food_security", (
        "粮食安全", "粮食产量", "粮食产能", "产能预测", "产量预测",
        "未来情景", "情景预测",
    )),
    ("cultivated_land_quality", (
        "耕地质量综合", "耕地质量全链条", "地力提升决策",
    )),
)

# question_type → 领域 collection 的 category slug（与 capabilities.domain 对齐）
_TYPE_TO_CATEGORY = {
    1: "stability",
    2: "grade",
    3: "problem",
    4: "acidification",
    5: "organic_matter",
    6: "fertility",
}

# 判定优先级：更"领域专属"的关键词组先判，避免泛化词抢占
_TYPE_ORDER = (4, 5, 3, 2, 1, 6)

_KEYWORDS_BY_TYPE = {
    1: QUESTION_TYPE_1_KEYWORDS,
    2: QUESTION_TYPE_2_KEYWORDS,
    3: QUESTION_TYPE_3_KEYWORDS,
    4: QUESTION_TYPE_4_KEYWORDS,
    5: QUESTION_TYPE_5_KEYWORDS,
    6: QUESTION_TYPE_6_KEYWORDS,
}


def route_category(query: Optional[str]) -> Optional[str]:
    """判断查询目标 category；无法判断返回 None（由调用方全库回退）。"""
    if not query:
        return None
    for category, keywords in _DIRECT_DOMAIN_KEYWORDS:
        if any(keyword in query for keyword in keywords):
            return category
    for qtype in _TYPE_ORDER:
        keywords = _KEYWORDS_BY_TYPE.get(qtype) or []
        if keywords and any(kw in query for kw in keywords):
            return _TYPE_TO_CATEGORY[qtype]
    return None
