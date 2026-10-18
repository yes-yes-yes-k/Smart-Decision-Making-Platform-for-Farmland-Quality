from __future__ import annotations
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone
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
    REFERENCE_QUESTIONS,
)
from .capabilities import get_capability_by_question_type
from framework.analysis_context.contracts import AnalysisContext
from framework.analysis_context.guard import AnalysisRequirementGuard
from framework.analysis_context.provenance import ResultProvenanceBuilder

analysis_requirement_guard = AnalysisRequirementGuard()
result_provenance_builder = ResultProvenanceBuilder()

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

# 业务任务关键词表（Design Doc 决策 A）
BUSINESS_TASK_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "障碍诊断": ("诊断", "毛病", "障碍"),
    "酸化改良": ("酸化", "调理剂", "石灰", "治酸", "pH提升", "碱性"),
    "有机质培肥": ("有机质", "有机肥", "秸秆", "培肥"),
    "稳定性评价": ("稳定性", "退化", "掉级", "稳定"),
    "质量等级评价": ("质量等级", "等级评价", "综合指数", "等级评定"),
}

# 预期输出关键词表（Design Doc 决策 A）
EXPECTED_OUTPUT_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "评价结果": ("等级", "指数", "评价结果", "评定"),
    "处方用量": ("施多少", "每亩", "用量", "投入量"),
    "诊断报告": ("诊断", "问题", "毛病", "障碍"),
}


def _match_first_keyword(question: str, table: Dict[str, Tuple[str, ...]]) -> Optional[str]:
    """遍历关键词表，返回第一个命中关键词的标签；未命中返回 None。"""
    for label, keywords in table.items():
        for kw in keywords:
            if kw in question:
                return label
    return None


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
        "analysis_context": state.get("analysis_context", {
            "mode": "spatial", "version": 0, "object": None,
        }),
        "calculation_mode": state.get("calculation_mode", "spatial"),
        "guard_decision": state.get("guard_decision", {}),
        "validated_identifiers": state.get("validated_identifiers", {}),
        "scenario_inputs": state.get("scenario_inputs", {}),
        "user_id": state.get("user_id"),
        "conversation_id": state.get("conversation_id"),
    }

def identify_question_node(state: MultiAgentState) -> MultiAgentState:
    import uuid
    from framework.observability.observe import observe_routing

    question = state["request"].get("question", "")
    context = _extract_five_dim_context(state)
    trace_id = uuid.uuid4().hex
    question_type, relevance, final_type, routing_status = observe_routing(
        question, context, trace_id=trace_id
    )
    return {
        **state,
        "question_type": final_type,
        "relevance": relevance,
        "routing_status": routing_status,
        "trace_id": trace_id,
        "error": None,
    }

def _extract_five_dim_context(state: MultiAgentState) -> dict:
    """从请求提取五维特征上下文（分析尺度/数据类型/业务任务/预期输出）。

    同时透传 parcel_id/parcel_code 到 context，供 LLM 路由感知"用户已选地块"场景。
    """
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

    # 业务任务提取：第一个命中关键词表的标签作为维度值
    question_text = request.get("question", "")
    context["business_task"] = _match_first_keyword(question_text, BUSINESS_TASK_KEYWORDS)
    # 预期输出提取
    context["expected_output"] = _match_first_keyword(question_text, EXPECTED_OUTPUT_KEYWORDS)
    # 透传地块标识符（LLM 路由可感知"用户已选地块"场景）
    if request.get("parcel_id"):
        context["parcel_id"] = request["parcel_id"]
    if request.get("parcel_code"):
        context["parcel_code"] = request["parcel_code"]
    return context

def route_models(state: MultiAgentState) -> str:
    routing_status = state.get("routing_status", ROUTING_STATUS_NORMAL)
    if routing_status == ROUTING_STATUS_BOUNDARY_PENDING:
        return "boundary_pending"
    question_type = state["question_type"]
    if question_type == 0:
        return "rag_chat"
    return "execute_models"


