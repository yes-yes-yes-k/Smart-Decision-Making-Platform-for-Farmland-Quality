from __future__ import annotations
import os
import time
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

        tracing_enabled = os.environ.get("LANGCHAIN_TRACING_V2")
        langsmith_key = os.environ.get("LANGCHAIN_API_KEY")
        langsmith_project = os.environ.get("LANGCHAIN_PROJECT")
        
        print(f"[LLM] 初始化中 - Tracing V2: {tracing_enabled}, API Key: {'已配置' if langsmith_key else '未配置'}, Project: {langsmith_project}")

        if api_key:
            try:
                self._client = ChatOpenAI(
                    model=Config.SILICONFLOW_CHAT_MODEL,
                    api_key=api_key,
                    base_url=api_base,
                    temperature=0.3,
                    max_tokens=2048,
                    timeout=Config.SILICONFLOW_LLM_TIMEOUT,
                    max_retries=Config.SILICONFLOW_LLM_MAX_RETRIES,
                )
                self._initialized = True
                print(f"[LLM] 初始化成功 - 模型: {Config.SILICONFLOW_CHAT_MODEL}")
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

        started_at = time.perf_counter()
        print(
            f"[LLM] 调用开始 - 模型: {Config.SILICONFLOW_CHAT_MODEL}, "
            f"提示长度: {len(prompt)}, 历史消息: {len(messages or [])}",
            flush=True,
        )
        try:
            if messages:
                full_messages = messages.copy()
                full_messages.append({"role": "user", "content": prompt})
            else:
                full_messages = [{"role": "user", "content": prompt}]

            response = self._client.invoke(full_messages)
            content = response.content if hasattr(response, "content") else str(response)
            print(
                f"[LLM] 调用成功 - 耗时: {time.perf_counter() - started_at:.2f}s",
                flush=True,
            )

            return {
                "success": True,
                "content": content,
                "model": Config.SILICONFLOW_CHAT_MODEL,
                "type": "llm",
            }
        except Exception as e:
            print(
                f"[LLM] 调用失败 - 耗时: {time.perf_counter() - started_at:.2f}s, "
                f"错误: {type(e).__name__}: {e}；使用专业结果降级",
                flush=True,
            )
            return self._get_fallback_response(prompt)

    def _get_fallback_response(self, prompt: str) -> Dict[str, Any]:
        return {
            "success": False,
            "content": "抱歉，AI服务暂时不可用，请稍后重试。",
            "model": "fallback",
            "type": "fallback",
            "message": "LLM服务不可用，将使用规则输出",
        }

llm_service = LLMService()
