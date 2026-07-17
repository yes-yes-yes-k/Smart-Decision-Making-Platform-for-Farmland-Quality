from __future__ import annotations
import os
from typing import Optional, List, Dict, Any
import chromadb
from chromadb.config import Settings
from framework.config import Config
from framework.embedding.service import embedding_service

class ChromaVectorStore:
    def __init__(self):
        self._client = None
        self._collection = None
        self._init_client()

    def _init_client(self):
        persist_dir = Config.CHROMA_PERSIST_DIR
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
            self._collection = self._client.get_or_create_collection(name=collection_name)
        except Exception as e:
            print(f"Chroma初始化失败: {e}")

    def add_documents(self, texts: List[str], metadatas: Optional[List[Dict]] = None, ids: Optional[List[str]] = None) -> int:
        if not self._collection:
            return 0

        try:
            self._collection.add(
                documents=texts,
                metadatas=metadatas or [],
                ids=ids or [f"doc_{i}" for i in range(len(texts))]
            )
            return len(texts)
        except Exception as e:
            print(f"添加文档失败: {e}")
            return 0

    def search(self, query: str, n_results: int = 3, filters: Optional[Dict] = None) -> Dict[str, Any]:
        if not self._collection:
            return {"results": [], "count": 0}

        try:
            results = self._collection.query(
                query_texts=[query],
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

    def delete_by_source(self, source_doc_name: str) -> int:
        if not self._collection:
            return 0

        try:
            count_before = self._collection.count()
            self._collection.delete(where={"source": source_doc_name})
            count_after = self._collection.count()
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
                return 0
            # 获取所有 id 然后删除
            all_data = self._collection.get()
            ids = all_data.get("ids", [])
            if ids:
                self._collection.delete(ids=ids)
            return count_before
        except Exception as e:
            print(f"清空集合失败: {e}")
            return 0

vector_store = ChromaVectorStore()