def analysis_requirement_node(state: MultiAgentState) -> MultiAgentState:
    capability = get_capability_by_question_type(state.get("question_type"))
    context = AnalysisContext.from_dict(state["analysis_context"])
    decision = analysis_requirement_guard.evaluate(
        capability, context, inputs=state.get("scenario_inputs", {}),
    )
    serialized = {
        "allowed": decision.allowed,
        "interaction_state": decision.interaction_state,
        "required_object_types": list(decision.required_object_types),
        "missing_inputs": list(decision.missing_inputs),
        "message": decision.message,
    }
    return {**state, "guard_decision": serialized}


def route_after_requirement(state: MultiAgentState) -> str:
    if state.get("routing_status") == ROUTING_STATUS_BOUNDARY_PENDING:
        return "boundary_pending"
    if state.get("question_type") == 0:
        return "rag_chat"
    if not state.get("guard_decision", {}).get("allowed", False):
        return "needs_input"
    return "execute_models"


def needs_input_node(state: MultiAgentState) -> MultiAgentState:
    decision = state["guard_decision"]
    return {
        **state,
        "model_results": {
            "status": decision["interaction_state"],
            "data": {
                "question_type": state.get("question_type"),
                "agents_invoked": [],
                "details": {},
                "recommendations": [],
                "summary": decision["message"],
            },
        },
        "status": "model_completed",
        "error": None,
    }

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
        result = rag_chain.chat(
            question,
            conversation_history=conversation_history,
            user_id=state.get("user_id"),
        )
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

def _execute_via_function_calling(
    question: str, context: dict, trace_id: Optional[str] = None
) -> Optional[dict]:
    """尝试通过 LLM function calling 调用专题模型。

    成功返回标准化的 model_results dict；失败返回 None 让调用方 fallback。
    """
    try:
        from framework.config import Config

        if not getattr(Config, "FUNCTION_CALLING_ENABLED", True):
            return None

        from framework.function_calling.specialized_tools import (
            get_specialized_tools,
            TOOL_NAME_TO_AGENT_ID,
        )
        from framework.llm.service import llm_service

        tools = get_specialized_tools()
        if not tools or not llm_service.is_available():
            return None

        # 构造 default_args：从 context 提取地块标识和参数
        default_args: dict = {}
        for key in (
            "parcel_id", "parcel_code", "area_code", "land_type",
            "fertilizer_type", "target_ph", "db_path",
        ):
            if key in context and context[key] is not None:
                default_args[key] = context[key]

        result = llm_service.generate_with_tools(
            prompt=question,
            messages=None,
            tools=tools,
            default_args=default_args,
            trace_id=trace_id,
        )

        if not result.get("success"):
            print(
                f"[FC] function calling 失败: {result.get('reason', 'unknown')}，"
                f"回退到关键词路由",
                flush=True,
            )
            return None

        # 工具已经通过 BaseAgent.analyze 返回规范结果。
        tool_results: dict = result.get("tool_results", {})
        # LLM 未调用任何工具（直接给出文本答复）→ 降级走关键词路由。
        # 对齐方案设计："无 tool_calls → 降级走旧 agent_manager.process 路径"，
        # 避免空结果绕过 fallback 导致用户拿不到真实模型计算。
        if not tool_results:
            return None
        agents_invoked = [
            TOOL_NAME_TO_AGENT_ID.get(name, name)
            for name in (tc.get("tool_name", "") for tc in result.get("tool_calls_trace", []))
        ]
        # 去重保持顺序
        seen = set()
        agents_invoked = [a for a in agents_invoked if not (a in seen or seen.add(a))]

        question_type = context.get("question_type")
        return {
            "status": "ok",
            "question_type": question_type,
            "models": {aid: tool_results[aid] for aid in agents_invoked if aid in tool_results},
            "answer": result.get("content", ""),
            "recommendations": [],
            "routing_method": "function_calling",
            "tool_calls_trace": result.get("tool_calls_trace", []),
            "iterations": result.get("iterations", 0),
        }
    except Exception as exc:
        print(f"[FC] _execute_via_function_calling 异常: {exc}，回退到关键词路由", flush=True)
        return None


