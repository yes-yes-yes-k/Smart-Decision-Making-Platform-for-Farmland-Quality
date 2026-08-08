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
        return self._call_api([text])[0] if self._call_api([text]) else []

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not self.is_available():
            return [[] for _ in texts]
        return self._call_api(texts)

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        """调用 SiliconFlow /v1/embeddings 接口"""
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
