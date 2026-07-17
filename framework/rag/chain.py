from __future__ import annotations
import os
import sqlite3
from typing import Optional, List, Dict, Any
from framework.llm.service import llm_service
from framework.vector_store.chroma_store import vector_store
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
        for uuid_name in uuid_names:
            doc_name = name_mapping.get(uuid_name, uuid_name)
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