def execute_models(state: MultiAgentState) -> MultiAgentState:
    """调用已由问题类型确定的专业能力（优先 function calling，失败回退关键词路由）。"""
    try:
        from framework.agents.manager import agent_manager

        question = state["request"].get("question", "")
        context = _build_verified_execution_context(state)
        print(f"[execute_models] context: parcel_id={context.get('parcel_id')}, "
              f"parcel_code={context.get('parcel_code')}, "
              f"question_type={context.get('question_type')}, "
              f"area_code={context.get('area_code')}")
        # 透传 question_type 到 context（agent 可能需要）
        if "question_type" in state:
            context["question_type"] = state["question_type"]

        # 优先尝试 function calling 路径
        trace_id = state.get("trace_id")
        fc_result = _execute_via_function_calling(question, context, trace_id)
        if fc_result is not None:
            return {
                **state,
                "model_results": fc_result,
                "status": "model_completed",
                "error": None,
            }

        # fallback: 原有关键词路由路径
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
                "question_type": question_type,
                "models": {},
                "answer": "专业能力执行失败，未调用其他专业模型。",
                "recommendations": [],
                "routing_method": "keyword_fallback",
            },
            "status": "model_completed",
            "error": None,
        }


def _build_verified_execution_context(state: MultiAgentState) -> dict:
    analysis_context = state.get("analysis_context", {})
    mode = analysis_context.get("mode", state.get("calculation_mode", "spatial"))
    if mode == "scenario":
        context = dict(state.get("scenario_inputs", {}))
    else:
        context = {}
        obj = analysis_context.get("object") or {}
        if obj.get("type") == "parcel":
            context["parcel_id"] = obj["id"]
        if obj.get("area_code") is not None:
            context["area_code"] = obj["area_code"]
        parcel_code = state.get("validated_identifiers", {}).get("parcel_code")
        if parcel_code is not None and state.get("question_type") == 2:
            context["parcel_code"] = parcel_code
    context.update({
        "question_type": state.get("question_type"),
        "calculation_mode": mode,
        "execution_channel": "chat",
        "guard_passed": True,
        "execution_context": {
            "trace_id": state.get("trace_id"),
            "analysis_context": analysis_context,
            "user_id": state.get("user_id"),
            "conversation_id": state.get("conversation_id"),
        },
    })
    return context


def retrieve_professional_evidence(state: MultiAgentState) -> MultiAgentState:
    """Use the same permission-safe evidence tool for every professional agent."""
    try:
        from framework.config import Config
        if not Config.KG_PROFESSIONAL_EVIDENCE_ENABLED:
            return state
        from framework.rag.chain import rag_chain
        question = state["request"].get("question", "")
        if not question:
            return state
        bundle = rag_chain.retrieve_evidence_bundle(
            question,
            user_id=state.get("user_id"),
            conversation_id=state.get("conversation_id"),
            conversation_history=state.get("conversation_history", []),
        )
        return {
            **state,
            "rag_response": {"success": True, **bundle},
            "error": None,
        }
    except Exception as exc:
        # Professional calculations remain usable if evidence retrieval is down.
        return {
            **state,
            "rag_response": {
                "success": False, "context": "", "sources": [],
                "degradation": "professional_evidence_unavailable",
                "error": str(exc),
            },
            "error": None,
        }

def boundary_pending_node(state: MultiAgentState) -> MultiAgentState:
    """模型边界待确认：不调用任一易混淆专业 Agent，返回显式降级。"""
    return {
        **state,
        "model_results": {
            "status": "boundary_pending",
            "question_type": state.get("question_type"),
            "models": {},
            "answer": BOUNDARY_PENDING_MESSAGE,
            "recommendations": [],
            "routing_method": "boundary_pending",
        },
        "status": "model_completed",
        "error": None,
    }

