"""独立路由模块：五维路由判定逻辑。

从 nodes.py 迁移而来，保持对外函数签名向后兼容。
context 为 None 时行为与旧版 nodes.py 完全一致。
"""
from __future__ import annotations
import numpy as np
from typing import List, Dict, Optional

try:
    from framework.embedding.service import embedding_service
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False

from .exclusive_rules import apply_exclusive_rules

from framework.config import Config
from framework.agents.capabilities import PROFESSIONAL_CAPABILITIES

try:
    from framework.llm.service import llm_service
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

QUESTION_TYPE_1_KEYWORDS = [
    "等级稳定", "稳定性", "稳不稳", "稳定吗", "稳定性较弱", "退化风险",
    "关注清单", "重点关注", "临界状态", "风险类型", "等级整体", "掉级",
    "稳定性评价", "等级边界安全度", "指标支撑均衡度", "关键指标临界度",
    "空间邻域一致性", "历史变化趋势", "掉级风险", "关键因子退化",
    "退化空间集聚", "持续低质风险",
]
QUESTION_TYPE_2_KEYWORDS = [
    "质量等级", "等级评价", "综合指数", "指标隶属度", "障碍度排序",
    "耕地质量等级", "质量评价", "等级评定", "指标权重",
]
QUESTION_TYPE_3_KEYWORDS = [
    "障碍因素", "主要问题", "障碍诊断", "障碍组合", "地块诊断", "毛病",
    "障碍等级", "哪些问题", "有问题",
    "障碍识别", "障碍程度", "障碍因子", "精准识别", "单一障碍", "多障碍",
]
QUESTION_TYPE_4_KEYWORDS = [
    "酸化程度", "酸化等级", "酸化现状", "酸化严重", "酸化了", "酸化治理",
    "调理剂", "碱性材料", "碱性调理剂", "木本泥炭", "石灰", "pH提升",
    "土地利用类型", "酸化",
    "酸化改良", "酸化分区", "改良方案", "土壤酸化", "酸性改良",
]
QUESTION_TYPE_5_KEYWORDS = [
    "有机质", "有机肥", "秸秆", "秸秆还田", "培肥", "培肥方案",
    "有机肥施用", "有机肥每亩", "提升有机质", "有机质含量",
]
QUESTION_TYPE_6_KEYWORDS: list[str] = []  # 占位符，无关键词

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
        "我的田耕地质量等级是多少",
        "查询地块的综合指数和障碍度排序",
        "这块地的耕地质量等级评价结果",
    ],
    3: [
        "我这块地到底有啥毛病",
        "全省耕地质量存在哪些问题",
        "县乡镇里的耕地在哪些方面有问题",
    ],
    4: [
        "查询区域内农用地土壤酸化程度如何不同酸化等级比例分别多少",
        "我的田酸化了pH是多少我要施加多少碱性调理剂可以治理好",
        "查询区域内不同土地利用类型的酸化程度",
        "我的这块田酸化严重吗",
    ],
    5: [
        "全省耕地土壤有机质含量如何空间分布情况",
        "为了提升耕地土壤有机质有机肥或者秸秆每亩施用量多少",
        "本县耕地土壤有机质平均含量是多少",
    ],
    6: [],  # 占位符
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

