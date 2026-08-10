from __future__ import annotations
from typing import Any, Dict
from langgraph.graph import StateGraph
from langgraph.constants import END
from .state import MultiAgentState
from .nodes import (
    initialize_state,
    identify_question_node,
    route_models,
    execute_models,
    llm_generate,
    rag_chat_node,
    boundary_pending_node,
    aggregate_results,
    finalize,
)

class MultiAgentOrchestrator:
    def __init__(self):
        self._graph = None
        self._app = None

    def build_graph(self) -> StateGraph:
        graph = StateGraph(MultiAgentState)

        graph.add_node("initialize", initialize_state)
        graph.add_node("identify_question", identify_question_node)
        graph.add_node("execute_models", execute_models)
        graph.add_node("llm_generate", llm_generate)
        graph.add_node("rag_chat", rag_chat_node)
        graph.add_node("boundary_pending", boundary_pending_node)
        graph.add_node("aggregate_results", aggregate_results)
        graph.add_node("finalize", finalize)

        graph.set_entry_point("initialize")

        graph.add_edge("initialize", "identify_question")

        graph.add_conditional_edges(
            "identify_question",
            route_models,
            {
                "rag_chat": "rag_chat",
                "execute_models": "execute_models",
                "boundary_pending": "boundary_pending",
            },
        )

        graph.add_edge("execute_models", "llm_generate")
        graph.add_edge("llm_generate", "aggregate_results")
        graph.add_edge("rag_chat", "aggregate_results")
        graph.add_edge("boundary_pending", "aggregate_results")
        graph.add_edge("aggregate_results", "finalize")
        graph.add_edge("finalize", END)

        return graph

    def run(self, request: Dict[str, Any], conversation_history: list = None) -> Dict[str, Any]:
        if self._app is None:
            self._graph = self.build_graph()
            self._app = self._graph.compile()

        initial_state: MultiAgentState = {
            "request": request,
            "data": {},
            "model_results": {},
            "llm_response": {},
            "rag_response": {},
            "conversation_history": conversation_history or [],
            "status": "pending",
            "error": None,
            "question_type": None,
            "relevance": None,
            "routing_status": "normal",
        }

        result = self._app.invoke(initial_state)

        if result["status"] == "completed":
            return result["model_results"]
        else:
            return {
                "status": "error",
                "error": {
                    "code": "PROCESS_FAILED",
                    "message": result.get("error", "流程执行失败"),
                },
            }

    def run_stream(self, request: Dict[str, Any], conversation_history: list = None):
        try:
            if self._app is None:
                self._graph = self.build_graph()
                self._app = self._graph.compile()

            initial_state: MultiAgentState = {
                "request": request,
                "data": {},
                "model_results": {},
                "llm_response": {},
                "rag_response": {},
                "conversation_history": conversation_history or [],
                "status": "pending",
                "error": None,
                "question_type": None,
                "relevance": None,
            }

            # 准备阶段：手动执行节点（跳过 llm_generate 和 finalize）
            state = initialize_state(initial_state)
            state = identify_question_node(state)

            route = route_models(state)
            if route == "rag_chat":
                state = rag_chat_node(state)
            else:
                state = execute_models(state)

            question = state["request"].get("question", "")
            question_type = state.get("question_type", 0)
            model_results = state.get("model_results", {})
            rag_response = state.get("rag_response", {})

            # 收集 sources（复刻 aggregate_results 的逻辑）
            sources = []
            if question_type == 0:
                sources = rag_response.get("sources", [])
            else:
                agent_data = model_results.get("data", {}) if isinstance(model_results, dict) else {}
                agent_details = agent_data.get("details", {}) if isinstance(agent_data, dict) else {}
                if isinstance(agent_details, dict):
                    for _agent_id, detail in agent_details.items():
                        if isinstance(detail, dict):
                            detail_sources = detail.get("sources", [])
                            if detail_sources:
                                sources.extend(detail_sources)
                            evidence = detail.get("evidence", [])
                            if evidence and not detail_sources:
                                for ev in evidence:
                                    if isinstance(ev, dict) and ev.get("doc_name"):
                                        sources.append(ev)
                if not sources and rag_response.get("sources"):
                    sources = rag_response.get("sources", [])

            # 生成阶段
            full_answer = ""

            if question_type in [1, 2, 3, 4, 5, 6, 7] and question:
                # 复刻 llm_generate 节点的 prompt 构造逻辑
                prompt = (
                    "你是耕地质量与土壤改良领域的助手。请基于专业智能体结果，"
                    "整合成一份准确、简洁、可执行的中文答复。不要编造未提供的数据，"
                    "保留明确的数值、单位和建议。\n"
                    f"用户问题：{question}\n"
                    f"专业智能体结果：{model_results}"
                )
                from framework.llm.service import llm_service
                for chunk in llm_service.generate_stream(prompt, messages=conversation_history):
                    full_answer += chunk
                    yield {"type": "token", "content": chunk}
            elif question_type == 0:
                # 知识性问题：RAG 已给出答案，直接输出
                full_answer = rag_response.get("answer", "")
                if full_answer:
                    yield {"type": "token", "content": full_answer}

            # 最终结果
            done_model_results = {} if question_type == 0 else model_results
            yield {
                "type": "done",
                "data": {
                    "answer": full_answer,
                    "sources": sources,
                    "model_results": done_model_results,
                    "question_type": question_type,
                    "question": question,
                },
            }
        except Exception as e:
            yield {"type": "error", "message": str(e)}

multi_agent_orchestrator = MultiAgentOrchestrator()