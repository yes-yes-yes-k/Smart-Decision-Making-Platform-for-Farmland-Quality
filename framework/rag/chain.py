from __future__ import annotations
import os
import sqlite3
from typing import Optional, List, Dict, Any
from framework.llm.service import llm_service
from framework.vector_store.chroma_store import vector_store
from framework.rag.reranker import rerank_service
from framework.rag.synonyms import normalize_query
from framework.rag.category_router import route_category
from framework.config import Config

class RAGChain:
    def __init__(self):
        self.llm_service = llm_service
        self.vector_store = vector_store

    def _query_doc_names(self, file_paths: List[str]) -> Dict[str, str]:
        """查询 kb_document 表，构建 file_path → doc_name 映射"""
        mapping = {}
        if not file_paths:
            return mapping
        try:
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'instance', 'development.db')
            if not os.path.exists(db_path):
                return mapping
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(file_paths))
            cursor.execute(f"SELECT file_path, doc_name FROM kb_document WHERE file_path IN ({placeholders})", file_paths)
            for row in cursor.fetchall():
                mapping[row[0]] = row[1]
            conn.close()
        except Exception:
            pass
        return mapping

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

        # 收集所有 UUID 文件名，查询数据库获取中文原始名
        uuid_names = []
        for result in retrieval_results["results"]:
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "unknown")
            if source not in uuid_names:
                uuid_names.append(source)
        name_mapping = self._query_doc_names(uuid_names)

        sources = []
        for result in retrieval_results["results"]:
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "unknown")
            doc_name = name_mapping.get(source, source)
            sources.append({
                "doc_name": doc_name,
                "chunk_index": metadata.get("chunk_index"),
                "page": metadata.get("page"),
            })

        return {
            "success": llm_response.get("success", False),
            "answer": llm_response.get("content", ""),
            "sources": sources,
            "model": llm_response.get("model", "fallback"),
            "retrieved_count": retrieval_results["count"],
        }

    def chat_stream(self, query: str, conversation_history: Optional[List[Dict]] = None, valid_doc_names: Optional[set] = None):
        """流式版本的 chat：检索文档后，使用流式 LLM 生成回答，逐 token yield"""
        retrieval_results = self._retrieve_documents(query, valid_doc_names)

        if retrieval_results["count"] == 0:
            # 未找到文档，流式调用 LLM 通用知识
            for chunk in self.llm_service.generate_stream(query, conversation_history):
                yield {"type": "token", "content": chunk}
            yield {
                "type": "meta",
                "sources": [],
                "notice": "本地知识库中未找到相关文档，以上回答来自模型通用知识。",
            }
            return

        context = self._build_context(retrieval_results["results"])
        prompt = self._build_prompt(query, context)

        # 收集来源文档信息
        uuid_names = []
        for result in retrieval_results["results"]:
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "unknown")
            if source not in uuid_names:
                uuid_names.append(source)
        name_mapping = self._query_doc_names(uuid_names)

        sources = []
        for result in retrieval_results["results"]:
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "unknown")
            doc_name = name_mapping.get(source, source)
            sources.append({
                "doc_name": doc_name,
                "chunk_index": metadata.get("chunk_index"),
                "page": metadata.get("page"),
            })

        # 先发送来源元数据，前端可立即展示参考来源
        yield {"type": "meta", "sources": sources}

        # 流式 LLM 生成
        for chunk in self.llm_service.generate_stream(prompt, conversation_history):
            yield {"type": "token", "content": chunk}

    def _retrieve_documents(self, query: str, valid_doc_names: Optional[set]) -> Dict[str, Any]:
        normalized_query = normalize_query(query)
        category = route_category(normalized_query)
        filters = {"source": {"$in": list(valid_doc_names)}} if valid_doc_names else None
        recalled = self.vector_store.hybrid_search(
            query=normalized_query, n_results=Config.RECALL_TOP_K, filters=filters,
            category=category)
        results = recalled["results"]
        if Config.RERANK_ENABLED and len(results) > Config.RETRIEVAL_TOP_K:
            results = rerank_service.rerank(query, results)
        return {"results": results[:Config.RETRIEVAL_TOP_K],
                "count": len(results[:Config.RETRIEVAL_TOP_K])}

    def _build_context(self, results: List[Dict]) -> str:
        context_parts = []
        for i, result in enumerate(results):
            content = result.get("content", "")
            context_parts.append(f"文档{i+1}: {content}")
        return "\n\n".join(context_parts)

    def _build_prompt(self, query: str, context: str) -> str:
        return f"""基于以下文档内容，回答用户的问题。请优先参考本地知识库中的文档内容进行回答。

文档内容：
{context}

用户问题：
{query}

请以自然、专业的语言回答。如果文档中没有完全匹配的信息，可结合文档相关内容进行推断，但需说明推断依据。"""

rag_chain = RAGChain()