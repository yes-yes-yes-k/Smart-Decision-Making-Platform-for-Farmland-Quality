from __future__ import annotations
import os
import re
import threading
import uuid
from typing import Optional, List, Dict, Any
from framework.vector_store.runtime_temp import prepare_chroma_temp_directory

prepare_chroma_temp_directory()

import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from chromadb.config import Settings
from framework.config import Config
from framework.embedding.service import embedding_service
from framework.vector_store.bm25_store import BM25Store
from framework.vector_store.retrieval_policy import VERSION as CONCEPT_VERSION, lexical_concept_groups, interleave_unique
from framework.knowledge.taxonomy import DOMAIN_CODES


class NoOpEmbeddingFunction(EmbeddingFunction[Documents]):
    """空操作 embedding function，仅用于阻止 ChromaDB 下载默认 ONNX 模型。
    实际的 embeddings 由 add_documents 方法直接传入。"""

    def __init__(self):
        pass

    def __call__(self, input: Documents) -> Embeddings:
        # 这个方法不应该被 ChromaDB 调用，因为我们总是直接传入 embeddings
        raise RuntimeError("NoOpEmbeddingFunction 不应被调用，请直接传入 embeddings")

    @staticmethod
    def name() -> str:
        return "noop"

    def get_config(self) -> Dict[str, Any]:
        return {"type": "noop"}

    @staticmethod
    def build_from_config(config: Dict[str, Any]) -> "NoOpEmbeddingFunction":
        return NoOpEmbeddingFunction()


def slugify(category: str) -> str:
    """将 category 规范化为 ASCII slug；无 ASCII 字符时归为 'other'。"""
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", category.strip().lower())
    return slug.strip("_") or "other"


def collection_name_for(category: Optional[str]) -> str:
    """计算 collection 名：空/other → 默认 enterprise_kb；否则 kb_<slug>。"""
    if not category:
        return Config.CHROMA_COLLECTION_NAME
    if category.strip().lower() == "other":
        return Config.CHROMA_COLLECTION_NAME
    return f"kb_{slugify(category)}"


