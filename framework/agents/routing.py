"""独立路由模块：五维路由判定逻辑。

从 nodes.py 迁移而来，保持对外函数签名向后兼容。
context 为 None 时行为与旧版 nodes.py 完全一致。
"""
from __future__ import annotations
import numpy as np
from typing import Any, List, Dict, Optional

try:
    from framework.embedding.service import embedding_service
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False

from .exclusive_rules import apply_exclusive_rules

QUESTION_TYPE_1_KEYWORDS = [
    "等级稳定", "稳定性", "稳不稳", "稳定吗", "稳定性较弱", "退化风险",
    "关注清单", "重点关注", "临界状态", "风险类型", "等级整体", "掉级",
    "稳定性评价", "等级边界安全度", "指标支撑均衡度", "关键指标临界度",
    "空间邻域一致性", "历史变化趋势", "掉级风险", "关键因子退化",
    "退化空间集聚", "持续低质风险",
]
QUESTION_TYPE_2_KEYWORDS = [
    "酸化程度", "酸化等级", "酸化现状", "酸化严重", "酸化了", "酸化治理",
    "调理剂", "碱性材料", "碱性调理剂", "木本泥炭", "石灰", "pH提升",
    "土地利用类型", "酸化",
    "酸化改良", "酸化分区", "改良方案", "土壤酸化", "酸性改良",
]
QUESTION_TYPE_3_KEYWORDS = [
    "障碍因素", "主要问题", "障碍诊断", "障碍组合", "地块诊断", "毛病",
    "障碍等级", "哪些问题", "有问题",
    "障碍识别", "障碍程度", "障碍因子", "精准识别", "单一障碍", "多障碍",
]
QUESTION_TYPE_4_KEYWORDS = [
    "肥力预测", "SOC预测", "有机碳预测", "有机碳", "SOC", "soc",
    "Dose", "dose", "施肥量预测", "预测施肥量", "预测置信度", "综合肥力",
    "肥力", "施多少肥", "氮肥",
]
QUESTION_TYPE_5_KEYWORDS = [
    "质量等级", "等级评价", "综合指数", "指标隶属度", "障碍度排序",
    "耕地质量等级", "质量评价", "等级评定", "指标权重",
]
QUESTION_TYPE_6_KEYWORDS = [
    "提升潜力", "潜力评估", "增产潜力", "潜力分布", "改良片区", "潜力多大", "潜力",
    "提升空间", "目标等级",
]
QUESTION_TYPE_7_KEYWORDS = [
    "有机质", "有机肥", "秸秆", "秸秆还田", "培肥", "培肥方案",
    "有机肥施用", "有机肥每亩", "提升有机质", "有机质含量",
]

KNOWLEDGE_QUESTION_PATTERNS_START = ["什么是", "何为", "解释"]
KNOWLEDGE_QUESTION_PATTERNS_CONTAIN = ["是什么意思", "什么意思", "定义", "概念", "含义"]

RELEVANCE_KEYWORDS = [
    "酸化", "pH", "土壤", "耕地", "治理", "改良", "氮肥", "施肥",
    "调理剂", "石灰", "碱性", "酸性", "交换性酸", "CEC", "阳离子交换量",
    "土壤质量", "农业", "农田", "养分", "种植", "作物", "水稻", "小麦",
    "玉米", "肥料", "有机质", "酸碱度", "酸性土", "碱性土", "改良剂",
    "田", "地", "质量", "等级", "稳定", "潜力", "障碍", "问题",
    "乡镇", "县", "片区", "地块", "农户", "风险", "关注", "清单",
    "诊断", "毛病", "增产", "粮食", "碳氮比", "全氮", "容重",
    "有机肥", "施用量", "秸秆", "培肥", "SOC", "Dose",
]

REFERENCE_QUESTIONS: Dict[int, List[str]] = {
    1: [
        "查询区域内耕地质量等级整体稳定吗",
        "查询区域内哪些高等级耕地存在退化风险",
        "本县哪些乡镇或地块等级稳定性较弱需要现场复核",
        "我的这块田质量等级稳不稳",
        "查询区域内哪些对象需要纳入重点关注清单",
    ],
    2: [
        "查询区域内农用地土壤酸化程度如何不同酸化等级比例分别多少",
        "我的田酸化了pH是多少我要施加多少碱性调理剂可以治理好",
        "查询区域内不同土地利用类型的酸化程度",
        "我的这块田酸化严重吗",
    ],
    3: [
        "我这块地到底有啥毛病",
        "全省耕地质量存在哪些问题",
        "县乡镇里的耕地在哪些方面有问题",
    ],
    4: [
        "我的田肥力怎么样",
        "我的田土壤有机碳含量大概多少",
        "预测这块地需要多少施肥量",
    ],
    5: [
        "我的田耕地质量等级是多少",
        "查询地块的综合指数和障碍度排序",
        "这块地的耕地质量等级评价结果",
    ],
    6: [
        "辖区耕地质量提升的总体潜力有多大可增产多少粮食",
        "我们县划定的优先改良片区具体在哪几个村每块潜力多大",
    ],
    7: [
        "全省耕地土壤有机质含量如何空间分布情况",
        "为了提升耕地土壤有机质有机肥或者秸秆每亩施用量多少",
        "本县耕地土壤有机质平均含量是多少",
    ],
}

