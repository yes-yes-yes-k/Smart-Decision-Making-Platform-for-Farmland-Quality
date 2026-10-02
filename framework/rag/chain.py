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
from framework.knowledge.taxonomy import DOMAIN_CODES

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
            from flask import has_app_context
            if has_app_context():
                from sqlalchemy import or_
                from framework.models.document import Document
                rows = Document.query.filter(or_(
                    Document.file_path.in_(file_paths),
                    Document.doc_name.in_(file_paths),
                )).all()
                for row in rows:
                    mapping[row.file_path] = row.doc_name
                    mapping[row.doc_name] = row.doc_name
                return mapping
        except Exception:
            pass
        try:
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'instance', 'development.db')
            if not os.path.exists(db_path):
                return mapping
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(file_paths))
            cursor.execute(
                f"SELECT file_path, doc_name FROM kb_document "
                f"WHERE file_path IN ({placeholders}) OR doc_name IN ({placeholders})",
                file_paths + file_paths,
            )
            for row in cursor.fetchall():
                mapping[row[0]] = row[1]
                mapping[row[1]] = row[1]
            conn.close()
        except Exception:
            pass
        return mapping

    def chat(
        self, query: str, conversation_history: Optional[List[Dict]] = None,
        valid_doc_names: Optional[set] = None, user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        retrieval_results = self._retrieve_documents(
            query, valid_doc_names, user_id=user_id,
        )

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
            doc_name = metadata.get("doc_name") or name_mapping.get(source, source)
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

    def search_documents(
        self, query: str, *, valid_doc_names: Optional[set] = None,
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return raw local retrieval results; never invoke an LLM fallback."""
        return list(self._retrieve_documents(
            query, valid_doc_names, user_id=user_id,
        )["results"])

    def chat_stream(
        self, query: str, conversation_history: Optional[List[Dict]] = None,
        valid_doc_names: Optional[set] = None, user_id: Optional[int] = None,
    ):
        """流式版本的 chat：检索文档后，使用流式 LLM 生成回答，逐 token yield"""
        retrieval_results = self._retrieve_documents(
            query, valid_doc_names, user_id=user_id,
        )

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
            doc_name = metadata.get("doc_name") or name_mapping.get(source, source)
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

    @staticmethod
    def _build_filters(
        valid_doc_names: Optional[set], user_id: Optional[int],
        domain_code: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        clauses: List[Dict[str, Any]] = []
        if user_id is not None:
            clauses.append({"$or": [
                {"visibility_scope": "public"},
                {"owner_id": int(user_id)},
            ]})
        else:
            clauses.append({"visibility_scope": "public"})
        if domain_code in DOMAIN_CODES:
            clauses.append({f"domain_{domain_code}": True})
        if valid_doc_names:
            clauses.append({"source": {"$in": sorted(valid_doc_names)}})
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def _retrieve_documents(
        self, query: str, valid_doc_names: Optional[set], *,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        normalized_query = normalize_query(query)
        category = route_category(normalized_query)
        filters = self._build_filters(valid_doc_names, user_id, category)
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
