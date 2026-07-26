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

QUESTION_TYPE_1_KEYWORDS = [
    "等级稳定", "稳定性", "稳不稳", "稳定吗", "稳定性较弱", "退化风险",
    "关注清单", "重点关注", "临界状态", "风险类型", "等级整体", "掉级",
    # 模型1 稳定性风险关键词
    "稳定性评价", "等级边界安全度", "指标支撑均衡度", "关键指标临界度",
    "空间邻域一致性", "历史变化趋势", "掉级风险", "关键因子退化",
    "退化空间集聚", "持续低质风险",
]
QUESTION_TYPE_2_KEYWORDS = [
    "酸化程度", "酸化等级", "酸化现状", "酸化严重", "酸化了", "酸化治理",
    "调理剂", "碱性材料", "碱性调理剂", "木本泥炭", "石灰", "pH提升",
    "土地利用类型", "酸化",
    # 模型3 酸化改良关键词
    "酸化改良", "酸化分区", "改良方案", "土壤酸化", "酸性改良",
]
QUESTION_TYPE_3_KEYWORDS = [
    "潜力", "障碍因素", "主要问题", "障碍诊断", "潜力分布", "障碍组合",
    "提升潜力", "地块诊断", "毛病", "障碍等级", "哪些问题", "有问题",
    # 模型3 障碍诊断关键词
    "障碍识别", "障碍程度", "障碍因子", "精准识别", "单一障碍", "多障碍",
]
QUESTION_TYPE_4_KEYWORDS = [
    "有机质", "有机肥", "秸秆", "肥力", "综合地力", "有机碳", "SOC", "soc",
    "施用量", "施肥量", "Dose", "dose", "培肥", "综合肥力",
]
QUESTION_TYPE_5_KEYWORDS = [
    # exe 质量等级评价关键词
    "质量等级", "等级评价", "综合指数", "指标隶属度", "障碍度排序",
    "耕地质量等级", "质量评价", "等级评定", "指标权重",
]

# 知识性问题模式：匹配到的问题走 RAG 知识库，不路由到专业模型
# 开头匹配：问题以这些前缀起始
KNOWLEDGE_QUESTION_PATTERNS_START = [
    "什么是", "何为", "解释",
]
# 包含匹配：问题中包含这些子串
KNOWLEDGE_QUESTION_PATTERNS_CONTAIN = [
    "是什么意思", "什么意思", "定义", "概念", "含义",
]

RELEVANCE_KEYWORDS = [
    "酸化", "pH", "土壤", "耕地", "治理", "改良", "氮肥", "施肥",
    "调理剂", "石灰", "碱性", "酸性", "交换性酸", "CEC", "阳离子交换量",
    "土壤质量", "农业", "农田", "养分", "种植", "作物", "水稻", "小麦",
    "玉米", "肥料", "有机质", "酸碱度", "酸性土", "碱性土", "改良剂",
    # 扩展：覆盖 xlsx 经典问题通用词，确保 relevance >= 0.3
    "田", "地", "质量", "等级", "稳定", "潜力", "障碍", "问题",
    "乡镇", "县", "片区", "地块", "农户", "风险", "关注", "清单",
    "诊断", "毛病", "增产", "粮食", "碳氮比", "全氮", "容重",
    "有机肥", "施用量",  # 补充：TYPE_4 关键词也需通过 relevance 阈值（Task 5 修复）
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
        "辖区耕地质量提升的总体潜力有多大可增产多少粮食",
        "我们县划定的优先改良片区具体在哪几个村每块潜力多大",
        "我这块地到底有啥毛病",
        "全省耕地质量存在哪些问题",
        "县乡镇里的耕地在哪些方面有问题",
    ],
    4: [
        "全省耕地土壤有机质含量如何空间分布情况",
        "为了提升耕地土壤有机质有机肥或者秸秆每亩施用量多少",
        "本县耕地土壤有机质平均含量是多少",
        "我的田肥力怎么样",
        "我的田土壤有机碳含量大概多少",
        "我这块地大概需要施多少有机肥",
    ],
    5: [
        "我的田耕地质量等级是多少",
        "查询地块的综合指数和障碍度排序",
        "这块地的耕地质量等级评价结果",
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
    """检测问题是否为知识性问题（如「什么是X」「X是什么意思」）。

    知识性问题应走 RAG 知识库，而非路由到专业模型。
    匹配策略：
    1. 开头匹配：问题以「什么是」「何为」「解释」起始
    2. 包含匹配：问题含「是什么意思」「什么意思」「定义」「概念」「含义」
    """
    if not question or not isinstance(question, str):
        return False
    # 开头匹配
    for pattern in KNOWLEDGE_QUESTION_PATTERNS_START:
        if question.startswith(pattern):
            return True
    # 包含匹配
    for pattern in KNOWLEDGE_QUESTION_PATTERNS_CONTAIN:
        if pattern in question:
            return True
    return False


def identify_question_type(question: str) -> tuple[int, float]:
    # 知识性问题预检：命中则直接走 RAG（type 0），不进入专业模型路由
    if _is_knowledge_question(question):
        return 0, 1.0
    # D5: 关键词匹配优先于向量匹配——先查关键词，命中（返回非 0）即采用，
    # 即使向量匹配的相关性分数较高也不覆盖关键词结果
    result = _identify_question_type_keyword(question)
    if result[0] != 0:
        return result
    # 关键词未命中，降级到向量匹配（embedding 可用时）
    if EMBEDDING_AVAILABLE and embedding_service.is_available():
        return _identify_question_type_vector(question)
    return result

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
    if max_similarity < 0.70:
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
    elif any(keyword in question for keyword in QUESTION_TYPE_4_KEYWORDS):
        return 4, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_5_KEYWORDS):
        return 5, relevance
    else:
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
    1: "model-1",
    2: "model-4",
    3: "model-2,model-3",  # 保留原值（此字典用于 fallback，不影响 AgentManager 路由）
    4: "model-5,model-6",  # 保留原值
    5: "model-7",          # 新增：type 5 fallback 路径
}

def execute_models(state: MultiAgentState) -> MultiAgentState:
    # 优先调用 AgentManager 进行多智能体协作
    try:
        from framework.agents.manager import agent_manager

        question = state["request"].get("question", "")
        context = {
            "area_code": state["request"].get("area_code", "lechang"),
            "data": state.get("data", {}),
            "question_type": state.get("question_type"),
        }
        # 透传可能的土壤参数与地块标识符
        # parcel_id（数字字符串）给 model-1/3/4 查 DB，parcel_code（字母数字）给 model-7 调 fortran exe
        for key in ("longitude", "latitude", "target_ph", "context",
                    "parcel_id", "parcel_code"):
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

    if not question or question_type not in [1, 2, 3, 4, 5]:
        return {**state, "llm_response": {}, "error": None}

    try:
        # 专业智能体不再各自调用 LLM；此处是模型路线唯一的 LLM 总结调用。
        prompt = (
            "你是耕地质量与土壤改良领域的助手。请基于专业智能体结果，"
            "整合成一份准确、简洁、可执行的中文答复。不要编造未提供的数据，"
            "保留明确的数值、单位和建议。\n"
            f"用户问题：{question}\n"
            f"专业智能体结果：{state.get('model_results', {})}"
        )
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

            if llm_response.get("success") and llm_response.get("content"):
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
