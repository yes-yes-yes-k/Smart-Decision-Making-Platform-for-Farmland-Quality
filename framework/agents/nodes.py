from __future__ import annotations
import asyncio
import numpy as np
from typing import Any, Tuple, List, Dict, Optional, Callable
from .state import MultiAgentState
from framework.config import Config

try:
    from framework.llm.service import llm_service
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

try:
    from framework.embedding.service import embedding_service
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False

QUESTION_TYPE_1_KEYWORDS = ["酸化程度", "酸化等级", "pH分级", "酸度", "酸化现状", "土壤酸性", "酸性分级"]
QUESTION_TYPE_2_KEYWORDS = ["治理", "调理剂", "石灰", "碱性材料", "改良", "修复", "调理", "施加", "用量"]
QUESTION_TYPE_3_KEYWORDS = ["氮肥", "pH下降", "施氮", "酸化原因", "氮素", "化肥", "施肥"]

RELEVANCE_KEYWORDS = [
    "酸化", "pH", "土壤", "耕地", "治理", "改良", "氮肥", "施肥",
    "调理剂", "石灰", "碱性", "酸性", "交换性酸", "CEC", "阳离子交换量",
    "土壤质量", "农业", "农田", "养分", "种植", "作物", "水稻", "小麦",
    "玉米", "肥料", "有机质", "酸碱度", "酸性土", "碱性土", "改良剂"
]

REFERENCE_QUESTIONS: Dict[int, List[str]] = {
    1: ["全省耕地酸化程度如何", "土壤pH分布情况", "酸化等级面积统计", "耕地酸性现状评估"],
    2: ["如何治理强酸性耕地", "石灰施用量计算", "土壤改良方案", "酸性土壤调理方法"],
    3: ["施氮肥会导致土壤pH下降多少", "氮肥对土壤酸化的影响", "不同施氮量对pH的影响"],
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

def identify_question_type(question: str) -> tuple[int, float]:
    if EMBEDDING_AVAILABLE and embedding_service.is_available():
        return _identify_question_type_vector(question)
    else:
        return _identify_question_type_keyword(question)

def _identify_question_type_vector(question: str) -> tuple[int, float]:
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
    if max_similarity < 0.5:
        return 0, max_similarity
    return best_type, max_similarity

def _identify_question_type_keyword(question: str) -> tuple[int, float]:
    relevance = _check_relevance_keyword(question)
    if relevance < 0.3:
        return 0, relevance
    if any(keyword in question for keyword in QUESTION_TYPE_1_KEYWORDS):
        return 1, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_2_KEYWORDS):
        return 2, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_3_KEYWORDS):
        return 3, relevance
    else:
        return 1, relevance

def initialize_state(state: MultiAgentState) -> MultiAgentState:
    return {
        **state,
        "status": "running",
        "error": None,
        "data": {},
        "model_results": {},
        "llm_response": {},
        "question_type": None,
        "relevance": None,
    }

def identify_question_node(state: MultiAgentState) -> MultiAgentState:
    question = state["request"].get("question", "")
    question_type, relevance = identify_question_type(question)
    return {
        **state,
        "question_type": question_type,
        "relevance": relevance,
        "error": None,
    }

def route_models(state: MultiAgentState) -> str:
    question_type = state["question_type"]
    if question_type == 0:
        return "finalize"
    return "execute_models"

async def _execute_model_concurrent(model_name: str, func: Callable, **kwargs) -> Tuple[str, Any]:
    try:
        result = func(**kwargs)
        return model_name, {"success": True, "result": result}
    except Exception as e:
        return model_name, {"success": False, "error": str(e)}

def execute_models(state: MultiAgentState) -> MultiAgentState:
    question_type = state["question_type"]
    request = state["request"]
    data = state["data"]

    models_to_run = []
    if question_type == 1:
        models_to_run.append("acidification_assessment")
    elif question_type == 2:
        models_to_run.append("acidification_assessment")
        models_to_run.append("lime_calculation")
    elif question_type == 3:
        models_to_run.append("nitrogen_impact")

    max_concurrent = Config.get_max_concurrent()

    async def run_concurrent():
        tasks = []
        for model_name in models_to_run[:max_concurrent]:
            if model_name == "acidification_assessment":
                from framework.domain.assessment.acidification import assess_acidification
                tasks.append(_execute_model_concurrent("acidification_assessment", assess_acidification, soil_data=data))
            elif model_name == "lime_calculation":
                from framework.domain.calculation.lime_calculator import calculate_lime_demand
                tasks.append(_execute_model_concurrent("lime_calculation", calculate_lime_demand,
                    assessment=state.get("model_results", {}).get("acidification_assessment", {}).get("result", {}),
                    target_ph=request.get("target_ph", 6.0),
                    soil_depth=request.get("soil_depth", 20),
                    bulk_density=request.get("bulk_density", 1.2),
                    safety_factor=request.get("safety_factor", 1.3),
                ))
            elif model_name == "nitrogen_impact":
                from framework.domain.assessment.acidification import simulate_nitrogen_impact
                tasks.append(_execute_model_concurrent("nitrogen_impact", simulate_nitrogen_impact,
                    assessment=state.get("model_results", {}).get("acidification_assessment", {}).get("result", {}),
                    current_ph=request.get("current_ph", 5.5),
                    nitrogen_rates=request.get("nitrogen_rates", [0, 50, 100, 150, 200]),
                ))

        results = await asyncio.gather(*tasks)
        return dict(results)

    model_results = asyncio.run(run_concurrent())

    return {
        **state,
        "model_results": model_results,
        "error": None,
    }

def llm_generate(state: MultiAgentState) -> MultiAgentState:
    if not LLM_AVAILABLE or not llm_service.is_available():
        return {**state, "llm_response": {}, "error": None}

    question = state["request"].get("question", "")
    question_type = state.get("question_type", 1)

    if not question or question_type not in [1, 2, 3]:
        return {**state, "llm_response": {}, "error": None}

    try:
        prompt = f"基于以下数据回答问题：\n问题类型: {question_type}\n问题: {question}\n数据: {state.get('model_results', {})}"
        llm_result = llm_service.generate(prompt)
        return {**state, "llm_response": llm_result, "error": None}
    except Exception as e:
        return {**state, "llm_response": {"success": False, "error": str(e)}, "error": None}

def aggregate_results(state: MultiAgentState) -> MultiAgentState:
    try:
        question = state["request"].get("question", "")
        question_type = state.get("question_type", 1)
        relevance = state.get("relevance", 0.0)
        model_results = state.get("model_results", {})
        llm_response = state.get("llm_response", {})

        final_result = {
            "status": "ok",
            "question": question,
            "question_type": question_type,
            "relevance": relevance,
            "model_results": model_results,
            "llm_response": llm_response.get("content", ""),
        }

        if question_type == 0:
            final_result["status"] = "rejected"
            final_result["message"] = "问题与耕地土壤酸化主题不相关"

        return {**state, "model_results": final_result, "status": "completed", "error": None}
    except Exception as e:
        return {**state, "status": "failed", "error": str(e)}

def finalize(state: MultiAgentState) -> MultiAgentState:
    return state