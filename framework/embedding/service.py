from __future__ import annotations
import os
from typing import List
from langchain_openai import OpenAIEmbeddings
from framework.config import Config

class EmbeddingService:
    DEFAULT_API_BASE = "https://api.siliconflow.cn/v1"

    def __init__(self):
        self._embeddings = None
        self._initialized = False
        self._init_embeddings()

    def _init_embeddings(self):
        api_key = os.environ.get("SILICONFLOW_KEY") or os.environ.get("SILICONFLOW_API_KEY") or Config.SILICONFLOW_API_KEY
        api_base = os.environ.get("SILICONFLOW_API_BASE") or os.environ.get("SILICONFLOW_BASE_URL") or Config.SILICONFLOW_BASE_URL

        if api_key:
            try:
                self._embeddings = OpenAIEmbeddings(
                    model=Config.SILICONFLOW_EMBED_MODEL,
                    api_key=api_key,
                    base_url=api_base,
                    timeout=30,
                )
                self._initialized = True
            except Exception as e:
                print(f"Embedding初始化失败，将使用关键词匹配降级模式: {e}")
                self._initialized = False

    def is_available(self) -> bool:
        return self._initialized and self._embeddings is not None

    def embed_query(self, text: str) -> List[float]:
        if not self.is_available():
            return []

        try:
            return self._embeddings.embed_query(text)
        except Exception as e:
            print(f"Embedding查询失败，使用降级模式: {e}")
            return []

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not self.is_available():
            return [[] for _ in texts]

        try:
            return self._embeddings.embed_documents(texts)
        except Exception as e:
            print(f"Embedding批量查询失败，使用降级模式: {e}")
            return [[] for _ in texts]

embedding_service = EmbeddingService()