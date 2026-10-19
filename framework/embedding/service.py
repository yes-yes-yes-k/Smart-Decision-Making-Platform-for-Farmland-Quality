from __future__ import annotations
import os
from typing import List
import requests
from framework.config import Config


class EmbeddingService:
    """通过 SiliconFlow API 进行文本向量化，不依赖 langchain_openai"""

    DEFAULT_API_BASE = "https://api.siliconflow.cn/v1"

    def __init__(self):
        self._api_key = None
        self._api_base = None
        self._model = None
        self._batch_size = 32
        self._initialized = False
        self._init_embeddings()

    def _init_embeddings(self):
        self._api_key = (
            os.environ.get("SILICONFLOW_KEY")
            or os.environ.get("SILICONFLOW_API_KEY")
            or getattr(Config, "SILICONFLOW_API_KEY", "")
        )
        self._api_base = (
            os.environ.get("SILICONFLOW_API_BASE")
            or os.environ.get("SILICONFLOW_BASE_URL")
            or getattr(Config, "SILICONFLOW_BASE_URL", self.DEFAULT_API_BASE)
        )
        self._model = getattr(Config, "SILICONFLOW_EMBED_MODEL", "BAAI/bge-m3")
        self._batch_size = max(
            1, int(getattr(Config, "SILICONFLOW_EMBED_BATCH_SIZE", 32))
        )

        if self._api_key:
            self._initialized = True
        else:
            print("[Embedding] 未配置 SILICONFLOW_API_KEY，向量化不可用")
            self._initialized = False

    def is_available(self) -> bool:
        return self._initialized

    def embed_query(self, text: str) -> List[float]:
        if not self.is_available():
            return []
        if not isinstance(text, str):
            return []
        vectors = self._call_api([text])
        return vectors[0] if vectors else []

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not self.is_available():
            return [[] for _ in texts]
        if texts is None or len(texts) == 0:
            return []
        total = len(texts)
        valid: List[tuple] = []
        for idx, t in enumerate(texts):
            if isinstance(t, str):
                valid.append((idx, t))
        if not valid:
            return [[] for _ in range(total)]
        indices = [i for i, _ in valid]
        cleaned = [t for _, t in valid]
        batch_size = max(1, int(getattr(self, "_batch_size", 32)))
        api_result: List[List[float]] = []
        for start in range(0, len(cleaned), batch_size):
            batch = cleaned[start:start + batch_size]
            batch_result = self._call_api(batch)
            # A partial API response must fail the whole logical write. The
            # vector store checks for empty vectors and will not persist a
            # partially embedded document.
            if len(batch_result) != len(batch):
                return [[] for _ in range(total)]
            api_result.extend(batch_result)
        result: List[List[float]] = [[] for _ in range(total)]
        for slot, vec in zip(indices, api_result):
            result[slot] = vec
        return result

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        """调用 SiliconFlow /v1/embeddings 接口，texts 必须全为非空字符串列表。"""
        if not texts:
            return []
        try:
            resp = requests.post(
                f"{self._api_base}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "input": texts,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            # API 返回 { data: [ { embedding: [...] }, ... ] }
            return [item["embedding"] for item in data.get("data", [])]
        except Exception as e:
            print(f"[Embedding] API 调用失败: {e}")
            return [[] for _ in texts]


embedding_service = EmbeddingService()
