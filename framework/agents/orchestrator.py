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
    llm_generate,
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

        graph.add_edge("execute_models", "llm_generate")
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
            if self._app is None:
                self._graph = self.build_graph()
                self._app = self._graph.compile()

            state, route = prepare_routed_state(request, conversation_history)
            question = state["request"].get("question", "")
            question_type = state.get("question_type", 0)

            full_answer = ""
            sources = []

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
                for item in rag_chain.chat_stream(question, conversation_history=conversation_history):
                    if item["type"] == "token":
                        full_answer += item["content"]
                        yield {"type": "token", "content": item["content"]}
                    elif item["type"] == "meta":
                        sources = item.get("sources", [])
                        yield {"type": "meta", "data": {"sources": sources}}
            elif route == "boundary_pending":
                state = boundary_pending_node(state)
                full_answer = state["model_results"]["data"]["summary"]
            else:
                # 模型路径：先执行模型（阻塞），再流式生成
                state = execute_models(state)
                model_results = state.get("model_results", {})
                rag_response = state.get("rag_response", {})

                # 收集 sources（复刻 aggregate_results 的逻辑）
                agent_data = model_results if isinstance(model_results, dict) else {}
                if not sources and rag_response.get("sources"):
                    sources = rag_response.get("sources", [])

                if question:
                    # function calling 已生成答复时直接使用，避免重复调 LLM
                    fc_summary = agent_data.get("answer", "") if isinstance(agent_data, dict) else ""
                    routing_method = agent_data.get("routing_method", "") if isinstance(agent_data, dict) else ""
                    if routing_method == "function_calling" and fc_summary:
                        full_answer = fc_summary
                        yield {"type": "token", "content": fc_summary}
                    else:
                        # 复刻 llm_generate 节点的 prompt 构造逻辑
                        # 提取关键模型结果摘要，便于排查
                        from .output_contract import llm_context
                        contexts = {
                            aid: llm_context(item)
                            for aid, item in agent_data.get("models", {}).items()
                        }
                        prompt = (
                            "你是耕地质量与土壤改良领域的助手。请基于专业智能体结果，"
                            "整合成一份准确、简洁、可执行的中文答复。不要编造未提供的数据，"
                            "保留明确的数值、单位和建议。回复中必须使用中文标准字段名称，"
                            "不得向用户展示 GGNL、DXBW、SXJ 等模型内部字段缩写。\n"
                            f"用户问题：{question}\n"
                            f"专业模型紧凑结果：{contexts}"
                        )
                        from framework.llm.service import llm_service
                        try:
                            for chunk in llm_service.generate_stream(prompt, messages=conversation_history):
                                full_answer += chunk
                                yield {"type": "token", "content": chunk}
                        except Exception:
                            # LLM 失败时直接根据同一份规范模型结果生成答复，
                            # 不重新执行任何专业 Agent。
                            from .output_contract import deterministic_answer
                            full_answer = "\n".join(
                                deterministic_answer(item) for item in agent_data.get("models", {}).values()
                            ) or "暂无可用结果"
                            yield {"type": "token", "content": full_answer}

            # 最终结果
            done_models = {} if question_type == 0 else state.get("model_results", {}).get("models", {})
            if not full_answer and question_type != 0:
                from .output_contract import deterministic_answer
                full_answer = "\n".join(
                    deterministic_answer(item) for item in done_models.values()
                ) or "暂无可用结果"
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
                    "routing": {
                        "question_type": question_type,
                        "status": state.get("routing_status", "normal"),
                    },
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
