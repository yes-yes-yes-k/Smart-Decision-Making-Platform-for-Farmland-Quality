from __future__ import annotations
from typing import List, Dict

import requests

from framework.config import Config


class RerankService:
    """SiliconFlow BGE-Reranker 精排，与 embedding/service.py 同栈（requests 直连）。"""

    def is_available(self) -> bool:
        return bool(Config.RERANK_ENABLED and Config.SILICONFLOW_API_KEY)

    def rerank(self, query: str, candidates: List[Dict]) -> List[Dict]:
        if not self.is_available() or not candidates:
            return candidates

        top_n = min(len(candidates), Config.RETRIEVAL_TOP_K)
        try:
            resp = requests.post(
                f"{Config.SILICONFLOW_BASE_URL}/rerank",
                headers={
                    "Authorization": f"Bearer {Config.SILICONFLOW_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": Config.RERANK_MODEL,
                    "query": query,
                    "documents": [c.get("content", "") for c in candidates],
                    "top_n": top_n,
                },
                timeout=Config.RERANK_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            items = sorted(
                data.get("results", []),
                key=lambda x: x.get("relevance_score", 0.0),
                reverse=True,
            )
            ranked = [candidates[item["index"]] for item in items
                      if 0 <= item.get("index", -1) < len(candidates)]
            return ranked if ranked else candidates
        except Exception as e:
            print(f"[Rerank] API 调用失败，降级原顺序: {e}")
            return candidates


rerank_service = RerankService()