# LLM 路由观测状态：每次 identify_question_type 调用前重置
_last_router_method: str = "keyword"
_last_llm_reason: Optional[str] = None
_last_llm_duration_ms: Optional[float] = None

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

    返回 (question_type, relevance)。question_type ∈ 1..6 与 0=RAG。
    ROUTING_MODE=llm 时优先 LLM 初判，失败回退关键词/向量；排他规则仍作为最终兜底。
    每次调用重置模块级 _last_router_method/_last_llm_reason/_last_llm_duration_ms。
    """
    global _last_router_method, _last_llm_reason, _last_llm_duration_ms
    # 每次调用重置观测状态
    _last_router_method = "keyword"
    _last_llm_reason = None
    _last_llm_duration_ms = None

    # 知识性问题：type 0，不调 LLM
    if _is_knowledge_question(question):
        _last_router_method = "knowledge"
        print(f"[路由] 知识性问题 → RAG (type=0)")
        return 0, 1.0

    base_type, base_rel = _identify_question_type_keyword(question)

    # ROUTING_MODE=llm 且 LLM 可用：优先 LLM 初判
    if Config.ROUTING_MODE == "llm" and LLM_AVAILABLE and llm_service.is_available():
        llm_result = _identify_question_type_llm(question, context)
        if llm_result is not None:
            base_type, base_rel = llm_result[0], llm_result[1]
            _last_router_method = "llm"
        else:
            # LLM 失败：回退关键词/向量，router_method 保持 keyword
            _last_router_method = "keyword"
            if base_type == 0 and EMBEDDING_AVAILABLE and embedding_service.is_available():
                base_type, base_rel = _identify_question_type_vector(question)
                if base_type != 0:
                    _last_router_method = "vector"
    else:
        # ROUTING_MODE=keyword 或 LLM 不可用：走现有路径
        if base_type == 0:
            if EMBEDDING_AVAILABLE and embedding_service.is_available():
                base_type, base_rel = _identify_question_type_vector(question)
                if base_type != 0:
                    _last_router_method = "vector"
        # 关键词命中时 router_method 保持 keyword

    # 当用户已选择地块（parcel_id/parcel_code 存在）但路由为RAG时，
    # 尝试回退到通用模型，避免AI回复"没有传递地块编号"
    if base_type == 0 and context is not None:
        has_parcel = context.get("parcel_id") or context.get("parcel_code")
        if has_parcel:
            base_type = _infer_model_from_question(question, context)
            if base_type > 0:
                _last_router_method = "parcel_fallback"
                print(f"[路由] 用户已选地块({has_parcel})，关键词未命中，回退到模型 type={base_type}")

    if context is not None:
        refined_type, _status = apply_exclusive_rules(question, base_type, context)
        print(f"[路由] 问题='{question[:30]}...' → type={base_type}→{refined_type}, "
              f"relevance={base_rel:.2f}, method={_last_router_method}")
        return refined_type, base_rel
    return base_type, base_rel


def _infer_model_from_question(question: str, context: dict) -> int:
    """当用户已选择地块但关键词未命中时，根据问题内容推断模型类型。

    优先级：问题关键词 → 默认 model-1（稳定性退化分析，最通用的地块分析模型）。
    """
    # 尝试从问题中找线索
    if any(w in question for w in ("等级", "评价", "质量", "这块地怎么样", "肥力如何")):
        return 2
    if any(w in question for w in ("障碍", "问题", "毛病", "诊断")):
        return 3
    if any(w in question for w in ("酸化", "pH", "酸性", "石灰")):
        return 4
    if any(w in question for w in ("有机质", "有机肥", "培肥", "秸秆", "施肥方案")):
        return 5
    # 默认：model-1 稳定性退化分析（最通用的地块分析）
    return 1

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

def _safe_parse_llm_result(content: str) -> Optional[tuple[int, float, str]]:
    """解析 LLM 返回内容为 (question_type, relevance, reason)；任何异常返回 None。

    - 自动剥离 markdown 代码块（```json ... ``` 或 ``` ... ```）
    - content 必须为合法 JSON
    - question_type 必须为 int 且在 0..6 范围
    - relevance 缺失默认 0.0；reason 缺失默认空串
    - 不向调用方抛出任何异常
    """
    import json
    try:
        # 剥离 markdown 代码块包裹（LLM 常忽略"仅输出 JSON"指令）
        cleaned = content.strip() if isinstance(content, str) else content
        if isinstance(cleaned, str) and cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # 去掉首行 ```json 或 ```
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            # 去掉末行 ```
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            return None
        if "question_type" not in data:
            return None
        qt = data["question_type"]
        if not isinstance(qt, int) or isinstance(qt, bool):
            return None
        if qt < 0 or qt > 6:
            return None
        relevance = data.get("relevance", 0.0)
        if not isinstance(relevance, (int, float)) or isinstance(relevance, bool):
            relevance = 0.0
        reason = data.get("reason", "")
        if not isinstance(reason, str):
            reason = str(reason)
        return qt, float(relevance), reason
    except Exception:
        return None


def _identify_question_type_llm(
    question: str, context: Optional[dict]
) -> Optional[tuple[int, float, str]]:
    """LLM 初判问题类型。

    - LLM 不可用或调用异常：返回 None（调用方回退关键词）
    - 解析失败/越界：返回 None
    - 成功：返回 (question_type, relevance, reason)，并已写入模块级状态
    """
    global _last_llm_reason, _last_llm_duration_ms
    if not LLM_AVAILABLE or not llm_service.is_available():
        return None

    # 动态构造 prompt：6 个能力 + 用户问题 + 五维上下文 + JSON 输出格式
    capability_lines = []
    for cap in PROFESSIONAL_CAPABILITIES:
        capability_lines.append(
            f"- 类型 {cap.question_type}：{cap.name}（{cap.description}）"
        )
    capabilities_text = "\n".join(capability_lines)

    context_lines = []
    if context:
        for key in ("scale", "data_type", "business_task", "expected_output"):
            val = context.get(key)
            if val:
                context_lines.append(f"- {key}: {val}")
        # 显式标注地块选中状态（LLM 路由关键信号）
        if context.get("parcel_id") or context.get("parcel_code"):
            context_lines.append("- parcel_selected: true（用户已在地图上选中地块）")
    context_text = "\n".join(context_lines) if context_lines else "（未提供）"

    # context 路由规则：用户已选地块时放宽专业模型进入条件
    context_rules = ""
    if context and (context.get("parcel_id") or context.get("parcel_code")):
        context_rules = (
            "\n\n【上下文路由规则】\n"
            "用户已在地图上选中地块（parcel_selected=true），表明需要针对该地块的具体分析，\n"
            "而非通用知识问答。在此场景下：\n"
            "1. 「施肥方案/培肥/改良/治理」类模糊请求 → 应路由到对应专业模型（type 3/4/5）\n"
            "   而非判为知识性问题（type 0）\n"
            "2. 「这块地怎么样/肥力如何」类查询 → 应路由到质量评价类模型（type 2）\n"
            "3. 仅当问题完全与农业/土壤无关时才返回 type 0\n"
        )

    prompt = (
        "你是耕地质量与土壤改良领域的问题分类助手。请根据用户问题，判定它属于以下哪一类问题类型。\n\n"
        "问题类型清单：\n"
        f"{capabilities_text}\n\n"
        "用户问题：\n"
        f"{question}\n\n"
        "五维上下文：\n"
        f"{context_text}"
        f"{context_rules}\n\n"
        "请仅输出严格 JSON，不要任何额外说明或 markdown 代码块：\n"
        '{"question_type": int(0..6, 0=知识性/RAG), '
        '"relevance": float(0..1), "reason": str(简短理由)}'
    )

    import time as _time
    t0 = _time.perf_counter()
    try:
        response = llm_service.generate(prompt, temperature=0.0)
    except Exception:
        _last_llm_reason = None
        _last_llm_duration_ms = round((_time.perf_counter() - t0) * 1000, 2)
        return None

    _last_llm_duration_ms = round((_time.perf_counter() - t0) * 1000, 2)

    if not isinstance(response, dict) or not response.get("success"):
        _last_llm_reason = None
        return None

    content = response.get("content", "")
    if not isinstance(content, str):
        _last_llm_reason = None
        return None

    parsed = _safe_parse_llm_result(content)
    if parsed is None:
        _last_llm_reason = None
        return None

    _last_llm_reason = parsed[2]
    return parsed

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
    elif QUESTION_TYPE_6_KEYWORDS and any(keyword in question for keyword in QUESTION_TYPE_6_KEYWORDS):
        return 6, relevance
    else:
        return 0, relevance
