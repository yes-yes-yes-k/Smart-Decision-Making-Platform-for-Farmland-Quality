from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional


DOMAIN_TAXONOMY: Dict[str, Dict] = {
    "heavy_metal": {
        "name": "土壤重金属污染",
        "keywords": (
            "重金属", "镉污染", "铅污染", "砷污染", "汞污染", "铬污染",
            "污染来源", "污染源解析", "风险管控", "土壤污染",
        ),
        "topics": {
            "heavy_metal.cadmium": ("镉", "cd"),
            "heavy_metal.lead": ("铅", "pb"),
            "heavy_metal.arsenic": ("砷", "as"),
            "heavy_metal.mercury": ("汞", "hg"),
            "heavy_metal.chromium": ("铬", "cr"),
            "heavy_metal.risk_assessment": ("风险评价", "风险评估", "风险筛选"),
            "heavy_metal.source_apportionment": ("来源解析", "源解析", "污染来源"),
            "heavy_metal.remediation": ("污染修复", "修复技术", "安全利用"),
            "heavy_metal.crop_safety": ("农产品安全", "作物安全", "超标农产品"),
        },
    },
    "food_security": {
        "name": "粮食安全与产能",
        "keywords": (
            "粮食安全", "粮食产量", "粮食产能", "粮食生产", "产能提升",
            "产量预测", "种植结构", "气候风险", "稳产保供",
        ),
        "topics": {
            "food_security.production_capacity": ("粮食产能", "生产能力", "产能提升"),
            "food_security.yield_prediction": ("产量预测", "单产预测", "产能预测"),
            "food_security.land_protection": ("耕地保护", "占补平衡", "永久基本农田"),
            "food_security.climate_risk": ("气候风险", "气象灾害", "极端气候"),
            "food_security.cropping_structure": ("种植结构", "种植制度", "作物布局"),
            "food_security.scenario_simulation": ("情景模拟", "情景预测", "未来情景"),
            "food_security.high_standard_farmland": ("高标准农田", "高标准农田建设"),
        },
    },
    "cultivated_land_quality": {
        "name": "耕地质量评价与提升",
        "keywords": (
            "耕地质量", "耕地地力", "质量等级", "地力等级", "土壤质量",
            "障碍因素", "高标准农田", "质量提升", "地力提升",
        ),
        "topics": {
            "cultivated_land_quality.policy_standard": (
                "政策", "标准", "技术规范", "技术规程", "工作方案", "通知",
            ),
            "cultivated_land_quality.grade_evaluation": (
                "等级评价", "质量评价", "地力评价", "分等定级",
            ),
            "cultivated_land_quality.indicator_system": (
                "指标体系", "评价指标", "指标权重",
            ),
            "cultivated_land_quality.obstacle_diagnosis": (
                "障碍因素", "障碍因子", "障碍诊断", "限制因素",
            ),
            "cultivated_land_quality.soil_health": (
                "土壤健康", "耕地健康", "土壤质量",
            ),
            "cultivated_land_quality.high_standard_farmland": (
                "高标准农田", "土地整治",
            ),
            "cultivated_land_quality.quality_improvement": (
                "质量提升", "地力提升", "定向培育", "改良措施",
            ),
            "cultivated_land_quality.remote_sensing": (
                "遥感监测", "多源遥感", "遥感数据", "webgis", "gis",
            ),
        },
    },
}

DOMAIN_CODES = tuple(DOMAIN_TAXONOMY)
TOPIC_TO_DOMAIN = {
    topic: domain
    for domain, definition in DOMAIN_TAXONOMY.items()
    for topic in definition["topics"]
}
ALL_LABEL_CODES = frozenset((*DOMAIN_CODES, *TOPIC_TO_DOMAIN))

_CULTIVATED_LEGACY_CATEGORIES = frozenset({
    "stability", "grade", "problem", "acidification", "organic_matter",
    "fertility", "cultivated_land_quality",
})


def label_level(label_code: str) -> str:
    return "domain" if label_code in DOMAIN_CODES else "topic"


def parent_domain(label_code: str) -> Optional[str]:
    if label_code in DOMAIN_CODES:
        return None
    return TOPIC_TO_DOMAIN.get(label_code)


def normalize_label_codes(labels: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    for value in labels:
        code = str(value).strip().lower()
        if code and code not in normalized:
            normalized.append(code)
    invalid = [code for code in normalized if code not in ALL_LABEL_CODES]
    if invalid:
        raise ValueError(f"不支持的知识标签: {', '.join(invalid)}")
    return normalized


def primary_domain_for_category(category: Optional[str]) -> Optional[str]:
    code = (category or "").strip().lower()
    if code in DOMAIN_CODES:
        return code
    if code in _CULTIVATED_LEGACY_CATEGORIES:
        return "cultivated_land_quality"
    return None


def expand_with_parent_domains(labels: Iterable[str]) -> List[str]:
    expanded = normalize_label_codes(labels)
    for code in list(expanded):
        parent = parent_domain(code)
        if parent and parent not in expanded:
            expanded.append(parent)
    return expanded


def classify_label_candidates(text: str, *, exclude: Iterable[str] = ()) -> List[Dict]:
    """Return deterministic candidates for human review.

    Automatic candidates are never considered approved by this function.  A
    single keyword is enough to create a review item; additional distinct
    keyword hits raise confidence without silently granting access/routing.
    """
    haystack = (text or "").lower()
    excluded = set(exclude)
    candidates: Dict[str, Dict] = {}

    def term_matches(term: str) -> bool:
        lowered = term.lower()
        if lowered.isascii() and lowered.replace("-", "").isalnum():
            return re.search(
                rf"(?<![a-z0-9]){re.escape(lowered)}(?![a-z0-9])",
                haystack,
            ) is not None
        return lowered in haystack

    def add_candidate(code: str, keywords: Iterable[str]) -> None:
        if code in excluded:
            return
        matched = sorted({term for term in keywords if term_matches(term)})
        if not matched:
            return
        confidence = min(0.95, 0.55 + 0.08 * (len(matched) - 1))
        candidates[code] = {
            "label_code": code,
            "label_level": label_level(code),
            "parent_code": parent_domain(code),
            "confidence": round(confidence, 4),
            "evidence": matched[:8],
        }

    for domain, definition in DOMAIN_TAXONOMY.items():
        add_candidate(domain, definition["keywords"])
        for topic, keywords in definition["topics"].items():
            add_candidate(topic, keywords)

    return sorted(
        candidates.values(),
        key=lambda item: (-item["confidence"], item["label_code"]),
    )


def domain_metadata(approved_labels: Iterable[str]) -> Dict[str, bool]:
    approved = set(approved_labels)
    return {f"domain_{code}": code in approved for code in DOMAIN_CODES}
