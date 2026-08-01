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

try:
    from framework.rag.chain import rag_chain
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False

try:
    from framework.core_engine import core_engine
    CORE_ENGINE_AVAILABLE = True
except ImportError:
    CORE_ENGINE_AVAILABLE = False

# TYPE_1: 等级稳定性/退化风险（model-1）
QUESTION_TYPE_1_KEYWORDS = ["稳定", "稳定性", "稳不稳", "关注清单", "退化风险"]
# TYPE_2: 酸化程度/调理剂/改良方案（model-4）
QUESTION_TYPE_2_KEYWORDS = ["酸化程度", "酸化", "调理剂", "石灰", "碱性材料", "修复", "怎么治", "怎么办", "如何改"]
# TYPE_3: 潜力/障碍因素/主要问题（model-2/3）
QUESTION_TYPE_3_KEYWORDS = ["潜力", "毛病", "问题", "障碍因素", "改良片区"]
# TYPE_4: 有机质/有机肥/肥力/有机碳（model-5/6）
QUESTION_TYPE_4_KEYWORDS = ["有机质", "有机肥", "秸秆", "肥力", "有机碳", "SOC", "Dose"]
# TYPE_5: 质量等级评价（model-7）
QUESTION_TYPE_5_KEYWORDS = ["质量等级", "综合指数", "障碍度排序", "等级评价", "耕地质量", "质量评价", "等级评估"]

RELEVANCE_KEYWORDS = [
    "酸化", "pH", "土壤", "耕地", "治理", "改良", "氮肥", "施肥",
    "调理剂", "石灰", "碱性", "酸性", "交换性酸", "CEC", "阳离子交换量",
    "土壤质量", "农业", "农田", "养分", "种植", "作物", "水稻", "小麦",
    "玉米", "肥料", "有机质", "酸碱度", "酸性土", "碱性土", "改良剂",
    "耕地质量", "地力", "土壤肥力", "培肥", "有机肥", "绿肥", "秸秆还田",
    "稳定性", "退化", "风险", "潜力", "障碍", "问题", "诊断", "综合",
    "提升", "质量等级", "评价", "评估", "监测"
]

