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
    if question_type == 0 and _has_scoped_parcel_field_query(state):
        return "execute_models"
    if question_type == 0:
        return "rag_chat"
    return "execute_models"


def _has_scoped_parcel_field_query(state: MultiAgentState) -> bool:
    """Keep explicit selected-parcel lookups out of the generic RAG path."""
    from .parcel_field_query import requested_metadata_fields, requested_parcel_fields

    request = state.get("request", {})
    question = str(request.get("question") or "")
    context = state.get("analysis_context") or {}
    analysis_object = context.get("object") or {}
    has_parcel = bool(
        request.get("parcel_id")
        or request.get("parcel_code")
        or (analysis_object.get("type") == "parcel" and analysis_object.get("id"))
    )
    return has_parcel and bool(
        requested_parcel_fields(question) or requested_metadata_fields(question)
    )


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
    if state.get("question_type") == 0 and _has_scoped_parcel_field_query(state):
        return "execute_models"
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
            get_specialized_tools_for,
            TOOL_NAME_TO_AGENT_ID,
        )
        from framework.llm.service import llm_service

        tools = get_specialized_tools()
        # 按 1:1 路由约束 tool 白名单：只暴露 question_type 对应的单一模型，
        # 避免 LLM 为单一提问额外调用无关模型（如问酸化却同时诊断障碍），产生与提问无关的内容。
        question_type = context.get("question_type")
        if question_type:
            from framework.agents.router import TYPE_AGENTS
            agent_ids = TYPE_AGENTS.get(question_type, [])
            if agent_ids:
                try:
                    tools = list(get_specialized_tools_for(set(agent_ids)).values())
                except ValueError:
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
        from framework.agents.parcel_field_query import (
            prepend_field_answer,
            query_requested_parcel_fields,
            requested_parcel_fields,
        )
        from framework.agents.router import TYPE_AGENTS

        question = state["request"].get("question", "")
        context = _build_verified_execution_context(state)
        field_query = query_requested_parcel_fields(
            question, context.get("parcel_id"),
        )
        print(f"[execute_models] context: parcel_id={context.get('parcel_id')}, "
              f"parcel_code={context.get('parcel_code')}, "
              f"question_type={context.get('question_type')}, "
              f"area_code={context.get('area_code')}")
        # 透传 question_type 到 context（agent 可能需要）
        if "question_type" in state:
            context["question_type"] = state["question_type"]

        # 字段联动：直查命中的字段由哪个模型负责（如"质量等级"归 model-2），
        # 就把该模型追加进本轮执行名单。避免"质量等级稳不稳"这种问题因为
        # 只路由到 model-1，导致质量等级/综合指数被误报"暂无可发布的已验证模型结果"。
        required_agent_ids = {
            f.model_agent_id
            for f in requested_parcel_fields(question)
            if getattr(f, "source_kind", None) == "model" and f.model_agent_id
        }
        extra_agent_ids = sorted(
            required_agent_ids - set(TYPE_AGENTS.get(state.get("question_type"), []))
        )
        if extra_agent_ids:
            context["extra_agent_ids"] = extra_agent_ids
            print(f"[execute_models] 字段联动追加模型: {extra_agent_ids}")

        # 优先尝试 function calling 路径（FC 白名单只暴露单一模型；
        # 需要联动执行额外模型时跳过 FC，走 Manager 关键词路径以保证全部执行）
        trace_id = state.get("trace_id")
        fc_result = (
            None
            if extra_agent_ids
            else _execute_via_function_calling(question, context, trace_id)
        )
        if fc_result is not None:
            refreshed_field_query = query_requested_parcel_fields(
                question, context.get("parcel_id"), professional_results=fc_result,
            )
            if refreshed_field_query is not None:
                fc_result["field_query"] = refreshed_field_query
                fc_result["answer"] = prepend_field_answer(
                    refreshed_field_query, fc_result.get("answer"),
                )
            return {
                **state,
                "model_results": fc_result,
                "status": "model_completed",
                "error": None,
            }

        # fallback: 原有关键词路由路径
        result = agent_manager.process(question, context)
        refreshed_field_query = query_requested_parcel_fields(
            question, context.get("parcel_id"), professional_results=result,
        )
        if refreshed_field_query is not None:
            result["field_query"] = refreshed_field_query
            result["answer"] = prepend_field_answer(
                refreshed_field_query, result.get("answer"),
            )
        return {
            **state,
            "model_results": result,
            "status": "model_completed",
            "error": None,
        }
    except Exception as exc:
        question_type = state.get("question_type")
        from framework.agents.parcel_field_query import prepend_field_answer
        fallback_answer = "专业能力执行失败，未调用其他专业模型。"
        fallback_answer = prepend_field_answer(
            locals().get("field_query"), fallback_answer,
        )
        fallback_result = {
            "status": "error",
            "question_type": question_type,
            "models": {},
            "answer": fallback_answer,
            "recommendations": [],
            "routing_method": "keyword_fallback",
        }
        if locals().get("field_query") is not None:
            fallback_result["field_query"] = field_query
        return {
            **state,
            "model_results": fallback_result,
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

def build_acidification_state_prefix(
    models: Dict[str, Any],
    parcel_id: Optional[str] = None,
) -> str:
    """Model-4 酸化状态的确定性前缀。

    修复「数据库存在实测 soil_ph 却回复缺少数据」的断点：即使 model-4 envelope
    中 soil_ph 在链路中丢失，也从地块权威快照兜底读取；有实测则输出 pH 与酸性
    分级结论，无实测则给出明确补测引导（而非笼统"无法判断"）。
    """
    import math
    from collections.abc import Mapping
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    soil_ph = None
    envelope = (models or {}).get("model-4")
    if isinstance(envelope, Mapping):
        result = envelope.get("result") if isinstance(envelope.get("result"), Mapping) else {}
        soil_ph = result.get("soil_ph")
    # 兜底：从地块权威快照读取实测 soil_ph（与字段直查同源，修复链路丢字段）
    if soil_ph is None and parcel_id:
        try:
            snapshot = ParcelDataAccessor().get_parcel_snapshot(str(parcel_id))
            if snapshot is not None:
                soil_ph = snapshot.indicators.get("soil_ph")
        except Exception:
            pass
    if soil_ph is None or isinstance(soil_ph, bool):
        return (
            "该地块缺少实测土壤酸碱度（pH）记录，暂无法判定酸化严重程度。"
            "分级阈值：强酸性 <5.5、酸性 5.5~6.5、中性及以上 ≥6.5；"
            "建议补测土壤 pH 后重新评估。"
        )
    try:
        ph = float(soil_ph)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(ph):
        return ""
    from framework.domain.statistics.indicator_definitions import classify_indicator

    bucket = classify_indicator("soil_ph", ph)
    level = bucket.label if bucket is not None else "未知"
    if ph < 5.5:
        verdict = "属强酸性，酸化情况较严重，需重点关注"
    elif ph < 6.5:
        verdict = "属酸性，尚未达强酸性，需留意"
    else:
        verdict = "非酸性，酸化情况不严重"
    return (
        f"土壤酸碱度（pH）为 {ph:.2f}，酸化分级为「{level}」。"
        f"按分级阈值（强酸性 <5.5、酸性 5.5~6.5）判定：{verdict}。"
    )


#: LLM 总结中禁止出现的幻觉字段名（模型结果中不存在，见修复提案 F6）。
#: 命中即判定该段正文不可信，回退确定性模板，防止「耕层质地」被改写成
#: 「耕作制度」这类字段名幻觉污染最终回答。
PROHIBITED_FIELD_NAMES = ("耕作制度",)


def has_prohibited_field_name(text: str) -> bool:
    """正文中是否出现白名单外幻觉字段名。"""
    return bool(text) and any(name in text for name in PROHIBITED_FIELD_NAMES)


def extract_prior_knowledge(
    conversation_history: Optional[list],
    parcel_id: Optional[str],
) -> str:
    """从同会话历史中提取上一轮模型结论作为「已知前提」（仅同地块注入）。

    用于「障碍度排序」等上一轮结论，供本轮酸化等问题引用（如障碍度中的
    「土壤酸碱度 0.14」），让回答能区分「障碍度 ≠ 实测 pH」。
    """
    if not conversation_history or not parcel_id:
        return ""
    last_assistant = ""
    for msg in reversed(list(conversation_history)):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            last_assistant = str(msg.get("content") or "")
            break
    if not last_assistant:
        return ""
    if f"地块 {parcel_id}" not in last_assistant:
        return ""
    lines = [
        line.strip()
        for line in last_assistant.splitlines()
        if line.strip() and any(ch.isdigit() for ch in line)
    ]
    return "\n".join(lines[:6])


def build_professional_answer_prompt(
    *,
    question: str,
    field_query,
    contexts: Dict[str, str],
    evidence_context: str,
) -> str:
    """构造专业模型结果的最终总结提示词。

    流式与非流式出口共用同一份提示词，避免两处规则漂移。
    """
    return (
        "你是耕地质量与土壤改良领域的助手。请基于专业智能体结果，"
        "整合成一份准确、简洁、可执行的中文答复。\n"
        "通用要求：\n"
        "- 【只答所问】严格围绕用户问题作答，只回答用户实际询问的内容；用户未问到的结论、建议、用量方案、"
        "补充参数请求、后续测算提议、其它模型的推荐，以及衍生风险或扩展解释，一律不得输出。\n"
        "- 不得编造未提供的数据，保留明确的数值和单位；没有配置单位的指标只展示数值，不提示单位缺失，也不得臆造单位。\n"
        "- 必须使用中文标准字段名称，不得展示 GGNL、DXBW、SXJ 等模型内部字段缩写；"
        "不得把 dose_prediction 改写成“有机质提升用量预测值”等自造名称。\n"
        "- 字段白名单：只能使用「专业模型紧凑结果」中实际存在的标准字段名，"
        "不得新增或改写字段名（如不得把「耕层质地」写成「耕作制度」）；"
        "若结果未提供某字段则不得以任何名称输出该类字段。\n"
        "- 若上下文提供 labels/units，必须使用其中的标准名称和单位。\n"
        "- 综合指数保留两位小数；耕地质量等级必须是 1~10 的整数（如 7 级，不得写成 7.00 级）；"
        "有机肥建议施用量取整到最近的 10 公斤/亩，并在数值前加“约”。\n"
        "- 不得输出 potential_increase 等未在结果中提供的字段。\n"
        "- 知识图谱证据只能解释专业模型结果，不得覆盖模型实际计算值；若证据不足，应省略扩展解释。\n"
        "- 指标分类角色与指标获取方式是独立维度。\n"
        "- 如有地块字段直查结果，该实际值已经由系统展示；不得否定或声称缺失，也不要重复该句。\n"
        "- 术语解释随正文就地给出"
        "不得单独输出“术语说明”段落。\n"
        "- 不得输出数据来源、模型版本、计算时间等元信息。\n"
        "回答结构与内容要求：\n"
        "1. 当用户同时询问现状与改善（例如“等级如何，怎么改善”）时，输出两节：\n"
        "“一、等级结论”：先写“耕地质量等级：X 级（整数，并说明数字越小质量越好）”，"
        "再写“耕地质量综合指数：X.XX（范围0~1，越接近 1 越好）”；"
        "等级解释必须紧跟等级数值，不得放到综合指数之后；若上下文提供等级临界说明，必须原样附上。\n"
        "“二、改善建议”：必须先逐项列出主要障碍因素和次要障碍因素的具体名称，"
        "不得只写“多障碍”或以“多障碍”代替因素名称；再按优先级逐条给出可执行措施（至少 3 条），"
        "每条措施对应一个障碍因素，措施只能来自上下文或知识库证据，不得编造用量；"
        "若上下文明确提供目标等级或复评时间则写出，未提供时直接省略，不得写“未提供”“本次结果未提供”。\n"
        "结尾给出 2~3 个可继续追问的问题。\n"
        "2. 当用户只询问当前土壤状态和酸化预测结果含义时，只输出两节：\n"
        "“一、当前土壤状态”：只列本次提供的地块实测指标（名称、数值、单位），"
        "不得写入预测值或风险等级；\n"
        "“二、预测结果含义”：用一句话说明预测值表示“pH 相对当前水平预计下降的幅度”，"
        "不得用多个等价说法反复解释同一含义；"
        "酸化预测本身不涉及目标 pH，不得输出目标土壤酸碱度或调酸用量；"
        "不得输出治理建议、用量方案、监测要求、参考文献或数据来源说明，"
        "也不要补充铝毒害、氮素失衡等未被问到的衍生风险。\n"
        "3. 只有当用户明确询问治理、改良、用量或措施时，才输出对应的建议。\n"
        "专项规则：\n"
        "- 主要障碍因素、次要障碍因素必须逐项列出；障碍类型只是分类标签，不能替代因素名称。\n"
        "- 障碍度排序：若上下文提供各障碍因子具体障碍度数值（obstacle_degrees），用户询问障碍度排序时"
        "必须逐项给出因子名称与数值，不得省略数值；若上下文未提供具体数值，"
        "必须明确说明「本次仅提供障碍因子排序，未提供各障碍因子的具体障碍度数值」，不得编造数值。\n"
        "- 有机肥：若上下文含 dose_confidence 且低于 0.6，或含 dose_warning，"
        "必须写成“约 N 公斤/亩（模型可信度偏低，仅供参考，实际用量需田间试验核定）”；"
        "若存在 imputed_features 或 imputed_inputs，在同一句末用括号简要说明“部分输入为模型回填”。\n"
        "- 酸化改良：若上下文提供了实测土壤 pH（soil_ph）与酸化程度（acidification_level），"
        "必须先报告实测 pH 值及其酸性分级，不得写“酸化程度未给出”；"
        "土地利用类型（land_type）已由地块档案确定，即使未在“模型回填输入”中列出也不得向用户追问，"
        "仅可针对“模型回填输入”实际列出的字段（如目标 pH、肥料类型）请求补充；"
        "若用户仅询问酸化严重程度（如“严重吗/什么程度/多少级/严不严重”），未询问治理、用量或改良措施，"
        "则报告 pH 值与酸性分级，并用一句话直接回答严重程度：按分级阈值（强酸性<5.5、酸性5.5~6.5）明确是"
        "“酸性，未达强酸性”还是“强酸性”；若数值距相邻档位阈值不足 0.1，须提示“接近临界，需留意”；"
        "不得输出调理剂/木本泥炭用量、补充参数请求或培肥建议；"
        "若用户询问治理/用量/改良措施，且模型用量字段为空，"
        "只用一句话说明原因与所需补充项（目标 pH 建议 6.0~6.5、肥料类型为复合肥/尿素），暂不测算用量；"
        "不得把“结论不可用”写成建议结论，不得使用“不宜据此制定用量”等免责式表述。\n"
        "- 稳定性/退化风险：若模型结果 modules 中历史相关模块（module_5 历史变化趋势、module_6 掉级风险、"
        "module_7 关键因子退化、module_9 持续低质）标记 reason=insufficient_history 或数值为空，"
        "必须明确告知用户「因缺少该地块至少 2 期历史等级快照，暂无法判断稳定性与退化风险高低」，"
        "并说明需补充历史等级记录后重新评估；不得含糊写成「无有效结果」或「不能判定」。\n"
        "若历史模块（module_5 历史变化趋势、module_6 掉级风险等）已有数值（历史快照充足），"
        "则必须基于这些数值给出稳定性与退化风险结论（等级趋势、是否有掉级风险），"
        "不得仍复述「缺少历史快照/无法判断」。\n"
        f"用户问题：{question}\n"
        f"地块字段直查结果：{field_query or '无'}\n"
        f"专业模型紧凑结果：{contexts}\n"
        f"经权限过滤的知识图谱/知识库证据：{evidence_context or '无'}"
    )


def llm_generate(state: MultiAgentState) -> MultiAgentState:
    model_results = state.get("model_results", {})
    if (
        model_results.get("routing_method") == "function_calling"
        and model_results.get("answer")
        and not model_results.get("field_query")
    ):
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
        field_query = model_results.get("field_query")
        evidence_context = str(state.get("rag_response", {}).get("context") or "")
        prompt = build_professional_answer_prompt(
            question=question,
            field_query=field_query,
            contexts=contexts,
            evidence_context=evidence_context,
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
        elif question_type == 0 and not (
            isinstance(model_results, dict) and model_results.get("field_query")
        ):
            final_result["answer"] = rag_response.get("answer", "")
            final_result["sources"] = rag_response.get("sources", [])
            final_result["models"] = {}
            final_result["llm_response"] = ""
        else:
            final_result["models"] = model_results.get("models", {}) if isinstance(model_results, dict) else {}
            if isinstance(model_results, dict) and model_results.get("field_query"):
                final_result["field_query"] = model_results["field_query"]
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

            if isinstance(model_results, dict):
                from .parcel_field_query import prepend_field_answer
                answer_body = prepend_field_answer(
                    model_results.get("field_query"), answer_body,
                )

            # 正文兜底：LLM 与 agent 摘要为空，或正文含白名单外幻觉字段名时，
            # 用确定性模型摘要补齐正文，满足「最终回答正文非空」契约。
            if (
                not str(answer_body or "").strip()
                or has_prohibited_field_name(str(answer_body))
            ):
                from .output_contract import deterministic_answer
                body_only = "\n".join(
                    deterministic_answer(item)
                    for item in final_result.get("models", {}).values()
                ) or "暂无可用结果"
                answer_body = ("\n\n" + body_only) if answer_body else body_only

            # 酸化状态确定性前缀：Model-4 有实测 pH 必须报告分级，修复
            # 「数据库存在 soil_ph 却回复缺少数据」链路断点。
            if question_type == 4:
                object_ctx = (state.get("analysis_context") or {}).get("object") or {}
                parcel_id = (
                    object_ctx.get("id") if object_ctx.get("type") == "parcel" else None
                )
                acid_prefix = build_acidification_state_prefix(
                    final_result.get("models", {}), parcel_id=parcel_id,
                )
                if acid_prefix:
                    answer_body = acid_prefix + "\n\n" + answer_body

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
