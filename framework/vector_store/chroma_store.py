from __future__ import annotations
import os
import re
import uuid
from typing import Optional, List, Dict, Any
import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from chromadb.config import Settings
from framework.config import Config
from framework.embedding.service import embedding_service
from framework.vector_store.bm25_store import BM25Store


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

    def _rebuild_bm25_indexes(self) -> None:
        """Restore the in-memory BM25 sidecar from persisted Chroma documents."""
        self._bm25 = {}
        for name, collection in self._collections.items():
            store = BM25Store()
            try:
                data = collection.get(include=["documents", "metadatas"])
                documents = data.get("documents") or []
                metadatas = data.get("metadatas") or []
                if documents:
                    store.add_documents(documents, metadatas)
            except Exception as exc:
                print(f"[BM25] 集合 {name} 重建失败: {exc}")
            self._bm25[name] = store

    def _get_collection(self, category: Optional[str] = None):
        """按 category 懒创建/获取 collection（空/other → 默认 enterprise_kb）。"""
        name = collection_name_for(category)
        if name not in self._collections:
            collection = self._client.get_or_create_collection(
                name=name, embedding_function=NoOpEmbeddingFunction())
            self._collections[name] = collection
            self._bm25.setdefault(name, BM25Store())
        return self._collections[name]

    def _targeted_collection(self, category: Optional[str] = None):
        """category 具体且对应 collection 已存在 → 返回；否则 None（全库回退）。"""
        if not category or category.strip().lower() == "other":
            return None
        return self._collections.get(collection_name_for(category))

    def _bm25_for(self, category: Optional[str] = None) -> BM25Store:
        """按 category 懒获取 BM25 索引（空/other → 默认）。"""
        name = collection_name_for(category)
        if name not in self._bm25:
            self._bm25[name] = BM25Store()
        return self._bm25[name]

    def add_documents(self, texts: List[str], metadatas: Optional[List[Dict]] = None,
                      ids: Optional[List[str]] = None, category: Optional[str] = None) -> int:
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

            collection = self._get_collection(category)
            existing = collection.get(ids=resolved_ids, include=["metadatas"])
            if existing.get("ids"):
                print(f"[Chroma] 检测到重复文档 ID，拒绝整批写入: {existing['ids']}")
                return 0

            count_before = collection.count()
            collection.add(
                ids=resolved_ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=clean_metadatas,
            )
            added_count = collection.count() - count_before
            if added_count != len(texts):
                print(
                    f"[Chroma] 写入数量不一致: expected={len(texts)} actual={added_count}"
                )
                return 0
            self._bm25_for(category).add_documents(texts, clean_metadatas)
            return added_count
        except Exception as e:
            print(f"添加文档失败: {e}")
            return 0

    def _search_in(self, collection, query: str, n_results: int,
                   filters: Optional[Dict]) -> List[Dict]:
        """对单个 collection 做向量召回，返回 [{content, metadata, distance}...]。"""
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
            return {"results": [], "count": 0}

        if not embedding_service.is_available():
            print("[Chroma] embedding_service 不可用，无法搜索")
            return {"results": [], "count": 0}

        try:
            target = self._targeted_collection(category)
            if target is not None:
                formatted = self._search_in(target, query, n_results, filters)
            else:
                formatted = []
                for collection in self._collections.values():
                    formatted.extend(self._search_in(collection, query, n_results, filters))
                # 全库回退：向量距离越小越相关，升序取 top-n
                formatted.sort(key=lambda r: r.get("distance", 0))
                formatted = formatted[:n_results]
            return {"results": formatted, "count": len(formatted)}
        except Exception as e:
            print(f"搜索失败: {e}")
            return {"results": [], "count": 0}

    def hybrid_search(self, query: str, n_results: int = 20, filters: Optional[Dict] = None,
                      category: Optional[str] = None) -> Dict[str, Any]:
        """双路召回：向量 + BM25，RRF 融合（支持 category 定向，否则全库回退）。

        Config.HYBRID_SEARCH_ENABLED=False 时回退纯向量单路（回滚路径）。
        """
        if not Config.HYBRID_SEARCH_ENABLED:
            return self.search(query, n_results, filters, category)

        vector_res = self.search(query, n_results, filters, category)
        bm25_docs = self._bm25_search(query, n_results, filters, category)
        fused = self._rrf_fuse(vector_res["results"], bm25_docs, k=Config.RRF_K)
        fused = fused[:n_results]
        return {"results": fused, "count": len(fused)}

    def _bm25_search(self, query: str, n_results: int, filters: Optional[Dict],
                     category: Optional[str] = None) -> List[Dict]:
        """BM25 召回：category 定向时单库；否则聚合所有分领域 BM25 后取 top-n。"""
        if self._targeted_collection(category) is not None:
            return self._bm25_for(category).search(query, n_results, filters)
        all_docs: List[Dict] = []
        for store in self._bm25.values():
            all_docs.extend(store.search(query, n_results, filters))
        all_docs.sort(key=lambda d: -d.get("score", 0.0))
        return all_docs[:n_results]

    @staticmethod
    def _rrf_fuse(vector_docs: List[Dict], bm25_docs: List[Dict], k: int = 60) -> List[Dict]:
        """RRF 融合：以 (source, content) 为键去重并累加倒数排名分。"""
        score: Dict[tuple, float] = {}
        docref: Dict[tuple, Dict] = {}
        for rank, d in enumerate(vector_docs):
            key = (d.get("metadata", {}).get("source"), d.get("content"))
            score[key] = score.get(key, 0.0) + 1.0 / (k + rank + 1)
            docref[key] = d
        for rank, d in enumerate(bm25_docs):
            key = (d.get("metadata", {}).get("source"), d.get("content"))
            score[key] = score.get(key, 0.0) + 1.0 / (k + rank + 1)
            docref[key] = d
        return [docref[k] for k, _ in sorted(score.items(), key=lambda kv: -kv[1])]

    def delete_by_source(self, source_doc_name: str) -> int:
        """从所有 collection 删除指定 source 的文档，并同步各 BM25。"""
        if not self._collections:
            return 0
        total_removed = 0
        for collection in self._collections.values():
            try:
                count_before = collection.count()
                collection.delete(where={"source": source_doc_name})
                count_after = collection.count()
                total_removed += count_before - count_after
            except Exception as e:
                print(f"删除失败: {e}")
        for store in self._bm25.values():
            try:
                store.delete_by_source(source_doc_name)
            except Exception as e:
                print(f"BM25 删除失败: {e}")
        return total_removed

    def delete_by_document_id(self, document_id: int, owner_id: Optional[int] = None) -> int:
        """Delete one logical document without affecting same-named documents."""
        if not self._collections:
            return 0
        where: Dict[str, Any] = {"document_id": document_id}
        if owner_id is not None:
            where = {"$and": [where, {"owner_id": owner_id}]}
        total_removed = 0
        for name, collection in self._collections.items():
            try:
                count_before = collection.count()
                collection.delete(where=where)
                total_removed += count_before - collection.count()
            except Exception as exc:
                print(f"删除 document_id={document_id} 失败 ({name}): {exc}")
        for store in self._bm25.values():
            store.delete_by_document_id(document_id, owner_id)
        return total_removed

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
        for collection in self._collections.values():
            try:
                count_before = collection.count()
                if count_before == 0:
                    continue
                all_data = collection.get()
                ids = all_data.get("ids", [])
                if ids:
                    collection.delete(ids=ids)
                total_removed += count_before
            except Exception as e:
                print(f"清空集合失败: {e}")
        for store in self._bm25.values():
            store.clear()
        return total_removed


vector_store = ChromaVectorStore()
