from __future__ import annotations
import os
from typing import Any, Dict, Optional
from langchain_openai import ChatOpenAI
from framework.config import Config

class LLMService:
    DEFAULT_API_BASE = "https://api.siliconflow.cn/v1"

    def __init__(self):
        self._client = None
        self._initialized = False
        self._init_client()

    def _init_client(self):
        api_key = os.environ.get("SILICONFLOW_KEY") or os.environ.get("SILICONFLOW_API_KEY") or Config.SILICONFLOW_API_KEY
        api_base = os.environ.get("SILICONFLOW_API_BASE") or os.environ.get("SILICONFLOW_BASE_URL") or Config.SILICONFLOW_BASE_URL

        if api_key:
            try:
                self._client = ChatOpenAI(
                    model=Config.SILICONFLOW_CHAT_MODEL,
                    api_key=api_key,
                    base_url=api_base,
                    temperature=0.3,
                    max_tokens=2048,
                    timeout=30,
                )
                self._initialized = True
            except Exception as e:
                print(f"LLM初始化失败，将使用降级模式: {e}")
                self._initialized = False

    def is_available(self) -> bool:
        return self._initialized and self._client is not None

    def generate(
        self,
        prompt: str,
        messages: Optional[list] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if not self.is_available():
            return self._get_fallback_response(prompt)

        try:
            if messages:
                full_messages = messages.copy()
                full_messages.append({"role": "user", "content": prompt})
            else:
                full_messages = [{"role": "user", "content": prompt}]

            response = self._client.invoke(full_messages)
            content = response.content if hasattr(response, "content") else str(response)

            return {
                "success": True,
                "content": content,
                "model": Config.SILICONFLOW_CHAT_MODEL,
                "type": "llm",
            }
        except Exception as e:
            print(f"LLM调用失败，使用降级模式: {e}")
            return self._get_fallback_response(prompt)

    def _get_fallback_response(self, prompt: str) -> Dict[str, Any]:
        return {
            "success": False,
            "content": "",
            "model": "fallback",
            "type": "fallback",
            "message": "LLM服务不可用，将使用规则输出",
        }

llm_service = LLMService()