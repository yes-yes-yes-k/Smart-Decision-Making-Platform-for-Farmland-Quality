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
    for qtype in _TYPE_ORDER:
        keywords = _KEYWORDS_BY_TYPE.get(qtype) or []
        if keywords and any(kw in query for kw in keywords):
            return _TYPE_TO_CATEGORY[qtype]
    return None