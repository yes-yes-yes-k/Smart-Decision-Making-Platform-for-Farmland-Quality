from __future__ import annotations
from typing import Optional, List, Dict, Any
from framework.llm.service import llm_service
from framework.vector_store.chroma_store import vector_store
from framework.config import Config

class RAGChain:
    def __init__(self):
        self.llm_service = llm_service
        self.vector_store = vector_store

    def chat(self, query: str, conversation_history: Optional[List[Dict]] = None, valid_doc_names: Optional[set] = None) -> Dict[str, Any]:
        retrieval_results = self._retrieve_documents(query, valid_doc_names)

        if retrieval_results["count"] == 0:
            llm_response = self.llm_service.generate(query, conversation_history)
            return {
                "success": llm_response.get("success", False),
                "answer": llm_response.get("content", ""),
                "sources": [],
                "model": llm_response.get("model", "fallback"),
                "notice": "本地知识库中未找到相关文档，以上回答来自模型通用知识。",
            }

        context = self._build_context(retrieval_results["results"])
        prompt = self._build_prompt(query, context)

        llm_response = self.llm_service.generate(prompt, conversation_history)

        sources = []
        for result in retrieval_results["results"]:
            metadata = result.get("metadata", {})
            doc_name = metadata.get("source", "unknown")
            if not any(s["doc_name"] == doc_name for s in sources):
                sources.append({"doc_name": doc_name})

        return {
            "success": llm_response.get("success", False),
            "answer": llm_response.get("content", ""),
            "sources": sources,
            "model": llm_response.get("model", "fallback"),
            "retrieved_count": retrieval_results["count"],
        }

    def _retrieve_documents(self, query: str, valid_doc_names: Optional[set]) -> Dict[str, Any]:
        filters = None
        if valid_doc_names:
            filters = {"source": {"$in": list(valid_doc_names)}}

        return self.vector_store.search(
            query=query,
            n_results=Config.RETRIEVAL_TOP_K,
            filters=filters,
        )

    def _build_context(self, results: List[Dict]) -> str:
        context_parts = []
        for i, result in enumerate(results):
            content = result.get("content", "")
            metadata = result.get("metadata", {})
            source = metadata.get("source", "unknown")
            context_parts.append(f"文档{i+1}({source}): {content}")
        return "\n\n".join(context_parts)

    def _build_prompt(self, query: str, context: str) -> str:
        return f"""基于以下文档内容，回答用户的问题。请优先参考本地知识库中的文档内容进行回答。

文档内容：
{context}

用户问题：
{query}

请以自然、专业的语言回答。回答时必须在引用文档内容处标注来源，格式为"根据《文档名》..."。如果文档中没有完全匹配的信息，可结合文档相关内容进行推断，但需说明推断依据。"""

rag_chain = RAGChain()