def llm_generate(state: MultiAgentState) -> MultiAgentState:
    model_results = state.get("model_results", {})
    if model_results.get("routing_method") == "function_calling" and model_results.get("answer"):
        return {**state, "llm_response": {"success": True, "content": model_results["answer"]}, "error": None}
    if not LLM_AVAILABLE or not llm_service.is_available():
        return {**state, "llm_response": {}, "error": None}

    question = state["request"].get("question", "")
    question_type = state.get("question_type", 1)

    if not question or question_type not in [1, 2, 3, 4, 5]:
        return {**state, "llm_response": {}, "error": None}

    try:
        from .output_contract import llm_context

        contexts = {
            agent_id: llm_context(model_result)
            for agent_id, model_result in model_results.get("models", {}).items()
        }
        evidence_context = str(state.get("rag_response", {}).get("context") or "")
        prompt = (
            "你是耕地质量与土壤改良领域的助手。请基于专业智能体结果，"
            "整合成一份准确、简洁、可执行的中文答复。不要编造未提供的数据，"
            "保留明确的数值、单位和建议。回复中必须使用中文标准字段名称，"
            "不得向用户展示 GGNL、DXBW、SXJ 等模型内部字段缩写。\n"
            "知识图谱证据只能解释专业模型结果，不得覆盖模型实际计算值；"
            "若证据不足，应省略扩展解释。指标分类角色与指标获取方式是独立维度。\n"
            f"用户问题：{question}\n"
            f"专业模型紧凑结果：{contexts}\n"
            f"经权限过滤的知识图谱/知识库证据：{evidence_context or '无'}"
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
            "analysis_context": state.get("analysis_context"),
            "interaction_state": state.get("guard_decision", {}).get("interaction_state", "completed"),
            "routing": {"question_type": question_type, "status": routing_status},
            "retrieval": (
                rag_response.get("retrieval")
                or rag_response.get("diagnostics")
                or {}
            ),
        }

        if routing_status == ROUTING_STATUS_BOUNDARY_PENDING:
            final_result["answer"] = BOUNDARY_PENDING_MESSAGE
            final_result["sources"] = []
            final_result["models"] = model_results.get("models", {}) if isinstance(model_results, dict) else {}
            final_result["llm_response"] = ""
            final_result["degradation"] = BOUNDARY_PENDING_MESSAGE
        elif not state.get("guard_decision", {}).get("allowed", True):
            decision = state["guard_decision"]
            final_result["answer"] = decision["message"]
            final_result["sources"] = []
            final_result["model_results"] = model_results
            final_result["llm_response"] = ""
            final_result["required_object_types"] = decision["required_object_types"]
            final_result["missing_inputs"] = decision["missing_inputs"]
        elif question_type == 0:
            final_result["answer"] = rag_response.get("answer", "")
            final_result["sources"] = rag_response.get("sources", [])
            final_result["models"] = {}
            final_result["llm_response"] = ""
        else:
            final_result["models"] = model_results.get("models", {}) if isinstance(model_results, dict) else {}
            final_result["llm_response"] = llm_response.get("content", "")

            agent_summary = model_results.get("answer", "") if isinstance(model_results, dict) else ""
            # 迁移窗口内兼容旧的 AgentManager 包络，但不再向新结果写入该结构。
            if not agent_summary and isinstance(model_results, dict):
                legacy_data = model_results.get("data", {})
                if isinstance(legacy_data, dict):
                    agent_summary = legacy_data.get("summary", "")

            if llm_response.get("success") and llm_response.get("content"):
                answer_body = llm_response.get("content", "")
            elif agent_summary:
                answer_body = agent_summary
            else:
                answer_body = llm_response.get("content", "")

            capability = get_capability_by_question_type(question_type)
            context_data = state.get("analysis_context")
            if capability is not None and context_data:
                analysis_context = AnalysisContext.from_dict(context_data)
                first_agent = next(iter(final_result["models"].values()), {})
                meta = first_agent.get("meta", {}) if isinstance(first_agent, dict) else {}
                provenance_input = {
                    "model_version": meta.get("model_version"),
                    "data_as_of": meta.get("data_as_of"),
                    "data_version": meta.get("data_version"),
                    "actual_inputs": first_agent.get("actual_inputs", {}),
                }
                provenance = result_provenance_builder.build(
                    trace_id=state.get("trace_id") or "unknown",
                    analysis_context=analysis_context,
                    capability=capability,
                    agent_result=provenance_input,
                    calculated_at=datetime.now(timezone.utc),
                )
                final_result["provenance"] = provenance
                final_result["answer"] = provenance["object_title"] + "\n\n" + answer_body
            else:
                final_result["answer"] = answer_body

            final_result["sources"] = []
            if not final_result["sources"] and rag_response.get("sources"):
                final_result["sources"] = rag_response.get("sources", [])

        return {**state, "model_results": final_result, "status": "completed", "error": None}
    except Exception as e:
        return {**state, "status": "failed", "error": str(e)}

def finalize(state: MultiAgentState) -> MultiAgentState:
    return state
