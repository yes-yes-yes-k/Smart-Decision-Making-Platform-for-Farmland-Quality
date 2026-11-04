from __future__ import annotations
from typing import Any, Dict
from uuid import uuid4
from flask import current_app, has_app_context
from framework.config import Config
from langgraph.graph import StateGraph
from langgraph.constants import END
from .state import MultiAgentState
from .nodes import (
    initialize_state,
    identify_question_node,
    route_models,
    analysis_requirement_node,
    route_after_requirement,
    needs_input_node,
    execute_models,
    retrieve_professional_evidence,
    llm_generate,
    build_professional_answer_prompt,
    rag_chat_node,
    boundary_pending_node,
    aggregate_results,
    finalize,
)


def _new_initial_state(request: Dict[str, Any], conversation_history: list | None) -> MultiAgentState:
    analysis_context = request.get("analysis_context") or {
        "mode": request.get("calculation_mode", "spatial"),
        "version": None if request.get("calculation_mode") == "scenario" else 0,
        "object": None,
    }
    return {
        "request": request,
        "data": {}, "model_results": {}, "llm_response": {}, "rag_response": {},
        "conversation_history": conversation_history or [],
        "status": "pending", "error": None, "question_type": None,
        "relevance": None, "routing_status": "normal", "trace_id": None,
        "analysis_context": analysis_context,
        "calculation_mode": analysis_context.get("mode", "spatial"),
        "guard_decision": {},
        "validated_identifiers": request.get("validated_identifiers", {}),
        "scenario_inputs": request.get("scenario_inputs", {}),
        "user_id": request.get("user_id"),
        "conversation_id": request.get("conversation_id"),
    }


def prepare_routed_state(
    request: Dict[str, Any], conversation_history: list | None,
) -> tuple[MultiAgentState, str]:
    state = initialize_state(_new_initial_state(request, conversation_history))
    state = identify_question_node(state)
    state = analysis_requirement_node(state)
    return state, route_after_requirement(state)

