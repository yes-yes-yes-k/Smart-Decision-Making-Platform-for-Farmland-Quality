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

    def generate_stream(
        self,
        prompt: str,
        messages: Optional[list] = None,
        **kwargs,
    ):
        if not self.is_available():
            yield "抱歉，AI服务暂时不可用，请稍后重试。"
            return

        started_at = time.perf_counter()
        print(
            f"[LLM] 流式调用开始 - 模型: {Config.SILICONFLOW_CHAT_MODEL}, "
            f"提示长度: {len(prompt)}, 历史消息: {len(messages or [])}",
            flush=True,
        )
        try:
            if messages:
                full_messages = messages.copy()
                full_messages.append({"role": "user", "content": prompt})
            else:
                full_messages = [{"role": "user", "content": prompt}]

            for chunk in self._client.stream(full_messages):
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if content:
                    yield content

            print(
                f"[LLM] 流式调用成功 - 耗时: {time.perf_counter() - started_at:.2f}s",
                flush=True,
            )
        except Exception as e:
            print(
                f"[LLM] 流式调用失败 - 耗时: {time.perf_counter() - started_at:.2f}s, "
                f"错误: {type(e).__name__}: {e}",
                flush=True,
            )
            yield "抱歉，AI服务暂时不可用，请稍后重试。"

    def generate_with_tools(
        self,
        prompt: str,
        messages: Optional[list] = None,
        tools: Optional[list] = None,
        tool_choice: str = "auto",
        default_args: Optional[Dict[str, Any]] = None,
        max_iterations: Optional[int] = None,
        trace_id: Optional[str] = None,
        restrict_tools: bool = False,
    ) -> Dict[str, Any]:
        """带工具调用的生成（function calling）。

        若 tools 为空或 LLM 不可用 → 退化为 generate()。
        若 bind_tools 不支持 → 返回 success=False 让调用方 fallback。
        否则构造 ToolCallingLoop 执行多轮工具调用。
        """
        if not self.is_available() or not tools:
            return self.generate(prompt, messages)

        if not getattr(Config, "SILICONFLOW_SUPPORTS_TOOL_CALLING", True):
            return {"success": False, "reason": "bind_tools_disabled"}

        try:
            bound = self._client.bind_tools(tools, tool_choice=tool_choice)
        except (TypeError, AttributeError) as e:
            print(f"[LLM] bind_tools 不支持: {type(e).__name__}: {e}", flush=True)
            return {"success": False, "reason": "bind_tools_unsupported", "error": str(e)}

        from framework.function_calling.tool_loop import ToolCallingLoop

        max_iter = max_iterations or getattr(Config, "FUNCTION_CALLING_MAX_ITERATIONS", 3)
        loop = ToolCallingLoop(
            llm=bound,
            max_iterations=max_iter,
            default_args=default_args or {},
            trace_id=trace_id,
            allowed_tool_names={tool.name for tool in tools} if restrict_tools else None,
        )
        started_at = time.perf_counter()
        print(
            f"[LLM] 工具调用开始 - 模型: {Config.SILICONFLOW_CHAT_MODEL}, "
            f"工具数: {len(tools)}, 最大迭代: {max_iter}, trace: {trace_id}",
            flush=True,
        )
        result = loop.run(prompt, messages)
        elapsed = time.perf_counter() - started_at
        print(f"[LLM] 工具调用结束 - 耗时: {elapsed:.2f}s", flush=True)
        return result

    def _get_fallback_response(self, prompt: str) -> Dict[str, Any]:
        return {
            "success": False,
            "content": "抱歉，AI服务暂时不可用，请稍后重试。",
            "model": "fallback",
            "type": "fallback",
            "message": "LLM服务不可用，将使用规则输出",
        }

llm_service = LLMService()