REFERENCE_VECTORS: Dict[int, List[List[float]]] = {}

def _precompute_reference_vectors() -> None:
    if not EMBEDDING_AVAILABLE or not embedding_service.is_available():
        return
    global REFERENCE_VECTORS
    for q_type, questions in REFERENCE_QUESTIONS.items():
        vectors = embedding_service.embed_documents(questions)
        REFERENCE_VECTORS[q_type] = vectors

def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    dot_product = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot_product / (norm1 * norm2))

_precompute_reference_vectors()

def check_relevance(question: str) -> float:
    if not question:
        return 0.0
    if EMBEDDING_AVAILABLE and embedding_service.is_available():
        return _check_relevance_vector(question)
    else:
        return _check_relevance_keyword(question)

def _check_relevance_vector(question: str) -> float:
    query_vector = embedding_service.embed_query(question)
    if not query_vector:
        return _check_relevance_keyword(question)
    max_similarity = 0.0
    for q_type, vectors in REFERENCE_VECTORS.items():
        for ref_vector in vectors:
            similarity = _cosine_similarity(query_vector, ref_vector)
            if similarity > max_similarity:
                max_similarity = similarity
    return max_similarity

def _check_relevance_keyword(question: str) -> float:
    if not question:
        return 0.0
    match_count = sum(1 for keyword in RELEVANCE_KEYWORDS if keyword in question)
    return min(match_count / 3, 1.0)

def _is_knowledge_question(question: str) -> bool:
    if not question:
        return False
    if question.startswith(("什么是", "何为", "解释")):
        return True
    contains_patterns = ["是什么意思", "什么意思", "定义", "概念", "含义"]
    if any(p in question for p in contains_patterns):
        return True
    return False

def identify_question_type(question: str, context: Optional[dict] = None) -> tuple[int, float]:
    """识别问题类型（向后兼容：context 为 None 时与旧版完全一致）。

    返回 (question_type, relevance)。question_type ∈ 1..7 与 0=RAG。
    context 提供时，在既有判定之上叠加五维排他规则精化。
    """
    if _is_knowledge_question(question):
        return 0, 1.0
    base_type, base_rel = _identify_question_type_keyword(question)
    if base_type == 0:
        if EMBEDDING_AVAILABLE and embedding_service.is_available():
            base_type, base_rel = _identify_question_type_vector(question)
        # 关键词与向量均未命中时 base_type 保持 0
    if context is not None:
        refined_type, _status = apply_exclusive_rules(question, base_type, context)
        return refined_type, base_rel
    return base_type, base_rel

def _identify_question_type_vector(question: str) -> tuple[int, float]:
    keyword_relevance = _check_relevance_keyword(question)
    query_vector = embedding_service.embed_query(question)
    if not query_vector:
        return _identify_question_type_keyword(question)
    max_similarity = 0.0
    best_type = 1
    for q_type, vectors in REFERENCE_VECTORS.items():
        for ref_vector in vectors:
            similarity = _cosine_similarity(query_vector, ref_vector)
            if similarity > max_similarity:
                max_similarity = similarity
                best_type = q_type
    if max_similarity < 0.75:
        return 0, max_similarity
    if max_similarity < 0.55:
        if keyword_relevance >= 0.3:
            return 2, keyword_relevance
        return 0, max_similarity
    return best_type, max_similarity

def _identify_question_type_keyword(question: str) -> tuple[int, float]:
    relevance = _check_relevance_keyword(question)
    if any(keyword in question for keyword in QUESTION_TYPE_1_KEYWORDS):
        return 1, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_2_KEYWORDS):
        return 2, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_3_KEYWORDS):
        return 3, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_4_KEYWORDS):
        return 4, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_5_KEYWORDS):
        return 5, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_6_KEYWORDS):
        return 6, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_7_KEYWORDS):
        return 7, relevance
    else:
        return 0, relevance