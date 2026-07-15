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
            }

        context = self._build_context(retrieval_results["results"])
        prompt = self._build_prompt(query, context)

        llm_response = self.llm_service.generate(prompt, conversation_history)

        sources = []
        for result in retrieval_results["results"]:
            metadata = result.get("metadata", {})
            sources.append({
                "doc_name": metadata.get("source", "unknown"),
                "content": result.get("content", "")[:200] + "...",
                "score": 1 - result.get("distance", 0),
            })

        return {
            "success": llm_response.get("success", False),
            "answer": llm_response.get("content", ""),
            "sources": sources,
            "model": llm_response.get("model", "fallback"),
            "retrieved_count": retrieval_results["count"],
        }

    def _retrieve_documents(self, query: str, valid_doc_names: Optional[set]) -> Dict[str, Any]:
        # 先检查向量库是否有文档，如果为空直接返回，避免触发 embedding 模型下载
        stats = self.vector_store.get_collection_stats()
        if stats.get("count", 0) == 0:
            return {"results": [], "count": 0}

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
        return f"""你是耕地质量与土壤改良领域的专家。请基于以下文档内容，回答用户关于耕地质量、土壤改良、酸化治理、有机质提升等方面的问题。

回答要求：
1. 优先使用文档中提供的信息回答
2. 如果文档中有相关信息，请准确引用并回答
3. 如果文档信息不完整，可以结合你的专业知识补充回答
4. 回答要条理清晰、专业准确
5. 如果文档中完全没有相关信息，请明确说明"根据现有文档无法找到相关信息"，然后基于你的专业知识给出参考回答

参考文档：
{context}

用户问题：
{query}

请以自然、专业的语言回答，字数适中，重点突出。"""

rag_chain = RAGChain()