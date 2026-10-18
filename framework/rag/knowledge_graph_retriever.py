"""Permission-safe adapter for the reviewed cultivated-land graph.

The graph ranks evidence references, but never returns its embedded quote as a
RAG document.  Every graph reference is resolved back to a persisted Chroma
chunk with the same access filters used by ordinary retrieval.  This keeps the
graph from becoming an authorization side channel.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from framework.knowledge.taxonomy import primary_domain_for_category
from framework.knowledge_graph import assess_graph_claim, rank_graph_evidence
from framework.rag.kg_runtime import (
    inspect_graph_release, stable_document_key, stable_evidence_id,
)


class KnowledgeGraphRetriever:
    """Load a reviewed graph lazily and resolve evidence to authorized chunks."""

    _SUPPORTED_SCHEMAS = {
        "minimal-cultivated-land-kg-v0.3": "knowledge_graph_v0.3",
        "minimal-cultivated-land-kg-v0.4": "knowledge_graph_v0.4",
    }

    def __init__(
        self, graph_path: str, *, enabled: bool = True,
        manifest_path: str | None = None, expected_sha256: str | None = None,
    ):
        self.graph_path = Path(graph_path)
        self.enabled = enabled
        self.manifest_path = manifest_path
        self.expected_sha256 = expected_sha256 or None
        self._graph: Optional[dict[str, Any]] = None
        self._graph_mtime_ns: Optional[int] = None
        self._last_error: Optional[str] = None

    def health(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "ready": True, "enabled": False, "status": "disabled",
                "graph_path": str(self.graph_path), "errors": [],
            }
        result = inspect_graph_release(
            self.graph_path, manifest_path=self.manifest_path,
            expected_sha256=self.expected_sha256,
        )
        # Unit tests and legacy callers may intentionally use an unsigned
        # temporary graph. Production RAG always supplies manifest_path.
        if self.manifest_path is None:
            result["errors"] = [
                item for item in result["errors"] if item != "manifest_missing"
            ]
            result["ready"] = not result["errors"]
        result.update({
            "enabled": True,
            "status": "ready" if result["ready"] else "degraded",
            "last_load_error": self._last_error,
        })
        return result

    def _load_graph(self) -> Optional[dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            health = self.health()
            if not health.get("ready"):
                self._last_error = ",".join(health.get("errors") or ["release_not_ready"])
                return None
            mtime_ns = self.graph_path.stat().st_mtime_ns
            if self._graph is None or self._graph_mtime_ns != mtime_ns:
                graph = json.loads(self.graph_path.read_text(encoding="utf-8"))
                if graph.get("schema_version") not in self._SUPPORTED_SCHEMAS:
                    self._last_error = "unsupported_schema"
                    return None
                self._graph = graph
                self._graph_mtime_ns = mtime_ns
                self._last_error = None
            return self._graph
        except (OSError, ValueError, TypeError):
            # The production RAG path must keep its vector fallback when the
            # optional graph artifact is absent or malformed.
            self._last_error = "graph_load_failed"
            return None

    @staticmethod
    def _category_is_eligible(category: Optional[str]) -> bool:
        if not category:
            return True
        domain = primary_domain_for_category(category)
        return domain in {None, "cultivated_land_quality"}

    @staticmethod
    def supports_query_intent(query: str) -> bool:
        """Return False for intents not represented by the v0.3 relation schema."""
        compact = "".join((query or "").split())
        if any(term in compact for term in ("什么是", "是什么意思", "定义是什么", "含义是什么")):
            return False
        if any(term in compact for term in ("空间分布", "分布情况", "区域分布", "时空变化", "变化趋势")):
            return False
        return True

    def retrieve(
        self,
        query: str,
        *,
        vector_store: Any,
        filters: Optional[Dict[str, Any]],
        category: Optional[str],
        top_k: int,
    ) -> dict[str, Any]:
        graph = self._load_graph()
        fetch = getattr(vector_store, "get_by_references", None)
        if (
            graph is None or not callable(fetch)
            or not self._category_is_eligible(category)
            or not self.supports_query_intent(query)
        ):
            return {"results": [], "claim_assessment": None, "matched": False}

        ranked = rank_graph_evidence(graph, query, top_k=max(top_k * 3, 12))
        if not ranked:
            return {"results": [], "claim_assessment": None, "matched": False}

        references = []
        for item in ranked:
            metadata = item.get("metadata") or {}
            references.append({
                "document_id": metadata.get("document_id"),
                "document_title": metadata.get("document_title"),
                "document_key": metadata.get("document_key") or stable_document_key(
                    str(metadata.get("document_title") or "")
                ),
                "page": metadata.get("page"),
                "chunk_index": metadata.get("chunk_index"),
                "evidence_id": metadata.get("evidence_id") or stable_evidence_id(metadata),
                "quote_sha256": metadata.get("quote_sha256"),
            })

        # Chroma applies the normal visibility/owner/domain/document filters.
        chunks = fetch(
            references,
            filters=filters,
            category=category,
            n_results=max(top_k * 4, 20),
        )
        retrieval_source = self._SUPPORTED_SCHEMAS[str(graph["schema_version"])]
        results = self._attach_graph_metadata(
            chunks, ranked, top_k=top_k, retrieval_source=retrieval_source,
        )
        claim = assess_graph_claim(graph, query)
        if claim.get("status") not in {"supported", "unsupported"}:
            claim = None
        if results and claim:
            results[0].setdefault("metadata", {})["graph_claim_status"] = claim["status"]
            results[0]["metadata"]["graph_claim_reason"] = claim.get("reason")
        return {
            "results": results,
            "claim_assessment": claim,
            "matched": True,
        }

    @staticmethod
    def _reference_matches(
        metadata: Mapping[str, Any], reference: Mapping[str, Any],
    ) -> bool:
        id_matches = False
        try:
            id_matches = int(metadata.get("document_id")) == int(reference.get("document_id"))
        except (TypeError, ValueError):
            pass
        key_matches = bool(
            metadata.get("document_key")
            and metadata.get("document_key") == reference.get("document_key")
        )
        if not (id_matches or key_matches):
            return False
        chunk_index = reference.get("chunk_index")
        page = reference.get("page")
        chunk_matches = chunk_index is not None and metadata.get("chunk_index") == chunk_index
        page_matches = page is not None and metadata.get("page") == page
        return chunk_matches or page_matches or (chunk_index is None and page is None)

    @classmethod
    def _attach_graph_metadata(
        cls,
        chunks: Sequence[Mapping[str, Any]],
        ranked: Sequence[Mapping[str, Any]],
        *,
        top_k: int,
        retrieval_source: str,
    ) -> list[dict[str, Any]]:
        attached: list[dict[str, Any]] = []
        positions: dict[tuple[Any, ...], int] = {}
        for evidence in ranked:
            reference = evidence.get("metadata") or {}
            for chunk in chunks:
                metadata = dict(chunk.get("metadata") or {})
                if not cls._reference_matches(metadata, reference):
                    continue
                key = (
                    metadata.get("document_id"), metadata.get("page"),
                    metadata.get("chunk_index"), chunk.get("content"),
                )
                relation_descriptor = {
                    "relation_id": evidence.get("relation_id"),
                    "relation_type": evidence.get("relation_type"),
                    "relation_label": evidence.get("relation_label"),
                    "relation_semantics": evidence.get("relation_semantics"),
                    "source_entity": evidence.get("source_entity"),
                    "target_entity": evidence.get("target_entity"),
                    "graph_rank": evidence.get("graph_rank"),
                    "graph_score": evidence.get("score"),
                    "evidence_id": reference.get("evidence_id") or stable_evidence_id(reference),
                }
                if key in positions:
                    existing_metadata = attached[positions[key]]["metadata"]
                    relation_ids = existing_metadata.setdefault("relation_ids", [])
                    if evidence.get("relation_id") not in relation_ids:
                        relation_ids.append(evidence.get("relation_id"))
                        existing_metadata.setdefault("graph_relations", []).append(
                            relation_descriptor
                        )
                    continue
                positions[key] = len(attached)
                metadata.update({
                    "retrieval_source": retrieval_source,
                    "graph_rank": evidence.get("graph_rank"),
                    "graph_score": evidence.get("score"),
                    "relation_id": evidence.get("relation_id"),
                    "relation_type": evidence.get("relation_type"),
                    "relation_label": evidence.get("relation_label"),
                    "relation_semantics": evidence.get("relation_semantics"),
                    "source_entity": evidence.get("source_entity"),
                    "target_entity": evidence.get("target_entity"),
                    "graph_schema_version": retrieval_source.replace("knowledge_graph_", "minimal-cultivated-land-kg-"),
                    "evidence_id": reference.get("evidence_id") or stable_evidence_id(reference),
                    "quote_sha256": reference.get("quote_sha256"),
                    "relation_ids": [evidence.get("relation_id")],
                    "graph_relations": [relation_descriptor],
                })
                attached.append({
                    "content": chunk.get("content", ""),
                    "metadata": metadata,
                    "distance": chunk.get("distance", 0),
                })
        return attached[:top_k]

    @staticmethod
    def merge(
        graph_results: Sequence[Mapping[str, Any]],
        vector_results: Sequence[Mapping[str, Any]],
        *,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Prefer audited graph evidence, then fill remaining slots by vector rank."""
        merged: list[dict[str, Any]] = []
        seen = set()
        for row in [*graph_results, *vector_results]:
            item = dict(row)
            metadata = dict(item.get("metadata") or {})
            item["metadata"] = metadata
            key = (
                metadata.get("document_id"), metadata.get("source"),
                metadata.get("page"), metadata.get("chunk_index"),
                item.get("content"),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= top_k:
                break
        return merged
