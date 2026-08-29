from __future__ import annotations
from typing import List, Optional, Dict

import jieba
from rank_bm25 import BM25Okapi


class BM25Store:
    """应用层 BM25 关键词索引，与 Chroma 无关但生命周期同步。

    取舍：写时全量重建（O(语料) 分词），换取正确性与实现简单。
    """

    def __init__(self):
        self._texts: List[str] = []
        self._sources: List[str] = []
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
            source = ""
            if i < len(metadatas) and metadatas[i]:
                source = metadatas[i].get("source", "")
            self._texts.append(text)
            self._sources.append(source)
        self._rebuild()
        return len(texts)

    def search(self, query: str, n_results: int = 20, filters: Optional[Dict] = None) -> List[Dict]:
        if not self._model:
            return []

        tokens = self._tokenize(query)
        scores = self._model.get_scores(tokens)

        allowed = None
        if filters and isinstance(filters.get("source"), dict) and "$in" in filters["source"]:
            allowed = set(filters["source"]["$in"])

        query_terms = set(tokens)
        scored = []
        for i, s in enumerate(scores):
            if allowed is not None and self._sources[i] not in allowed:
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
                "metadata": {"source": self._sources[i]},
                "score": float(s),
            })
        return results

    def delete_by_source(self, source: str) -> int:
        kept_texts, kept_sources = [], []
        removed = 0
        for text, src in zip(self._texts, self._sources):
            if src == source:
                removed += 1
            else:
                kept_texts.append(text)
                kept_sources.append(src)
        self._texts = kept_texts
        self._sources = kept_sources
        self._rebuild()
        return removed

    def clear(self) -> int:
        count = len(self._texts)
        self._texts = []
        self._sources = []
        self._model = None
        return count