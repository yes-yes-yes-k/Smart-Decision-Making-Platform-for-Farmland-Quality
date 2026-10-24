from __future__ import annotations
import json
import os
import re
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

    def _query_document_metadata(
        self, file_paths: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Load bibliography fields that may be absent from older vector chunks."""
        mapping: Dict[str, Dict[str, Any]] = {}
        if not file_paths:
            return mapping

        def add_row(row) -> None:
            bibliographic = getattr(row, "bibliographic_metadata", None) or {}
            item = {
                "doc_name": getattr(row, "doc_name", None),
                "document_kind": getattr(row, "document_kind", None),
                "title": getattr(row, "title", None),
                "authors": bibliographic.get("authors") or [],
                "journal": bibliographic.get("journal"),
                "publication_date": bibliographic.get("publication_date"),
                "volume": bibliographic.get("volume"),
                "issue": bibliographic.get("issue"),
                "pages": bibliographic.get("pages"),
                "doi": getattr(row, "doi_normalized", None),
                "standard_number": getattr(row, "standard_number_normalized", None),
                "issuing_authority": getattr(row, "issuing_authority", None),
            }
            item = {key: value for key, value in item.items() if value not in (None, "", [])}
            for key in (getattr(row, "file_path", None), getattr(row, "doc_name", None)):
                if key:
                    mapping[str(key)] = item

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
                    add_row(row)
                return mapping
        except Exception:
            pass

        try:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "instance", "development.db",
            )
            if not os.path.exists(db_path):
                return mapping
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" * len(file_paths))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT file_path, doc_name, document_kind, title, "
                "bibliographic_metadata, doi_normalized, "
                "standard_number_normalized, issuing_authority "
                f"FROM kb_document WHERE file_path IN ({placeholders}) "
                f"OR doc_name IN ({placeholders})",
                file_paths + file_paths,
            )
            for raw in cursor.fetchall():
                bibliographic = raw["bibliographic_metadata"] or "{}"
                if isinstance(bibliographic, str):
                    try:
                        bibliographic = json.loads(bibliographic)
                    except json.JSONDecodeError:
                        bibliographic = {}
                item = {
                    "doc_name": raw["doc_name"],
                    "document_kind": raw["document_kind"],
                    "title": raw["title"],
                    "authors": bibliographic.get("authors") or [],
                    "journal": bibliographic.get("journal"),
                    "publication_date": bibliographic.get("publication_date"),
                    "volume": bibliographic.get("volume"),
                    "issue": bibliographic.get("issue"),
                    "pages": bibliographic.get("pages"),
                    "doi": raw["doi_normalized"],
                    "standard_number": raw["standard_number_normalized"],
                    "issuing_authority": raw["issuing_authority"],
                }
                item = {
                    key: value for key, value in item.items()
                    if value not in (None, "", [])
                }
                for key in (raw["file_path"], raw["doc_name"]):
                    if key:
                        mapping[str(key)] = item
            conn.close()
        except Exception:
            pass
        return mapping

    @staticmethod
    def _enrich_results(
        results: List[Dict], document_metadata: Dict[str, Dict[str, Any]],
    ) -> List[Dict]:
        enriched = []
        for result in results:
            metadata = dict(result.get("metadata") or {})
            source = str(metadata.get("source") or metadata.get("doc_name") or "unknown")
            for key, value in document_metadata.get(source, {}).items():
                if metadata.get(key) in (None, "", []):
                    metadata[key] = value
            enriched.append({**result, "metadata": metadata})
        return enriched

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

        results = retrieval_results["results"]
        uuid_names = []
        for result in results:
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "unknown")
            if source not in uuid_names:
                uuid_names.append(source)
        name_mapping = self._query_doc_names(uuid_names)
        document_metadata = self._query_document_metadata(uuid_names)
        results = self._enrich_results(results, document_metadata)

        context = self._build_context(results)
        prompt = self._build_prompt(query, context)

        llm_response = self.llm_service.generate(prompt, conversation_history)
        answer = self._finalize_answer(llm_response.get("content", ""), results)
        sources = self._build_sources(results, name_mapping)

        return {
            "success": llm_response.get("success", False),
            "answer": answer,
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
        results = self._enrich_results(
            retrieved["results"], self._query_document_metadata(file_paths),
        )
        return {
            "context": self._build_context(results),
            "sources": self._build_sources(results, mapping),
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

        results = retrieval_results["results"]
        uuid_names = []
        for result in results:
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "unknown")
            if source not in uuid_names:
                uuid_names.append(source)
        name_mapping = self._query_doc_names(uuid_names)
        results = self._enrich_results(
            results, self._query_document_metadata(uuid_names),
        )

        context = self._build_context(results)
        prompt = self._build_prompt(query, context)

        sources = self._build_sources(results, name_mapping)

        # 先发送来源元数据，前端可立即展示参考来源
        yield {
            "type": "meta", "sources": sources,
            "retrieval": retrieval_results.get("diagnostics", {}),
        }

        # 流式 LLM 生成
        for chunk in self.llm_service.generate_stream(prompt, conversation_history):
            yield {"type": "token", "content": chunk}
        reference_suffix = self._reference_suffix(results)
        if reference_suffix:
            yield {"type": "token", "content": reference_suffix}

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

    @staticmethod
    def _citation_key(metadata: Dict[str, Any]) -> str:
        return str(
            metadata.get("document_id")
            or metadata.get("source")
            or metadata.get("doc_name")
            or metadata.get("title")
            or "unknown"
        )

    @staticmethod
    def _normalize_authors(value: Any) -> List[str]:
        if isinstance(value, (list, tuple)):
            return [str(author).strip() for author in value if str(author).strip()]
        if not value:
            return []
        text = str(value).strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(author).strip() for author in parsed if str(author).strip()]
            except json.JSONDecodeError:
                pass
        return [author.strip() for author in re.split(r"[;；]", text) if author.strip()]

    @classmethod
    def _format_citation(cls, metadata: Dict[str, Any]) -> str:
        """Format a compact GB/T 7714-style bibliography entry."""
        fallback = str(metadata.get("doc_name") or metadata.get("source") or "来源未详")
        fallback = os.path.splitext(os.path.basename(fallback))[0] or fallback
        title = str(metadata.get("title") or fallback).strip()
        authors = cls._normalize_authors(metadata.get("authors"))
        kind = str(metadata.get("document_kind") or "other")
        type_code = {
            "academic_paper": "J",
            "standard": "S",
            "method_guideline": "S",
            "policy": "Z",
            "other": "Z",
        }.get(kind, "Z")

        lead_parts = []
        if authors:
            lead_parts.append(", ".join(authors))
        standard_number = str(metadata.get("standard_number") or "").strip()
        if standard_number and standard_number not in title:
            title = f"{standard_number} {title}"
        lead_parts.append(f"{title}[{type_code}]")
        citation = ". ".join(lead_parts) + "."

        publication_parts = []
        if kind in {"standard", "method_guideline"}:
            authority = str(metadata.get("issuing_authority") or "").strip()
            if authority and authority not in authors:
                publication_parts.append(authority)
        else:
            journal = str(metadata.get("journal") or "").strip()
            if journal:
                publication_parts.append(journal)

        publication_date = str(metadata.get("publication_date") or "").strip()
        year_match = re.search(r"\b(19|20)\d{2}\b", publication_date)
        year = year_match.group(0) if year_match else publication_date
        if year:
            publication_parts.append(year)

        volume = str(metadata.get("volume") or "").strip()
        issue = str(metadata.get("issue") or "").strip()
        if volume:
            publication_parts.append(f"{volume}({issue})" if issue else volume)
        elif issue:
            publication_parts.append(f"({issue})")
        pages = str(metadata.get("pages") or "").strip()
        if pages:
            publication_parts.append(pages)
        if publication_parts:
            citation += " " + ", ".join(publication_parts) + "."

        doi = str(metadata.get("doi") or "").strip()
        if doi:
            citation += f" DOI: {doi}."
        return citation

    @classmethod
    def _reference_catalog(cls, results: List[Dict]) -> List[Dict[str, Any]]:
        catalog = []
        seen = set()
        for result in results:
            metadata = result.get("metadata") or {}
            key = cls._citation_key(metadata)
            if key in seen:
                continue
            seen.add(key)
            catalog.append({
                "key": key,
                "number": len(catalog) + 1,
                "citation": cls._format_citation(metadata),
            })
        return catalog

    @classmethod
    def _reference_suffix(cls, results: List[Dict]) -> str:
        catalog = cls._reference_catalog(results)
        if not catalog:
            return ""
        entries = "\n".join(
            f"[{item['number']}] {item['citation']}" for item in catalog
        )
        return f"\n\n参考文献\n{entries}"

    @classmethod
    def _finalize_answer(cls, answer: str, results: List[Dict]) -> str:
        normalized = re.sub(
            r"文档\s*(\d+)",
            lambda match: f"参考文献[{match.group(1)}]",
            answer or "",
        ).rstrip()
        return normalized + cls._reference_suffix(results)

    def _build_context(self, results: List[Dict]) -> str:
        context_parts = []
        claim_notice = None
        catalog = self._reference_catalog(results)
        citation_numbers = {item["key"]: item["number"] for item in catalog}
        citations = {item["key"]: item["citation"] for item in catalog}
        for result in results:
            content = result.get("content", "")
            metadata = result.get("metadata") or {}
            citation_key = self._citation_key(metadata)
            citation_number = citation_numbers[citation_key]
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
            page = metadata.get("page")
            location = f"\n证据位置：第 {page} 页" if page is not None else ""
            context_parts.append(
                f"[{citation_number}] 参考文献：{citations[citation_key]}{relation}"
                f"{location}\n证据内容：{content}"
            )
        if claim_notice:
            context_parts.insert(0, claim_notice)
        return "\n\n".join(context_parts)

    @classmethod
    def _build_sources(
        cls, results: List[Dict], name_mapping: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        sources = []
        seen = set()
        catalog = cls._reference_catalog(results)
        citation_numbers = {item["key"]: item["number"] for item in catalog}
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
            has_bibliography = any(metadata.get(field) not in (None, "", []) for field in (
                "document_kind", "title", "authors", "journal", "publication_date",
                "doi", "standard_number", "issuing_authority",
            ))
            if has_bibliography:
                citation_key = cls._citation_key(metadata)
                item.update({
                    "citation_number": citation_numbers[citation_key],
                    "citation": cls._format_citation(metadata),
                    "title": metadata.get("title") or item["doc_name"],
                    "authors": cls._normalize_authors(metadata.get("authors")),
                    "journal": metadata.get("journal"),
                    "publication_year": (
                        re.search(r"\b(19|20)\d{2}\b", str(metadata.get("publication_date") or ""))
                        .group(0)
                        if re.search(r"\b(19|20)\d{2}\b", str(metadata.get("publication_date") or ""))
                        else None
                    ),
                    "doi": metadata.get("doi") or None,
                })
            key = (
                source, item.get("chunk_index"), item.get("page"),
                item.get("relation_id"), item.get("evidence_id"),
            )
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
        return f"""基于以下参考文献与证据内容，回答用户的问题。请优先参考本地知识库中的内容。

参考文献与证据：
{context}

用户问题：
{query}

请以自然、专业的语言回答，并遵守以下证据规则：
1. “基础性/区域补充性”是指标分类角色；“现场踏勘/实验室检测”是指标获取方式，两个维度相互独立，不得用一个维度证明另一个维度。
2. 只陈述上述证据直接支持的事实；证据未出现的工具、步骤、阈值和适用范围不得自行补充。
3. 如果问题前提与已核验图谱关系冲突，应明确指出“不对”，再给出有证据的正确关系。
4. 如果证据不足，应明确说“当前已核验材料不足以判断”，不得用模型常识补齐权威结论。
5. 回答先给直接结论，再说明标准名称、关系和页码依据。
6. 在相关陈述后用“[1]”“[2]”这样的顺序编码标注引文；严禁使用“文档1”“文档2”或文件名作为引文。
7. 不得编造作者、题名、期刊、年份或 DOI。只输出正文和顺序编码，不要另写参考文献列表，系统会统一附加规范格式的参考文献。"""

rag_chain = RAGChain()
