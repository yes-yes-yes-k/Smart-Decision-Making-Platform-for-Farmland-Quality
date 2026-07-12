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
            },
        )

        graph.add_edge("execute_models", "llm_generate")
        graph.add_edge("llm_generate", "aggregate_results")
        graph.add_edge("rag_chat", "aggregate_results")
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

multi_agent_orchestrator = MultiAgentOrchestrator()