class MultiAgentOrchestrator:
    def __init__(self):
        self._graph = None
        self._app = None

    def build_graph(self) -> StateGraph:
        graph = StateGraph(MultiAgentState)

        graph.add_node("initialize", initialize_state)
        graph.add_node("identify_question", identify_question_node)
        graph.add_node("analysis_requirement", analysis_requirement_node)
        graph.add_node("needs_input", needs_input_node)
        graph.add_node("execute_models", execute_models)
        graph.add_node("retrieve_professional_evidence", retrieve_professional_evidence)
        graph.add_node("llm_generate", llm_generate)
        graph.add_node("rag_chat", rag_chat_node)
        graph.add_node("boundary_pending", boundary_pending_node)
        graph.add_node("aggregate_results", aggregate_results)
        graph.add_node("finalize", finalize)

        graph.set_entry_point("initialize")

        graph.add_edge("initialize", "identify_question")

        graph.add_edge("identify_question", "analysis_requirement")
        graph.add_conditional_edges(
            "analysis_requirement",
            route_after_requirement,
            {
                "rag_chat": "rag_chat",
                "execute_models": "execute_models",
                "boundary_pending": "boundary_pending",
                "needs_input": "needs_input",
            },
        )

        graph.add_edge("execute_models", "retrieve_professional_evidence")
        graph.add_edge("retrieve_professional_evidence", "llm_generate")
        graph.add_edge("llm_generate", "aggregate_results")
        graph.add_edge("rag_chat", "aggregate_results")
        graph.add_edge("boundary_pending", "aggregate_results")
        graph.add_edge("needs_input", "aggregate_results")
        graph.add_edge("aggregate_results", "finalize")
        graph.add_edge("finalize", END)

        return graph

    def run(self, request: Dict[str, Any], conversation_history: list = None) -> Dict[str, Any]:
        routed = self.prepare_top_level_route(request, conversation_history)
        if routed["path"] == "comprehensive":
            runtime = runtime_from_current_app()
            payload = dict(request)
            payload.setdefault("run_id", uuid4().hex)
            payload.setdefault("trace_id", uuid4().hex)
            return runtime.run_initial(payload).model_dump(mode="json")
        from framework.agents.cd_conversation import answer_cd

        cd_result = answer_cd(request, conversation_history)
        if cd_result is not None:
            return cd_result
        if self._app is None:
            self._graph = self.build_graph()
            self._app = self._graph.compile()

        initial_state = _new_initial_state(request, conversation_history)

        result = self._app.invoke(initial_state)
        trace_id = result.get("trace_id")

        if result["status"] == "completed":
            return {**result["model_results"], "trace_id": trace_id}
        else:
            return {
                "status": "error",
                "error": {
                    "code": "PROCESS_FAILED",
                    "message": result.get("error", "流程执行失败"),
                },
                "trace_id": trace_id,
            }

    def prepare_top_level_route(self, request: Dict[str, Any], history: list | None = None) -> dict[str, Any]:
        mode = comprehensive_mode_for_user(request.get("user_id"))
        message = str(request.get("question") or "")
        explicit = any(x in message for x in ("综合诊断", "综合报告", "全面诊断", "诊断与改良报告"))
        context = request.get("analysis_context") or {}
        obj = context.get("object") or {}
        eligible = context.get("mode", request.get("calculation_mode")) == "spatial" and obj.get("type") == "parcel"
        if mode == "enabled" and explicit and eligible:
            return {"path":"comprehensive","intent":{"kind":"comprehensive_analysis"},"request":request}
        return {"path":"fast","intent":{"kind":"comprehensive_analysis"} if explicit and mode=="shadow" else None,"request":request}

    def run_stream(self, request: Dict[str, Any], conversation_history: list = None):
        try:
            from framework.agents.cd_conversation import answer_cd

            cd_result = answer_cd(request, conversation_history)
            if cd_result is not None:
                yield {"type": "token", "content": cd_result["answer"]}
                yield {"type": "done", "data": cd_result}
                return
            if self._app is None:
                self._graph = self.build_graph()
                self._app = self._graph.compile()

            state, route = prepare_routed_state(request, conversation_history)
            question = state["request"].get("question", "")
            question_type = state.get("question_type", 0)

            full_answer = ""
            sources = []
            retrieval_meta = {}

            if route == "needs_input":
                state = needs_input_node(state)
                decision = state["guard_decision"]
                meta = {
                    "interaction_state": decision["interaction_state"],
                    "required_object_types": decision["required_object_types"],
                    "missing_inputs": decision["missing_inputs"],
                    "analysis_context": state["analysis_context"],
                    "trace_id": state.get("trace_id"),
                }
                yield {"type": "meta", "data": meta}
                yield {"type": "done", "data": {
                    **meta,
                    "answer": decision["message"],
                    "sources": [],
                    "model_results": state["model_results"],
                    "question_type": question_type,
                    "question": question,
                }}
                return
            if route == "rag_chat":
                # ✅ RAG 路径：使用流式检索 + 流式 LLM 生成，替代原来的阻塞式 rag_chat_node
                from framework.rag.chain import rag_chain
                for item in rag_chain.chat_stream(
                    question,
                    conversation_history=conversation_history,
                    user_id=state.get("user_id"),
                    conversation_id=state.get("conversation_id"),
                ):
                    if item["type"] == "token":
                        full_answer += item["content"]
                        yield {"type": "token", "content": item["content"]}
                    elif item["type"] == "meta":
                        sources = item.get("sources", [])
                        retrieval_meta = item.get("retrieval", {})
                        yield {"type": "meta", "data": {
                            "sources": sources, "retrieval": retrieval_meta,
                        }}
            elif route == "boundary_pending":
                state = boundary_pending_node(state)
                full_answer = state["model_results"].get("answer", "")
            else:
                # 模型路径：先执行模型（阻塞），再流式生成
                state = execute_models(state)
                state = retrieve_professional_evidence(state)
                model_results = state.get("model_results", {})
                rag_response = state.get("rag_response", {})
                retrieval_meta = (
                    rag_response.get("retrieval")
                    or rag_response.get("diagnostics")
                    or {}
                )

                # 收集 sources（复刻 aggregate_results 的逻辑）
                agent_data = model_results if isinstance(model_results, dict) else {}
                if not sources and rag_response.get("sources"):
                    sources = rag_response.get("sources", [])

                if question:
                    # 酸化状态确定性前缀：任何路径（FC/流式/非流式）都必须强制
                    # 输出权威地块快照中的实测土壤酸碱度与酸化分级，修复
                    # 「数据库存在 soil_ph 却回复缺少数据」链路断点（F1/F4）。
                    object_ctx = (state.get("analysis_context") or {}).get("object") or {}
                    parcel_id = (
                        object_ctx.get("id") if object_ctx.get("type") == "parcel" else None
                    )
                    acid_prefix = ""
                    if question_type == 4:
                        from .nodes import build_acidification_state_prefix
                        acid_prefix = build_acidification_state_prefix(
                            (agent_data.get("models") if isinstance(agent_data, dict) else None) or {},
                            parcel_id=parcel_id,
                        )
                    # function calling 已生成答复时直接使用，避免重复调 LLM
                    fc_summary = agent_data.get("answer", "") if isinstance(agent_data, dict) else ""
                    routing_method = agent_data.get("routing_method", "") if isinstance(agent_data, dict) else ""
                    if (
                        routing_method == "function_calling"
                        and fc_summary
                        and not agent_data.get("field_query")
                    ):
                        # FC 路径同样强制拼接酸化确定性前缀（LLM 自行总结时可能
                        # 忽略 tool 结果中的 soil_ph，导致误报"缺实测"）。
                        if acid_prefix:
                            full_answer = acid_prefix + "\n\n" + fc_summary
                            yield {"type": "token", "content": acid_prefix + "\n\n"}
                            yield {"type": "token", "content": fc_summary}
                        else:
                            full_answer = fc_summary
                            yield {"type": "token", "content": fc_summary}
                    else:
                        # 流式与非流式共用 build_professional_answer_prompt，
                        # 避免两处规则漂移（稳定性历史不足、酸化分级、只答所问等）。
                        from .output_contract import llm_context
                        from .parcel_field_query import prepend_field_answer
                        contexts = {
                            aid: llm_context(item)
                            for aid, item in agent_data.get("models", {}).items()
                        }
                        field_query = agent_data.get("field_query")
                        field_answer = str((field_query or {}).get("answer") or "").strip()
                        # acid_prefix/object_ctx/parcel_id 已在 `if question:` 开头统一计算
                        head = "\n\n".join(part for part in (field_answer, acid_prefix) if part)
                        if head:
                            full_answer = head + "\n\n"
                            yield {"type": "token", "content": full_answer}
                        evidence_context = str(
                            state.get("rag_response", {}).get("context") or ""
                        )
                        # 会话上下文已知前提注入：同会话同地块上一轮模型结论\n                        # （如障碍度中「土壤酸碱度 0.14」），供本轮回答引用，\n                        # 使其能区分「障碍度 ≠ 实测 pH」，消除跨轮矛盾观感。\n                        from .nodes import extract_prior_knowledge\n                        prior_knowledge = extract_prior_knowledge(\n                            conversation_history,\n                            (object_ctx or {}).get(\"id\")\n                            if (object_ctx or {}).get(\"type\") == \"parcel\" else None,\n                        )\n                        if prior_knowledge:\n                            evidence_context = (\n                                evidence_context + \"\\n\\n【上一轮已知前提】\\n\" + prior_knowledge\n                            ).strip()\n                        prompt = build_professional_answer_prompt(\n                            question=question,\n                            field_query=field_query,\n                            contexts=contexts,\n                            evidence_context=evidence_context,\n                        )
                        from framework.llm.service import llm_service
                        body = ""
                        try:
                            for chunk in llm_service.generate_stream(prompt, messages=conversation_history):
                                body += chunk
                                full_answer += chunk
                                yield {"type": "token", "content": chunk}
                        except Exception:
                            # LLM 失败时直接根据同一份规范模型结果生成答复，
                            # 不重新执行任何专业 Agent（body 保持空，走下方兜底）。
                            body = ""
                        # 空正文兜底：LLM 失败或空流（无 token），或正文含白名单外
                        # 幻觉字段名（如「耕作制度」）→ 确定性摘要拼接。
                        from .nodes import has_prohibited_field_name
                        if not body.strip() or has_prohibited_field_name(body):
                            # 酸化测算兜底优先：正文为空或不可信时，若本轮携带
                            # 权威酸化测算上下文，则解释本轮测算结果本身，而不是
                            # 拼接 Model-4 其他材料剂量或输出「暂无可用结果」。
                            from .output_contract import deterministic_answer, acid_measurement_answer
                            acid_ctx = (
                                (state.get("analysis_context") or {})
                                .get("acidification_result_context") or {}
                            )
                            if acid_ctx:
                                body = acid_measurement_answer(acid_ctx)
                            else:
                                body = "\n".join(
                                    deterministic_answer(item) for item in agent_data.get("models", {}).values()
                                ) or "暂无可用结果"
                            full_answer += body
                            yield {"type": "token", "content": body}

            # 最终结果
            done_models = {} if question_type == 0 else state.get("model_results", {}).get("models", {})
            if not full_answer and question_type != 0:
                from .output_contract import deterministic_answer, acid_measurement_answer
                acid_ctx = (
                    (state.get("analysis_context") or {})
                    .get("acidification_result_context") or {}
                )
                if acid_ctx:
                    full_answer = acid_measurement_answer(acid_ctx)
                else:
                    full_answer = "\n".join(
                        deterministic_answer(item) for item in done_models.values()
                    ) or "暂无可用结果"
            field_query = state.get("model_results", {}).get("field_query")
            yield {
                "type": "done",
                "data": {
                    "answer": full_answer,
                    "sources": sources,
                    "question_type": question_type,
                    "question": question,
                    "trace_id": state.get("trace_id"),
                    "analysis_context": state.get("analysis_context"),
                    "interaction_state": state.get("guard_decision", {}).get("interaction_state", "completed"),
                    "required_object_types": state.get("guard_decision", {}).get("required_object_types", []),
                    "models": done_models,
                    "field_query": field_query,
                    "routing": {
                        "question_type": question_type,
                        "status": state.get("routing_status", "normal"),
                    },
                    "retrieval": retrieval_meta,
                },
            }
        except Exception as e:
            yield {"type": "error", "message": str(e)}

multi_agent_orchestrator = MultiAgentOrchestrator()


def comprehensive_mode_for_user(user_id: int | None) -> str:
    mode=Config.COMPREHENSIVE_WORKFLOW_MODE
    allowed=Config.COMPREHENSIVE_ALLOWED_USER_IDS
    return "off" if mode=="enabled" and allowed and user_id not in allowed else mode


def runtime_from_current_app():
    if not has_app_context():
        from framework.agents.workflows.comprehensive.runtime import CheckpointerUnavailable
        raise CheckpointerUnavailable("application_context_required")
    runtime=current_app.extensions.get("comprehensive_runtime")
    if runtime is None:
        from framework.agents.workflows.comprehensive.runtime import CheckpointerUnavailable
        raise CheckpointerUnavailable("comprehensive_runtime_not_initialized")
    return runtime
