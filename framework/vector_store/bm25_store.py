from __future__ import annotations
from typing import Any, List, Optional, Dict

import jieba
from rank_bm25 import BM25Okapi


class BM25Store:
    """应用层 BM25 关键词索引，与 Chroma 无关但生命周期同步。

    取舍：写时全量重建（O(语料) 分词），换取正确性与实现简单。
    """

    def __init__(self):
        self._texts: List[str] = []
        self._metadatas: List[Dict[str, Any]] = []
        self._model = None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return jieba.lcut(text)

    def _rebuild(self) -> None:
        if not self._texts:
            self._model = None
        else:
            self._model = BM25Okapi([self._tokenize(t) for t in self._texts])

    def add_documents(self, texts: List[str], metadatas: Optional[List[Dict]] = None) -> int:
        metadatas = metadatas or []
        for i, text in enumerate(texts):
            self._texts.append(text)
            metadata = metadatas[i] if i < len(metadatas) and metadatas[i] else {}
            self._metadatas.append(dict(metadata))
        self._rebuild()
        return len(texts)

    @staticmethod
    def _matches_filter(metadata: Dict[str, Any], filters: Optional[Dict]) -> bool:
        """Evaluate the small subset of Chroma filters used by the application."""
        if not filters:
            return True
        if "$and" in filters:
            return all(BM25Store._matches_filter(metadata, item) for item in filters["$and"])
        if "$or" in filters:
            return any(BM25Store._matches_filter(metadata, item) for item in filters["$or"])
        for key, expected in filters.items():
            actual = metadata.get(key)
            if isinstance(expected, dict):
                if "$in" in expected and actual not in set(expected["$in"]):
                    return False
                if "$eq" in expected and actual != expected["$eq"]:
                    return False
            elif actual != expected:
                return False
        return True

    def search(self, query: str, n_results: int = 20, filters: Optional[Dict] = None) -> List[Dict]:
        if not self._model:
            return []

        tokens = self._tokenize(query)
        scores = self._model.get_scores(tokens)

        query_terms = set(tokens)
        scored = []
        for i, s in enumerate(scores):
            if not self._matches_filter(self._metadatas[i], filters):
                continue
            # 小型语料下 BM25 idf 可能为 0（术语横跨半数文档），
            # 用词项交集过滤，避免把与查询无交集的文档也排进结果
            if not query_terms & set(self._tokenize(self._texts[i])):
                continue
            scored.append((s, i))
        scored.sort(key=lambda x: -x[0])

        results = []
        for s, i in scored[:n_results]:
            results.append({
                "content": self._texts[i],
                "metadata": dict(self._metadatas[i]),
                "score": float(s),
            })
        return results

    def delete_by_source(self, source: str) -> int:
        kept_texts, kept_metadatas = [], []
        removed = 0
        for text, metadata in zip(self._texts, self._metadatas):
            if metadata.get("source") == source:
                removed += 1
            else:
                kept_texts.append(text)
                kept_metadatas.append(metadata)
        self._texts = kept_texts
        self._metadatas = kept_metadatas
        self._rebuild()
        return removed

    def delete_by_document_id(self, document_id: int, owner_id: Optional[int] = None) -> int:
        kept_texts, kept_metadatas = [], []
        removed = 0
        for text, metadata in zip(self._texts, self._metadatas):
            same_document = metadata.get("document_id") == document_id
            same_owner = owner_id is None or metadata.get("owner_id") == owner_id
            if same_document and same_owner:
                removed += 1
            else:
                kept_texts.append(text)
                kept_metadatas.append(metadata)
        self._texts = kept_texts
        self._metadatas = kept_metadatas
        self._rebuild()
        return removed

    def clear(self) -> int:
        count = len(self._texts)
        self._texts = []
        self._metadatas = []
        self._model = None
        return count
