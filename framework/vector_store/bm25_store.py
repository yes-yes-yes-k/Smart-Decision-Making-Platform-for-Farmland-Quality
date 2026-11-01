"""BM25-compatible interface backed by a persistent, incremental FTS5 index."""
import hashlib
import json
from pathlib import Path
import tempfile

from .lexical_index import LexicalIndex, tokenize


class BM25Store:
    def __init__(self, path=None, collection="default"):
        self._temporary = tempfile.TemporaryDirectory(prefix="knowledge-lexical-") if path is None else None
        self.index = LexicalIndex(path or Path(self._temporary.name)/"index.sqlite3", collection)

    @staticmethod
    def _tokenize(text):
        return tokenize(text)

    def add_documents(self, texts, metadatas=None, ids=None):
        metas = metadatas or [{} for _ in texts]
        if len(metas) != len(texts) or (ids is not None and len(ids) != len(texts)):
            raise ValueError("lexical_document_batch_alignment")
        values = []
        for index, (text, meta) in enumerate(zip(texts, metas)):
            if not isinstance(text, str) or not text.strip():
                raise ValueError("lexical_nonempty_text_required")
            identity = ids[index] if ids is not None else hashlib.sha256(json.dumps(
                {"text": text, "metadata": meta}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            values.append((identity, text, meta))
            if len(values) == 500:
                self.index.upsert(values); values = []
        if values:
            self.index.upsert(values)
        self.index.mark_ready()
        return len(texts)

    @staticmethod
    def _matches_filter(metadata, filters):
        if not filters:
            return True
        for key, expected in filters.items():
            if key in ("$and", "$or"):
                matched = [BM25Store._matches_filter(metadata, item) for item in expected]
                if not (all(matched) if key == "$and" else any(matched)):
                    return False
                continue
            actual = metadata.get(key)
            operations = expected if isinstance(expected, dict) else {"$eq": expected}
            for operation,value in operations.items():
                if operation == "$in": valid = actual in value
                elif operation == "$nin": valid = actual not in value
                elif operation == "$eq": valid = actual == value
                elif operation == "$ne": valid = actual != value
                elif operation in ("$gt", "$gte", "$lt", "$lte"):
                    try: valid = {"$gt": lambda: actual > value, "$gte": lambda: actual >= value, "$lt": lambda: actual < value, "$lte": lambda: actual <= value}[operation]()
                    except TypeError: valid = False
                else: raise ValueError("unsupported_lexical_filter_operator")
                if not valid: return False
        return True

    def search(self, query, n_results=20, filters=None, *, concept_groups=None):
        return self.index.search(query, n_results, filters, concept_groups=concept_groups)

    def delete_by_source(self, source):
        return self.index.delete({"source": source})

    def delete_by_document_id(self, document_id, owner_id=None):
        where = {"document_id": document_id}
        if owner_id is not None:
            where = {"$and": [where, {"owner_id": owner_id}]}
        return self.index.delete(where)

    def clear(self):
        return self.index.clear()

    def close(self):
        if self._temporary is not None:
            self._temporary.cleanup()

    def __del__(self):
        try:
            self.close()
        except OSError:
            pass