class ChromaVectorStore:
    def __init__(self):
        self._client = None
        self._collections: Dict[str, Any] = {}
        self._bm25: Dict[str, BM25Store] = {}
        self._lexical_path = os.path.join(os.path.abspath(Config.CHROMA_PERSIST_DIR), "lexical-index.sqlite3")
        # Chroma's local persistent client is not reliably read-after-write
        # consistent when several worker threads mutate the same collection at
        # once.  Embedding remains concurrent; only the short persistence
        # critical sections are serialized.
        self._write_lock = threading.RLock()
        self._init_client()

    def _init_client(self):
        persist_dir = os.path.abspath(Config.CHROMA_PERSIST_DIR)
        default_name = Config.CHROMA_COLLECTION_NAME

        os.makedirs(persist_dir, exist_ok=True)

        try:
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=False,
                )
            )

            # Never delete or recreate a persisted collection during application startup.
            # Chroma stores embedding-function configuration outside collection.metadata in
            # some versions, so metadata is not a safe compatibility signal.
            for item in self._client.list_collections():
                name = item.name if hasattr(item, "name") else str(item)
                self._collections[name] = self._client.get_collection(
                    name=name, embedding_function=NoOpEmbeddingFunction())

            if default_name not in self._collections:
                self._collections[default_name] = self._client.get_or_create_collection(
                    name=default_name, embedding_function=NoOpEmbeddingFunction())

            self._rebuild_bm25_indexes()
            print(
                f"[Chroma] 已加载 {len(self._collections)} 个集合: "
                f"{', '.join(sorted(self._collections))}"
            )
        except Exception as e:
            print(f"Chroma初始化失败: {e}")
            import traceback
            traceback.print_exc()

    def _new_bm25(self, name):
        return BM25Store(getattr(self, "_lexical_path", None), name)

    @staticmethod
    def _lexical_batches(collection, selector=None):
        selector = selector or {}
        if "ids" in selector:
            groups = [selector["ids"][offset:offset+500] for offset in range(0, len(selector["ids"]), 500)]
            for identifiers in groups:
                data = collection.get(ids=identifiers, include=["documents", "metadatas"])
                actual, documents, metas = data.get("ids") or [], data.get("documents") or [], data.get("metadatas") or []
                if len(actual) != len(documents) or len(documents) != len(metas):
                    raise ValueError("lexical_source_page_alignment_failed")
                yield list(zip(actual, documents, metas))
            return
        offset = 0
        while True:
            options = dict(limit=500, offset=offset, include=["documents", "metadatas"])
            if selector.get("where"):
                options["where"] = selector["where"]
            data = collection.get(**options)
            identifiers, documents, metas = data.get("ids") or [], data.get("documents") or [], data.get("metadatas") or []
            if len(identifiers) != len(documents) or len(documents) != len(metas):
                raise ValueError("lexical_source_page_alignment_failed")
            if identifiers:
                yield list(zip(identifiers, documents, metas))
            if len(identifiers) < 500:
                break
            offset += len(identifiers)

    def _sync_lexical_pending(self, name, collection):
        store = self._bm25[name]
        for identifier, selector in store.index.pending():
            store.index.reconcile(identifier, selector, self._lexical_batches(collection, selector), collection.count())

    def _rebuild_bm25_indexes(self, force=False) -> None:
        """Open ready indexes without text reads; bootstrap/repair stream pages."""
        for name, collection in self._collections.items():
            if name not in self._bm25:
                self._bm25[name] = self._new_bm25(name)
            store = self._bm25[name]
            try:
                health = store.index.health()
                if force or health["base_state"] != "ready":
                    count = collection.count()
                    store.index.begin_rebuild()
                    for batch in self._lexical_batches(collection):
                        store.index.upsert(batch)
                    if collection.count() != count:
                        raise ValueError("lexical_source_changed_during_bootstrap")
                    store.index.finish_rebuild(count)
                elif health["pending_operations"]:
                    self._sync_lexical_pending(name, collection)
                elif health["source_count"] != collection.count() or health["rows"] != collection.count():
                    # Outside writers require explicit full repair, not a silent
                    # per-query rebuild. Chroma remains the authoritative source.
                    store.index.begin_operation({"where": None})
                    self._sync_lexical_pending(name, collection)
            except Exception:
                print(f"[BM25] 集合 {name} 派生索引未就绪，保留向量回退与修复记录")

    def _get_collection(self, category: Optional[str] = None):
        """按 category 懒创建/获取 collection（空/other → 默认 enterprise_kb）。"""
        name = collection_name_for(category)
        if name not in self._collections:
            collection = self._client.get_or_create_collection(
                name=name, embedding_function=NoOpEmbeddingFunction())
            self._collections[name] = collection
            if name not in self._bm25:
                self._bm25[name] = self._new_bm25(name)
                if self._bm25[name].index.health()["rows"]:
                    self._bm25[name].index.begin_rebuild()
                self._bm25[name].index.finish_rebuild(0)
        return self._collections[name]

    def _targeted_collection(self, category: Optional[str] = None):
        """category 具体且对应 collection 已存在 → 返回；否则 None（全库回退）。"""
        if not category or category.strip().lower() == "other":
            return None
        # A document may carry several approved domain labels while its chunks
        # remain stored once in the original primary collection. Domain queries
        # therefore scan collections and rely on boolean metadata filters.
        if category.strip().lower() in DOMAIN_CODES:
            return None
        return self._collections.get(collection_name_for(category))

    def _bm25_for(self, category: Optional[str] = None) -> BM25Store:
        """按 category 懒获取 BM25 索引（空/other → 默认）。"""
        name = collection_name_for(category)
        if name not in self._bm25:
            self._bm25[name] = self._new_bm25(name)
        return self._bm25[name]

    def add_documents(self, texts: List[str], metadatas: Optional[List[Dict]] = None,
                      ids: Optional[List[str]] = None, category: Optional[str] = None,
                      update_bm25: bool = True) -> int:
        """添加文档：按 category 路由到分领域 collection，并同步对应 BM25。"""
        if not self._client:
            return 0

        if not embedding_service.is_available():
            print("[Chroma] embedding_service 不可用，跳过向量化")
            return 0

        try:
            if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
                print("[Chroma] 文档内容为空或类型非法，跳过向量化")
                return 0

            clean_metadatas: List[Dict[str, Any]] = []
            for metadata in metadatas or [{} for _ in texts]:
                clean_metadatas.append({
                    key: value for key, value in dict(metadata or {}).items()
                    if value is not None and isinstance(value, (str, int, float, bool))
                })
            if len(clean_metadatas) != len(texts):
                print("[Chroma] metadata 数量与文档数量不一致")
                return 0

            resolved_ids = ids or [uuid.uuid4().hex for _ in texts]
            if len(resolved_ids) != len(texts) or len(set(resolved_ids)) != len(resolved_ids):
                print("[Chroma] 文档 ID 数量不一致或存在重复")
                return 0

            # 直接获取 embeddings，不通过 ChromaDB 的 embedding_function
            embeddings = embedding_service.embed_documents(texts)
            if len(embeddings) != len(texts) or any(not vector for vector in embeddings):
                print("[Chroma] embedding 返回数量不足或包含空向量")
                return 0

            with self._write_lock:
                collection = self._get_collection(category)
                existing = collection.get(ids=resolved_ids, include=["metadatas"])
                if existing.get("ids"):
                    print(f"[Chroma] 检测到重复文档 ID，拒绝整批写入: {existing['ids']}")
                    return 0

                name = collection_name_for(category)
                lexical = self._bm25_for(category)
                lexical.index.begin_operation({"ids": resolved_ids})
                collection.add(
                    ids=resolved_ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=clean_metadatas,
                )
                written = collection.get(ids=resolved_ids, include=[]).get("ids") or []
                added_count = len(written)
                if set(written) != set(resolved_ids):
                    print(
                        f"[Chroma] 写入数量不一致: expected={len(texts)} actual={added_count}"
                    )
                    return 0
                if update_bm25:
                    try:
                        self._sync_lexical_pending(name, collection)
                    except Exception:
                        print("[BM25] 写入后派生索引待修复，文献向量写入仍有效")
            return added_count
        except Exception as e:
            print(f"添加文档失败: {e}")
            return 0

    def _search_in(self, collection, query: str, n_results: int,
                   filters: Optional[Dict], query_embedding=None) -> List[Dict]:
        """对单个 collection 做向量召回，返回 [{content, metadata, distance}...]。"""
        if query_embedding is None:
            query_embedding = embedding_service.embed_query(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filters or None,
        )
        formatted: List[Dict] = []
        for i in range(len(results.get("documents", []))):
            docs = results["documents"][i]
            metas = results.get("metadatas", [[]])[i]
            dists = results.get("distances", [[]])[i]
            for j, doc in enumerate(docs):
                formatted.append({
                    "content": doc,
                    "metadata": metas[j] if j < len(metas) else {},
                    "distance": dists[j] if j < len(dists) else 0,
                })
        return formatted

    def search(self, query: str, n_results: int = 3, filters: Optional[Dict] = None,
               category: Optional[str] = None) -> Dict[str, Any]:
        if not self._collections:
            return {"results": [], "count": 0, "retrieval": {"mode": "vector", "state": "unavailable", "reason": "no_collections"}}

        if not embedding_service.is_available():
            print("[Chroma] embedding_service 不可用，无法搜索")
            return {"results": [], "count": 0, "retrieval": {"mode": "vector", "state": "unavailable", "reason": "embedding_not_configured"}}

        try:
            # One query vector is shared by all collections. Do not issue one
            # paid embedding request per collection.
            query_embedding = embedding_service.embed_query(query)
            if not query_embedding:
                return {"results": [], "count": 0, "retrieval": {"mode": "vector", "state": "failed", "reason": "empty_query_embedding"}}
            target = self._targeted_collection(category)
            if target is not None:
                formatted = self._search_in(target, query, n_results, filters, query_embedding)
            else:
                formatted = []
                for collection in self._collections.values():
                    formatted.extend(self._search_in(collection, query, n_results, filters, query_embedding))
                # 全库回退：向量距离越小越相关，升序取 top-n
                formatted.sort(key=lambda r: r.get("distance", 0))
                formatted = formatted[:n_results]
            return {"results": formatted, "count": len(formatted),
                    "retrieval": {"mode": "vector", "state": "completed", "query_embeddings": 1}}
        except Exception as e:
            print(f"搜索失败: {e}")
            return {"results": [], "count": 0, "retrieval": {"mode": "vector", "state": "failed", "reason": "vector_query_failed"}}

    def hybrid_search(self, query: str, n_results: int = 20, filters: Optional[Dict] = None,
                      category: Optional[str] = None, *, domain_expansion=False) -> Dict[str, Any]:
        """双路召回：向量 + BM25，RRF 融合（支持 category 定向，否则全库回退）。

        Config.HYBRID_SEARCH_ENABLED=False 时回退纯向量单路（回滚路径）。
        """
        if not Config.HYBRID_SEARCH_ENABLED:
            return self.search(query, n_results, filters, category)

        vector_res = self.search(query, n_results, filters, category)
        lexical = {"collections_checked": 0, "collections_ready": 0, "failures": 0}
        groups = lexical_concept_groups(query) if domain_expansion and n_results >= 2 else []
        if groups:
            original_limit = (n_results+1)//2
            original = self._bm25_search(query, original_limit, filters, category, diagnostics=lexical)
            expanded = self._bm25_search(query, n_results-original_limit, filters, category,
                                         diagnostics=lexical, concept_groups=groups)
            bm25_docs = interleave_unique(original, expanded, n_results)
            lexical["expansion"] = {"version": CONCEPT_VERSION, "groups": groups,
                                    "original_limit": original_limit, "expanded_limit": n_results-original_limit,
                                    "original_hits": len(original), "expanded_hits": len(expanded),
                                    "query_vector_unchanged": True}
        else:
            bm25_docs = self._bm25_search(query, n_results, filters, category, diagnostics=lexical)
        fused = self._rrf_fuse(vector_res["results"], bm25_docs, k=Config.RRF_K)
        fused = fused[:n_results]
        vector = vector_res.get("retrieval", {"state": "unknown"})
        lexical["state"] = ("unavailable" if not lexical["collections_ready"] else
                            "partial" if lexical["failures"] else "completed")
        mode = "hybrid" if vector["state"] == lexical["state"] == "completed" else "degraded"
        return {"results": fused, "count": len(fused), "retrieval": {
            "mode": mode, "vector": vector | {"hits": len(vector_res["results"])},
            "lexical": lexical | {"hits": len(bm25_docs)},
            "fusion": {"method": "rrf", "k": Config.RRF_K}, "reranking": "not_applied"}}

    @staticmethod
    def _combine_filters(
        left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        clauses: List[Dict[str, Any]] = []
        for value in (left, right):
            if not value:
                continue
            if set(value) == {"$and"} and isinstance(value["$and"], list):
                clauses.extend(value["$and"])
            else:
                clauses.append(value)
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def get_by_references(
        self,
        references: List[Dict[str, Any]],
        *,
        filters: Optional[Dict[str, Any]] = None,
        category: Optional[str] = None,
        n_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """Resolve graph evidence to persisted chunks under normal ACL filters."""
        clauses: List[Dict[str, Any]] = []
        seen = set()
        for reference in references:
            document_id = reference.get("document_id")
            document_key = reference.get("document_key")
            identity_terms: List[Dict[str, Any]] = []
            if document_id is not None:
                identity_terms.append({"document_id": int(document_id)})
            if document_key:
                identity_terms.append({"document_key": str(document_key)})
            if not identity_terms:
                continue
            identity_clause = (
                identity_terms[0] if len(identity_terms) == 1
                else {"$or": identity_terms}
            )
            locator_terms: List[Dict[str, Any]] = []
            if reference.get("chunk_index") is not None:
                locator_terms.append({"chunk_index": int(reference["chunk_index"])})
            if reference.get("page") is not None:
                locator_terms.append({"page": int(reference["page"])})
            terms: List[Dict[str, Any]] = [identity_clause]
            if locator_terms:
                terms.append(
                    locator_terms[0] if len(locator_terms) == 1
                    else {"$or": locator_terms}
                )
            clause = terms[0] if len(terms) == 1 else {"$and": terms}
            signature = repr(clause)
            if signature not in seen:
                seen.add(signature)
                clauses.append(clause)
        if not clauses or not self._collections:
            return []
        reference_filter = clauses[0] if len(clauses) == 1 else {"$or": clauses}
        where = self._combine_filters(filters, reference_filter)

        target = self._targeted_collection(category)
        collections = [target] if target is not None else list(self._collections.values())
        formatted: List[Dict[str, Any]] = []
        result_keys = set()
        for collection in collections:
            try:
                data = collection.get(
                    where=where, include=["documents", "metadatas"],
                )
            except Exception as exc:
                print(f"按图谱证据读取分块失败: {exc}")
                continue
            documents = data.get("documents") or []
            metadatas = data.get("metadatas") or []
            for index, content in enumerate(documents):
                metadata = metadatas[index] if index < len(metadatas) else {}
                key = (
                    metadata.get("document_id"), metadata.get("page"),
                    metadata.get("chunk_index"), content,
                )
                if key in result_keys:
                    continue
                result_keys.add(key)
                formatted.append({"content": content, "metadata": metadata})
                if len(formatted) >= n_results:
                    return formatted
        return formatted

    def _bm25_search(self, query: str, n_results: int, filters: Optional[Dict],
                     category: Optional[str] = None, *, diagnostics=None, concept_groups=None) -> List[Dict]:
        """Resolve only bounded lexical candidates against authoritative Chroma."""
        target = self._targeted_collection(category)
        names = [collection_name_for(category)] if target is not None else list(self._bm25)
        all_docs: List[Dict] = []
        for name in names:
            store, collection = self._bm25.get(name), self._collections.get(name)
            if store is None or collection is None:
                continue
            try:
                if diagnostics is not None:
                    diagnostics["collections_checked"] += 1
                    health = store.index.health()
                    if health["base_state"] != "ready" or health["pending_operations"]:
                        diagnostics["failures"] += 1
                        continue
                    diagnostics["collections_ready"] += 1
                candidates = (store.search(query, n_results, filters, concept_groups=concept_groups)
                              if concept_groups else store.search(query, n_results, filters))
                if not candidates:
                    continue
                options = dict(ids=[item["id"] for item in candidates], include=["documents", "metadatas"])
                # IDs are already bounded by the filtered sidecar query. Chroma
                # combines where+ids with a corpus metadata scan; read these IDs
                # directly and enforce the filter on authoritative metadata below.
                current = collection.get(**options)
                actual = {identifier: (text, meta) for identifier, text, meta in zip(
                    current.get("ids") or [], current.get("documents") or [], current.get("metadatas") or [])}
                stale = []
                for item in candidates:
                    value = actual.get(item["id"])
                    if value is None or value[0] != item["content"] or value[1] != item["metadata"]:
                        stale.append(item["id"]); continue
                    if not store._matches_filter(value[1], filters):
                        continue
                    all_docs.append({key: value for key,value in item.items() if key != "id"})
                if stale:
                    store.index.begin_operation({"ids": stale})
            except Exception:
                if diagnostics is not None:
                    diagnostics["failures"] += 1
                print(f"[BM25] 集合 {name} 当前候选校验失败，使用其他可用检索路径")
        all_docs.sort(key=lambda d: -d.get("score", 0.0))
        return all_docs[:n_results]

    @staticmethod
    def _rrf_fuse(vector_docs: List[Dict], bm25_docs: List[Dict], k: int = 60) -> List[Dict]:
        """Fuse by versioned chunk identity; retain per-leg ranks and RRF score."""
        score: Dict[tuple, float] = {}
        docref: Dict[tuple, Dict] = {}
        for leg, values in (("vector", vector_docs), ("lexical", bm25_docs)):
            seen = set()
            for rank, d in enumerate(values, 1):
                meta = d.get("metadata", {})
                key = ((meta["document_id"], meta.get("content_sha256"), meta["chunk_index"])
                       if meta.get("document_id") is not None and meta.get("chunk_index") is not None
                       else (meta.get("source"), d.get("content")))
                if key in seen:
                    continue
                seen.add(key)
                score[key] = score.get(key, 0.0) + 1.0 / (k + rank)
                if key not in docref:
                    docref[key] = dict(d, retrieval_ranks={})
                docref[key]["retrieval_ranks"][leg] = rank
        return [dict(docref[key], rrf_score=value) for key, value in sorted(score.items(), key=lambda kv: -kv[1])]

    def delete_by_source(self, source_doc_name: str) -> int:
        """从所有 collection 删除指定 source 的文档，并同步各 BM25。"""
        if not self._collections:
            return 0
        total_removed = 0
        for name, collection in self._collections.items():
            try:
                where = {"source": source_doc_name}
                count_before = len(collection.get(where=where, include=[]).get("ids") or [])
                self._bm25[name].index.begin_operation({"where": where})
                collection.delete(where={"source": source_doc_name})
                remaining = len(collection.get(where=where, include=[]).get("ids") or [])
                total_removed += count_before-remaining
                self._sync_lexical_pending(name, collection)
            except Exception as e:
                print(f"删除失败: {e}")
        return total_removed

    def delete_by_document_id(self, document_id: int, owner_id: Optional[int] = None) -> int:
        """Delete one logical document without affecting same-named documents."""
        if not self._collections:
            return 0
        where: Dict[str, Any] = {"document_id": document_id}
        if owner_id is not None:
            where = {"$and": [where, {"owner_id": owner_id}]}
        total_removed = 0
        with self._write_lock:
            for name, collection in self._collections.items():
                try:
                    count_before = len(collection.get(where=where, include=[]).get("ids") or [])
                    self._bm25[name].index.begin_operation({"where": where})
                    collection.delete(where=where)
                    remaining = len(collection.get(where=where, include=[]).get("ids") or [])
                    total_removed += count_before-remaining
                    self._sync_lexical_pending(name, collection)
                except Exception as exc:
                    print(f"删除 document_id={document_id} 失败 ({name}): {exc}")
        return total_removed

    def update_document_metadata(
        self, document_id: int, updates: Dict[str, Any],
        owner_id: Optional[int] = None, rebuild_indexes: bool = True,
    ) -> int:
        """Update metadata for every chunk of one logical document."""
        if not self._collections:
            return 0
        where: Dict[str, Any] = {"document_id": int(document_id)}
        if owner_id is not None:
            where = {"$and": [where, {"owner_id": int(owner_id)}]}
        updated = 0
        with self._write_lock:
            for name, collection in self._collections.items():
                try:
                    data = collection.get(where=where, include=["metadatas"])
                    ids = data.get("ids") or []
                    if not ids:
                        continue
                    metadatas = []
                    for metadata in data.get("metadatas") or []:
                        merged = dict(metadata or {})
                        merged.update({
                            key: value for key, value in updates.items()
                            if value is not None and isinstance(value, (str, int, float, bool))
                        })
                        metadatas.append(merged)
                    self._bm25[name].index.begin_operation({"where": where})
                    collection.update(ids=ids, metadatas=metadatas)
                    updated += len(ids)
                    if rebuild_indexes:
                        try:
                            self._sync_lexical_pending(name, collection)
                        except Exception:
                            print("[BM25] 元数据已更新，派生索引待增量修复")
                except Exception as exc:
                    print(f"更新 document_id={document_id} 元数据失败 ({name}): {exc}")
        return updated

    def rebuild_bm25_indexes(self) -> None:
        """Flush deferred document scopes; ready collections never reload text."""
        self._rebuild_bm25_indexes()

    def get_collection_stats(self) -> Dict[str, Any]:
        if not self._collections:
            return {"count": 0, "name": ""}
        total = 0
        names = []
        for name, collection in self._collections.items():
            names.append(name)
            try:
                total += collection.count()
            except Exception as e:
                print(f"获取统计失败: {e}")
        return {"count": total, "name": ",".join(names)}

    def clear(self) -> int:
        """清空所有 collection 及其 BM25，返回删除前总文档数。"""
        if not self._collections:
            return 0
        total_removed = 0
        for name, collection in self._collections.items():
            try:
                count_before = collection.count()
                if count_before == 0:
                    continue
                self._bm25[name].index.begin_operation({"where": None})
                removed = 0
                while removed < count_before:
                    ids = collection.get(limit=500, offset=0, include=[]).get("ids") or []
                    if not ids:
                        break
                    collection.delete(ids=ids); removed += len(ids)
                total_removed += removed
                self._sync_lexical_pending(name, collection)
            except Exception as e:
                print(f"清空集合失败: {e}")
        return total_removed

    def close(self) -> None:
        """Release this instance's native handles without resetting any data."""
        client = self._client
        self._client = None
        self._collections.clear()
        for store in self._bm25.values():
            store.close()
        self._bm25.clear()
        if client is not None and callable(getattr(client, "close", None)):
            client.close()


vector_store = ChromaVectorStore()