REFERENCE_QUESTIONS: Dict[int, List[str]] = {
    1: ["全省耕地质量等级整体稳定吗", "耕地稳定性如何", "哪些地方存在退化风险",
        "等级稳定性较弱的地方", "需要纳入重点关注清单的对象"],
    2: ["全省耕地酸化程度如何", "酸化等级面积统计", "如何治理强酸性耕地",
        "碱性调理剂施用量", "土壤酸化怎么改良"],
    3: ["辖区耕地质量提升的总体潜力有多大", "主要障碍因素是什么", "耕地质量问题诊断",
        "优先改良片区在哪", "耕地存在哪些问题"],
    4: ["耕地有机质含量如何", "有机质怎么提升", "有机肥施用量", "土壤培肥措施"],
    5: ["耕地质量等级是多少", "查询地块的综合指数和障碍度排序", "耕地质量等级评价结果"],
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
    """识别知识性问题（如"什么是X"/"X是什么意思"），路由到 RAG。"""
    if not question:
        return False
    # 开头匹配（强信号）
    if question.startswith(("什么是", "何为", "解释")):
        return True
    # 包含匹配（含义类）
    contains_patterns = ["是什么意思", "什么意思", "定义", "概念", "含义"]
    if any(p in question for p in contains_patterns):
        return True
    return False

def identify_question_type(question: str) -> tuple[int, float]:
    # 知识性预检：命中时走 RAG（TYPE_0）
    if _is_knowledge_question(question):
        return 0, 1.0
    # 关键词优先匹配具体类型
    kw_type, kw_rel = _identify_question_type_keyword(question)
    if kw_type != 0:
        return kw_type, kw_rel
    # 关键词未命中具体类型，回退到向量匹配
    if EMBEDDING_AVAILABLE and embedding_service.is_available():
        return _identify_question_type_vector(question)
    return 0, kw_rel

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
    # 关键词优先匹配具体类型（按 TYPE_1→2→3→4→5 顺序，避免宽泛词误匹配）
    if any(keyword in question for keyword in QUESTION_TYPE_1_KEYWORDS):
        return 1, max(relevance, 0.3)
    if any(keyword in question for keyword in QUESTION_TYPE_2_KEYWORDS):
        return 2, max(relevance, 0.3)
    if any(keyword in question for keyword in QUESTION_TYPE_3_KEYWORDS):
        return 3, max(relevance, 0.3)
    if any(keyword in question for keyword in QUESTION_TYPE_4_KEYWORDS):
        return 4, max(relevance, 0.3)
    if any(keyword in question for keyword in QUESTION_TYPE_5_KEYWORDS):
        return 5, max(relevance, 0.3)
    # 无具体关键词命中
    if relevance < 0.2:
        return 0, relevance
    return 0, relevance

def initialize_state(state: MultiAgentState) -> MultiAgentState:
    return {
        **state,
        "status": "running",
        "error": None,
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": state.get("conversation_history", []),
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
        return "rag_chat"
    return "execute_models"

def rag_chat_node(state: MultiAgentState) -> MultiAgentState:
    question = state["request"].get("question", "")
    conversation_history = state.get("conversation_history", [])

    if not RAG_AVAILABLE:
        return {
            **state,
            "rag_response": {
                "success": False,
                "answer": "RAG服务不可用",
                "sources": [],
            },
            "error": None,
        }

    try:
        result = rag_chain.chat(question, conversation_history=conversation_history)
        return {
            **state,
            "rag_response": result,
            "error": None,
        }
    except Exception as e:
        return {
            **state,
            "rag_response": {
                "success": False,
                "answer": f"RAG处理失败: {str(e)}",
                "sources": [],
            },
            "error": None,
        }

async def _execute_model_concurrent(model_name: str, func: Callable, semaphore: asyncio.Semaphore, **kwargs) -> Tuple[str, Any]:
    async with semaphore:
        try:
            result = func(**kwargs)
            return model_name, {"success": True, "result": result}
        except Exception as e:
            return model_name, {"success": False, "error": str(e)}

async def _execute_model_dependent(model_name: str, func: Callable, dep_result: dict, **kwargs) -> Tuple[str, Any]:
    try:
        result = func(assessment=dep_result, **kwargs)
        return model_name, {"success": True, "result": result}
    except Exception as e:
        return model_name, {"success": False, "error": str(e)}

QUESTION_TYPE_TO_MODEL_ID = {
    1: "acidification-governance",
    2: "multi-factor-collaborative-improvement",
    3: "organic-matter-improvement",
}

def execute_models(state: MultiAgentState) -> MultiAgentState:
    # 优先调用 AgentManager 进行多智能体协作
    try:
        from framework.agents.manager import agent_manager

        question = state["request"].get("question", "")
        context = {
            "area_code": state["request"].get("area_code", "lechang"),
            "data": state.get("data", {}),
        }
        # 透传地块标识符到 context top-level（模型优先从 top-level 读取）
        for key in ("parcel_id", "parcel_code"):
            if key in state["request"]:
                context[key] = state["request"][key]
        # 透传 question_type 到 context（agent 可能需要）
        if "question_type" in state:
            context["question_type"] = state["question_type"]
        # 透传可能的土壤参数与区域/土地类型
        for key in ("longitude", "latitude", "target_ph", "context", "land_type", "fertilizer_type"):
            if key in state["request"]:
                context[key] = state["request"][key]

        result = agent_manager.process(question, context)
        if result.get("status") == "ok":
            return {
                **state,
                "model_results": result,
                "status": "model_completed",
                "error": None,
            }
    except Exception:
        # AgentManager 失败时回退到原模型执行逻辑
        pass

    return _execute_models_fallback(state)

def _execute_models_fallback(state: MultiAgentState) -> MultiAgentState:
    question_type = state["question_type"]
    request = state["request"]
    data = state["data"]

    max_concurrent = Config.get_max_concurrent()

    async def run_models():
        semaphore = asyncio.Semaphore(max_concurrent)
        results = {}

        independent = []
        dependent = []

        if question_type == 1:
            independent.append("acidification_assessment")
        elif question_type == 2:
            independent.append("acidification_assessment")
            dependent.append("lime_calculation")
        elif question_type == 3:
            dependent.append("nitrogen_impact")

        if independent:
            from framework.domain.assessment.acidification import assess_acidification
            tasks = [_execute_model_concurrent(name, assess_acidification, semaphore, soil_data=data) for name in independent]
            ind_results = await asyncio.gather(*tasks)
            results.update(dict(ind_results))

        if dependent:
            dep_kwargs = {}
            if "lime_calculation" in dependent:
                from framework.domain.calculation.lime_calculator import calculate_lime_demand
                assess_result = results.get("acidification_assessment", {}).get("result", {})
                tasks = [_execute_model_dependent("lime_calculation", calculate_lime_demand, assess_result,
                    target_ph=request.get("target_ph", 6.0),
                    soil_depth=request.get("soil_depth", 20),
                    bulk_density=request.get("bulk_density", 1.2),
                    safety_factor=request.get("safety_factor", 1.3),
                )]
                dep_results = await asyncio.gather(*tasks)
                results.update(dict(dep_results))
            elif "nitrogen_impact" in dependent:
                from framework.domain.assessment.acidification import simulate_nitrogen_impact
                assess_result = {}
                if question_type == 3 and "acidification_assessment" not in results:
                    from framework.domain.assessment.acidification import assess_acidification
                    _, res = await _execute_model_concurrent("acidification_assessment", assess_acidification, semaphore, soil_data=data)
                    assess_result = res.get("result", {})
                    results["acidification_assessment"] = res
                else:
                    assess_result = results.get("acidification_assessment", {}).get("result", {})
                tasks = [_execute_model_dependent("nitrogen_impact", simulate_nitrogen_impact, assess_result,
                    current_ph=request.get("current_ph", 5.5),
                    nitrogen_rates=request.get("nitrogen_rates", [0, 50, 100, 150, 200]),
                )]
                dep_results = await asyncio.gather(*tasks)
                results.update(dict(dep_results))

        return results

    model_results = asyncio.run(run_models())

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
        rag_response = state.get("rag_response", {})

        final_result = {
            "status": "ok",
            "question": question,
            "question_type": question_type,
            "relevance": relevance,
        }

        if question_type == 0:
            final_result["answer"] = rag_response.get("answer", "")
            final_result["sources"] = rag_response.get("sources", [])
            final_result["model_results"] = {}
            final_result["llm_response"] = ""
        else:
            final_result["model_results"] = model_results
            final_result["llm_response"] = llm_response.get("content", "")

            agent_data = model_results.get("data", {}) if isinstance(model_results, dict) else {}
            agent_summary = agent_data.get("summary", "")
            agent_details = agent_data.get("details", {}) if isinstance(agent_data, dict) else {}

            all_sources = []
            if isinstance(agent_details, dict):
                for agent_id, detail in agent_details.items():
                    if isinstance(detail, dict):
                        sources = detail.get("sources", [])
                        if sources:
                            all_sources.extend(sources)
                        evidence = detail.get("evidence", [])
                        if evidence and not sources:
                            for ev in evidence:
                                if isinstance(ev, dict) and ev.get("doc_name"):
                                    all_sources.append(ev)

            if llm_response.get("content"):
                final_result["answer"] = llm_response.get("content", "")
            elif agent_summary:
                final_result["answer"] = agent_summary
            else:
                final_result["answer"] = llm_response.get("content", "")

            final_result["sources"] = all_sources if all_sources else []
            if not final_result["sources"] and rag_response.get("sources"):
                final_result["sources"] = rag_response.get("sources", [])

        return {**state, "model_results": final_result, "status": "completed", "error": None}
    except Exception as e:
        return {**state, "status": "failed", "error": str(e)}

def finalize(state: MultiAgentState) -> MultiAgentState:
    return state