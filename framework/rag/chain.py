from __future__ import annotations
import os
import sqlite3
import time
from typing import Optional, List, Dict, Any
from framework.llm.service import llm_service
from framework.vector_store.chroma_store import vector_store
from framework.rag.reranker import rerank_service
from framework.rag.synonyms import normalize_query
from framework.rag.category_router import route_category
from framework.rag.knowledge_graph_retriever import KnowledgeGraphRetriever
from framework.config import Config
from framework.knowledge.taxonomy import DOMAIN_CODES
from framework.rag.kg_runtime import (
    kg_metrics, rewrite_query_for_retrieval, rollout_decision,
)

class RAGChain:
    def __init__(self):
        self.llm_service = llm_service
        self.vector_store = vector_store
        self.kg_retriever = KnowledgeGraphRetriever(
            Config.KG_GRAPH_PATH, enabled=Config.KG_RETRIEVAL_ENABLED,
            manifest_path=Config.KG_MANIFEST_PATH,
            expected_sha256=Config.KG_EXPECTED_SHA256,
        )

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
        conversation_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        retrieval_kwargs: Dict[str, Any] = {"user_id": user_id}
        if conversation_id is not None:
            retrieval_kwargs["conversation_id"] = conversation_id
        if conversation_history:
            retrieval_kwargs["conversation_history"] = conversation_history
        retrieval_results = self._retrieve_documents(
            query, valid_doc_names, **retrieval_kwargs,
        )

        if retrieval_results["count"] == 0:
            if Config.KG_FAIL_CLOSED_AUTHORITATIVE and self._is_authoritative_query(query):
                return {
                    "success": True,
                    "answer": "当前已核验知识库中没有找到足以支持该结论的证据，暂不作权威判断。请补充适用地区、标准名称或指标名称后再查询。",
                    "sources": [],
                    "model": "knowledge_base_abstention",
                    "notice": "权威类问题无可核验证据，系统已停止通用模型自由回答。",
                    "retrieval": retrieval_results.get("diagnostics", {}),
                }
            llm_response = self.llm_service.generate(query, conversation_history)
            return {
                "success": llm_response.get("success", False),
                "answer": llm_response.get("content", ""),
                "sources": [],
                "model": llm_response.get("model", "fallback"),
                "notice": "本地知识库中未找到相关文档，以上回答来自模型通用知识。",
                "retrieval": retrieval_results.get("diagnostics", {}),
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

        sources = self._build_sources(retrieval_results["results"], name_mapping)

        return {
            "success": llm_response.get("success", False),
            "answer": llm_response.get("content", ""),
            "sources": sources,
            "model": llm_response.get("model", "fallback"),
            "retrieved_count": retrieval_results["count"],
            "retrieval": retrieval_results.get("diagnostics", {}),
        }

    def search_documents(
        self, query: str, *, valid_doc_names: Optional[set] = None,
        user_id: Optional[int] = None, conversation_id: Optional[int] = None,
        conversation_history: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        """Return raw local retrieval results; never invoke an LLM fallback."""
        return list(self._retrieve_documents(
            query, valid_doc_names, user_id=user_id,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
        )["results"])

    def retrieve_evidence_bundle(
        self, query: str, *, user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
        conversation_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Shared, permission-safe evidence tool for professional agents."""
        retrieved = self._retrieve_documents(
            query, None, user_id=user_id, conversation_id=conversation_id,
            conversation_history=conversation_history,
        )
        file_paths = [
            (row.get("metadata") or {}).get("source", "unknown")
            for row in retrieved["results"]
        ]
        mapping = self._query_doc_names(file_paths)
        return {
            "context": self._build_context(retrieved["results"]),
            "sources": self._build_sources(retrieved["results"], mapping),
            "retrieved_count": retrieved["count"],
            "diagnostics": retrieved.get("diagnostics", {}),
        }

    def chat_stream(
        self, query: str, conversation_history: Optional[List[Dict]] = None,
        valid_doc_names: Optional[set] = None, user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ):
        """流式版本的 chat：检索文档后，使用流式 LLM 生成回答，逐 token yield"""
        retrieval_kwargs: Dict[str, Any] = {"user_id": user_id}
        if conversation_id is not None:
            retrieval_kwargs["conversation_id"] = conversation_id
        if conversation_history:
            retrieval_kwargs["conversation_history"] = conversation_history
        retrieval_results = self._retrieve_documents(
            query, valid_doc_names, **retrieval_kwargs,
        )

        if retrieval_results["count"] == 0:
            if Config.KG_FAIL_CLOSED_AUTHORITATIVE and self._is_authoritative_query(query):
                yield {
                    "type": "token",
                    "content": "当前已核验知识库中没有找到足以支持该结论的证据，暂不作权威判断。请补充适用地区、标准名称或指标名称后再查询。",
                }
                yield {
                    "type": "meta", "sources": [],
                    "retrieval": retrieval_results.get("diagnostics", {}),
                    "notice": "权威类问题无可核验证据，系统已停止通用模型自由回答。",
                }
                return
            # 未找到文档，流式调用 LLM 通用知识
            for chunk in self.llm_service.generate_stream(query, conversation_history):
                yield {"type": "token", "content": chunk}
            yield {
                "type": "meta",
                "sources": [],
                "notice": "本地知识库中未找到相关文档，以上回答来自模型通用知识。",
                "retrieval": retrieval_results.get("diagnostics", {}),
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

        sources = self._build_sources(retrieval_results["results"], name_mapping)

        # 先发送来源元数据，前端可立即展示参考来源
        yield {
            "type": "meta", "sources": sources,
            "retrieval": retrieval_results.get("diagnostics", {}),
        }

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
        user_id: Optional[int] = None, conversation_id: Optional[int] = None,
        conversation_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        retrieval_query = rewrite_query_for_retrieval(query, conversation_history)
        normalized_query = normalize_query(retrieval_query)
        category = route_category(normalized_query)
        filters = self._build_filters(valid_doc_names, user_id, category)
        recalled = self.vector_store.hybrid_search(
            query=normalized_query, n_results=Config.RECALL_TOP_K, filters=filters,
            category=category)
        results = recalled["results"]
        if Config.RERANK_ENABLED and len(results) > Config.RETRIEVAL_TOP_K:
            results = rerank_service.rerank(retrieval_query, results)
        decision = rollout_decision(
            mode=Config.KG_ROLLOUT_MODE,
            user_id=user_id, conversation_id=conversation_id, query=query,
            canary_percent=Config.KG_CANARY_PERCENT,
            canary_user_ids=Config.KG_CANARY_USER_IDS,
        )
        kg_retriever = getattr(self, "kg_retriever", None)
        if kg_retriever is None:
            kg_retriever = KnowledgeGraphRetriever(
                Config.KG_GRAPH_PATH, enabled=Config.KG_RETRIEVAL_ENABLED,
                manifest_path=Config.KG_MANIFEST_PATH,
                expected_sha256=Config.KG_EXPECTED_SHA256,
            )
        graph_bundle = {"results": [], "claim_assessment": None, "matched": False}
        if Config.KG_RETRIEVAL_ENABLED and decision["mode"] != "off":
            graph_bundle = kg_retriever.retrieve(
            # The synonym normalizer intentionally broadens vector recall, but
            # it may collapse distinct graph entities (for example “有效土层厚度”
            # and “耕层厚度” into “土层厚度”).  Keep the original wording for
            # ontology matching so the reviewed relation remains unambiguous.
            query,
            vector_store=self.vector_store,
            filters=filters,
            category=category,
            top_k=min(Config.KG_RETRIEVAL_TOP_K, Config.RETRIEVAL_TOP_K),
            )
        vector_results = list(results)
        if decision["active"]:
            results = kg_retriever.merge(
                graph_bundle["results"], results,
                top_k=Config.RETRIEVAL_TOP_K,
            )
        else:
            results = results[:Config.RETRIEVAL_TOP_K]
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        def _result_key(row: Dict[str, Any]) -> tuple:
            metadata = row.get("metadata") or {}
            return (
                metadata.get("document_id"), metadata.get("page"),
                metadata.get("chunk_index"), row.get("content"),
            )
        vector_keys = {_result_key(row) for row in vector_results}
        graph_keys = {_result_key(row) for row in graph_bundle.get("results") or []}
        health_fn = getattr(kg_retriever, "health", None)
        graph_health = health_fn() if callable(health_fn) else {}
        diagnostics = {
            **decision,
            "graph_schema_version": (graph_health.get("schema_version") if Config.KG_RETRIEVAL_ENABLED else None),
            "query_rewritten": retrieval_query != query,
            "matched": bool(graph_bundle.get("matched")),
            "graph_result_count": len(graph_bundle.get("results") or []),
            "vector_result_count": len(vector_results),
            "graph_vector_overlap_count": len(graph_keys & vector_keys),
            "graph_relation_ids": list(dict.fromkeys(
                relation_id
                for row in graph_bundle.get("results") or []
                for relation_id in ((row.get("metadata") or {}).get("relation_ids") or [])
                if relation_id
            )),
            "latency_ms": latency_ms,
        }
        kg_metrics.record(diagnostics)
        return {"results": results, "count": len(results), "diagnostics": diagnostics}

    def _build_context(self, results: List[Dict]) -> str:
        context_parts = []
        claim_notice = None
        for i, result in enumerate(results):
            content = result.get("content", "")
            metadata = result.get("metadata") or {}
            relation = ""
            if str(metadata.get("retrieval_source") or "").startswith("knowledge_graph_"):
                relation_label = metadata.get("relation_label") or metadata.get("relation_type")
                relation = (
                    f"（已核验图谱关系：{metadata.get('source_entity')} "
                    f"--{relation_label}--> "
                    f"{metadata.get('target_entity')}）"
                )
            if metadata.get("graph_claim_status") == "unsupported":
                claim_notice = (
                    "图谱约束：当前已核验语料不支持问题中所述实体关系。"
                    "不得把该关系写成事实；可说明材料未予支持，并给出有证据的替代关系。"
                )
            context_parts.append(f"文档{i+1}{relation}: {content}")
        if claim_notice:
            context_parts.insert(0, claim_notice)
        return "\n\n".join(context_parts)

    @staticmethod
    def _build_sources(
        results: List[Dict], name_mapping: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        sources = []
        seen = set()
        for result in results:
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "unknown")
            item: Dict[str, Any] = {
                "doc_name": metadata.get("doc_name") or name_mapping.get(source, source),
                "chunk_index": metadata.get("chunk_index"),
                "page": metadata.get("page"),
            }
            graph_fields = {
                "retrieval_source": metadata.get("retrieval_source"),
                "graph_schema_version": metadata.get("graph_schema_version"),
                "relation_id": metadata.get("relation_id"),
                "relation_type": metadata.get("relation_type"),
                "relation_label": metadata.get("relation_label"),
                "source_entity": metadata.get("source_entity"),
                "target_entity": metadata.get("target_entity"),
                "evidence_id": metadata.get("evidence_id"),
            }
            if any(value is not None for value in graph_fields.values()):
                item.update(graph_fields)
            key = tuple(item.values())
            if key not in seen:
                seen.add(key)
                sources.append(item)
        return sources

    @staticmethod
    def _is_authoritative_query(query: str) -> bool:
        compact = "".join((query or "").split())
        return any(term in compact for term in (
            "标准", "国标", "规范", "指标", "属于", "规定", "检测方法",
            "基础性", "区域补充", "踏勘", "实验室", "赋值",
        ))

    def health(self) -> Dict[str, Any]:
        return {
            "rollout_mode": Config.KG_ROLLOUT_MODE,
            "canary_percent": Config.KG_CANARY_PERCENT,
            "professional_evidence_enabled": Config.KG_PROFESSIONAL_EVIDENCE_ENABLED,
            "graph": self.kg_retriever.health(),
        }

    def _build_prompt(self, query: str, context: str) -> str:
        return f"""基于以下文档内容，回答用户的问题。请优先参考本地知识库中的文档内容进行回答。

文档内容：
{context}

用户问题：
{query}

请以自然、专业的语言回答，并遵守以下证据规则：
1. “基础性/区域补充性”是指标分类角色；“现场踏勘/实验室检测”是指标获取方式，两个维度相互独立，不得用一个维度证明另一个维度。
2. 只陈述上述证据直接支持的事实；证据未出现的工具、步骤、阈值和适用范围不得自行补充。
3. 如果问题前提与已核验图谱关系冲突，应明确指出“不对”，再给出有证据的正确关系。
4. 如果证据不足，应明确说“当前已核验材料不足以判断”，不得用模型常识补齐权威结论。
5. 回答先给直接结论，再说明标准名称、关系和页码依据。"""

rag_chain = RAGChain()
