from __future__ import annotations
import os
import shutil
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


class ChromaVectorStore:
    def __init__(self):
        self._client = None
        self._collection = None
        self._bm25 = BM25Store()
        self._init_client()

    def _init_client(self):
        persist_dir = os.path.abspath(Config.CHROMA_PERSIST_DIR)
        collection_name = Config.CHROMA_COLLECTION_NAME

        os.makedirs(persist_dir, exist_ok=True)

        try:
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=False,
                )
            )

            need_recreate = False
            try:
                existing = self._client.get_collection(name=collection_name)
                existing_ef = None
                if hasattr(existing, 'metadata') and existing.metadata:
                    existing_ef = existing.metadata.get("embedding_function", None)
                print(f"[Chroma] 检测到旧集合，embedding_function={existing_ef}")
                if existing_ef != "noop":
                    print(f"[Chroma] 需要重建集合以使用自定义 embedding function")
                    need_recreate = True
            except Exception:
                print(f"[Chroma] 集合不存在或无法读取，将直接创建")
                pass

            if need_recreate:
                try:
                    self._client.delete_collection(name=collection_name)
                    print(f"[Chroma] 旧集合已删除")
                except Exception as e:
                    print(f"[Chroma] 删除旧集合失败: {e}，尝试删除整个持久化目录")
                    try:
                        shutil.rmtree(persist_dir, ignore_errors=True)
                        os.makedirs(persist_dir, exist_ok=True)
                        self._client = chromadb.PersistentClient(
                            path=persist_dir,
                            settings=Settings(
                                anonymized_telemetry=False,
                                allow_reset=False,
                            )
                        )
                        print(f"[Chroma] 持久化目录已清理")
                    except Exception as e2:
                        print(f"[Chroma] 删除持久化目录失败: {e2}")

            try:
                self._collection = self._client.create_collection(
                    name=collection_name,
                    embedding_function=NoOpEmbeddingFunction(),
                )
                print(f"[Chroma] 集合 '{collection_name}' 初始化完成")
            except Exception as e:
                # 创建失败，常见于旧版本 ChromaDB 写入的元数据不兼容
                # （如 KeyError: '_type'）。清理持久化目录后重试一次。
                print(f"[Chroma] 创建集合失败: {e}，清理持久化目录后重试")
                try:
                    # 先释放旧 client，避免 Windows 文件锁导致 rmtree 不彻底
                    self._client = None
                    shutil.rmtree(persist_dir, ignore_errors=True)
                    os.makedirs(persist_dir, exist_ok=True)
                    self._client = chromadb.PersistentClient(
                        path=persist_dir,
                        settings=Settings(
                            anonymized_telemetry=False,
                            allow_reset=False,
                        )
                    )
                    self._collection = self._client.create_collection(
                        name=collection_name,
                        embedding_function=NoOpEmbeddingFunction(),
                    )
                    print(f"[Chroma] 集合 '{collection_name}' 初始化完成（已重建持久化目录）")
                except Exception as e2:
                    print(f"Chroma初始化失败: {e2}")
                    self._collection = None
        except Exception as e:
            print(f"Chroma初始化失败: {e}")
            import traceback
            traceback.print_exc()

    def add_documents(self, texts: List[str], metadatas: Optional[List[Dict]] = None, ids: Optional[List[str]] = None) -> int:
        """添加文档到向量库，直接使用 embedding_service 获取 embeddings，
        不依赖 ChromaDB 的 embedding_function（避免触发 ONNX 下载）。"""
        if not self._collection:
            return 0

        if not embedding_service.is_available():
            print("[Chroma] embedding_service 不可用，跳过向量化")
            return 0

        try:
            # 直接获取 embeddings，不通过 ChromaDB 的 embedding_function
            embeddings = embedding_service.embed_documents(texts)

            self._collection.add(
                ids=ids or [f"doc_{i}" for i in range(len(texts))],
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas or [],
            )
            self._bm25.add_documents(texts, metadatas)
            return len(texts)
        except Exception as e:
            print(f"添加文档失败: {e}")
            return 0

    def search(self, query: str, n_results: int = 3, filters: Optional[Dict] = None) -> Dict[str, Any]:
        if not self._collection:
            return {"results": [], "count": 0}

        if not embedding_service.is_available():
            print("[Chroma] embedding_service 不可用，无法搜索")
            return {"results": [], "count": 0}

        try:
            query_embedding = embedding_service.embed_query(query)

            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=filters,
            )

            formatted_results = []
            for i in range(len(results.get("documents", []))):
                docs = results["documents"][i]
                metadatas = results.get("metadatas", [[]])[i]
                distances = results.get("distances", [[]])[i]

                for j, doc in enumerate(docs):
                    formatted_results.append({
                        "content": doc,
                        "metadata": metadatas[j] if j < len(metadatas) else {},
                        "distance": distances[j] if j < len(distances) else 0,
                    })

            return {
                "results": formatted_results,
                "count": len(formatted_results),
            }
        except Exception as e:
            print(f"搜索失败: {e}")
            return {"results": [], "count": 0}

    def hybrid_search(self, query: str, n_results: int = 20, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """双路召回：向量 + BM25，RRF 融合去重后取 top-n。

        Config.HYBRID_SEARCH_ENABLED=False 时回退纯向量单路（回滚路径）。
        """
        if not Config.HYBRID_SEARCH_ENABLED:
            return self.search(query, n_results, filters)

        vector_res = self.search(query, n_results, filters)
        bm25_docs = self._bm25.search(query, n_results, filters)
        fused = self._rrf_fuse(vector_res["results"], bm25_docs, k=Config.RRF_K)
        fused = fused[:n_results]
        return {"results": fused, "count": len(fused)}

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
        if not self._collection:
            return 0

        try:
            count_before = self._collection.count()
            self._collection.delete(where={"source": source_doc_name})
            count_after = self._collection.count()
            self._bm25.delete_by_source(source_doc_name)
            return count_before - count_after
        except Exception as e:
            print(f"删除失败: {e}")
            return 0

    def get_collection_stats(self) -> Dict[str, Any]:
        if not self._collection:
            return {"count": 0, "name": ""}

        try:
            return {
                "count": self._collection.count(),
                "name": self._collection.name,
            }
        except Exception as e:
            print(f"获取统计失败: {e}")
            return {"count": 0, "name": ""}

    def clear(self) -> int:
        """清空集合中的所有文档，返回删除前的文档数"""
        if not self._collection:
            return 0
        try:
            count_before = self._collection.count()
            if count_before == 0:
                self._bm25.clear()
                return 0
            all_data = self._collection.get()
            ids = all_data.get("ids", [])
            if ids:
                self._collection.delete(ids=ids)
            self._bm25.clear()
            return count_before
        except Exception as e:
            print(f"清空集合失败: {e}")
            return 0

vector_store = ChromaVectorStore()
