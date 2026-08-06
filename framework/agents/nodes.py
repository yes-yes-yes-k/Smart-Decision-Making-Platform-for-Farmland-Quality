from __future__ import annotations
from .state import MultiAgentState
from .exclusive_rules import (
    apply_exclusive_rules,
    BOUNDARY_PENDING_MESSAGE,
    ROUTING_STATUS_NORMAL,
    ROUTING_STATUS_BOUNDARY_PENDING,
)
from .routing import (
    identify_question_type,
    _identify_question_type_keyword,
    _identify_question_type_vector,
    _is_knowledge_question,
    check_relevance,
    EMBEDDING_AVAILABLE,
    QUESTION_TYPE_1_KEYWORDS,
    QUESTION_TYPE_2_KEYWORDS,
    QUESTION_TYPE_3_KEYWORDS,
    QUESTION_TYPE_4_KEYWORDS,
    QUESTION_TYPE_5_KEYWORDS,
    QUESTION_TYPE_6_KEYWORDS,
    QUESTION_TYPE_7_KEYWORDS,
    REFERENCE_QUESTIONS,
)

try:
    from framework.llm.service import llm_service
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

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
        "routing_status": "normal",
    }

def identify_question_node(state: MultiAgentState) -> MultiAgentState:
    question = state["request"].get("question", "")
    context = _extract_five_dim_context(state)
    question_type, relevance = identify_question_type(question, context)
    final_type, routing_status = apply_exclusive_rules(question, question_type, context)
    return {
        **state,
        "question_type": final_type,
        "relevance": relevance,
        "routing_status": routing_status,
        "error": None,
    }

def _extract_five_dim_context(state: MultiAgentState) -> dict:
    """从请求提取五维特征上下文（分析尺度/数据类型）。"""
    request = state.get("request", {})
    context: dict = {}
    scale = request.get("scale")
    if not scale:
        question = request.get("question", "")
        if any(w in question for w in ("我的田", "我的地", "这块", "这个地块", "地块")):
            scale = "地块"
        elif any(w in question for w in ("片区", "村")):
            scale = "片区"
        elif any(w in question for w in ("全省", "全市", "全省耕地")):
            scale = "省"
        elif any(w in question for w in ("全县", "县域", "我们县", "本县")):
            scale = "县"
    context["scale"] = scale or "县"
    if request.get("indicators"):
        context["data_type"] = "指标数据"
    elif request.get("parcel_id") or request.get("parcel_code"):
        context["data_type"] = "评价结果"
    else:
        question = request.get("question", "")
        if any(w in question for w in ("施多少", "每亩", "施用量", "用量", "投入量")):
            context["data_type"] = "处方用量"
        else:
            context["data_type"] = "指标数据"
    return context

def route_models(state: MultiAgentState) -> str:
    routing_status = state.get("routing_status", ROUTING_STATUS_NORMAL)
    if routing_status == ROUTING_STATUS_BOUNDARY_PENDING:
        return "boundary_pending"
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

def execute_models(state: MultiAgentState) -> MultiAgentState:
    """调用已由问题类型确定的单一专业能力。"""
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
        return {
            **state,
            "model_results": result,
            "status": "model_completed",
            "error": None,
        }
    except Exception as exc:
        question_type = state.get("question_type")
        return {
            **state,
            "model_results": {
                "status": "error",
                "data": {
                    "question_type": question_type,
                    "agents_invoked": [],
                    "summary": "专业能力执行失败，未调用其他专业模型。",
                    "details": {},
                    "recommendations": [],
                    "error": str(exc),
                },
            },
            "status": "model_completed",
            "error": None,
        }

def boundary_pending_node(state: MultiAgentState) -> MultiAgentState:
    """模型边界待确认：不调用任一易混淆专业 Agent，返回显式降级。"""
    return {
        **state,
        "model_results": {
            "status": "boundary_pending",
            "data": {
                "question_type": state.get("question_type"),
                "agents_invoked": [],
                "summary": BOUNDARY_PENDING_MESSAGE,
                "details": {},
                "recommendations": [],
            },
        },
        "status": "model_completed",
        "error": None,
    }

def llm_generate(state: MultiAgentState) -> MultiAgentState:
    if not LLM_AVAILABLE or not llm_service.is_available():
        return {**state, "llm_response": {}, "error": None}

    question = state["request"].get("question", "")
    question_type = state.get("question_type", 1)

    if not question or question_type not in [1, 2, 3, 4, 5, 6, 7]:
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

        routing_status = state.get("routing_status", ROUTING_STATUS_NORMAL)
        final_result = {
            "status": "ok",
            "question": question,
            "question_type": question_type,
            "relevance": relevance,
            "routing_status": routing_status,
        }

        if routing_status == ROUTING_STATUS_BOUNDARY_PENDING:
            final_result["answer"] = BOUNDARY_PENDING_MESSAGE
            final_result["sources"] = []
            final_result["model_results"] = model_results
            final_result["llm_response"] = ""
            final_result["degradation"] = BOUNDARY_PENDING_MESSAGE
        elif question_type == 0:
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
