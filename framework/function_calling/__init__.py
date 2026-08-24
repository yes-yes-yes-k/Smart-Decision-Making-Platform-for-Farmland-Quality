"""Function calling 模块：工具注册表 + 执行器 + 多轮调用循环。

import 本包时自动注册所有工具（document_search + 5 个专题工具）。
"""
from .registry import tool_registry, ToolRegistry
from .executor import tool_executor, ToolExecutor
from .tool_loop import ToolCallingLoop

# 触发注册副作用：document_search + 5 个专题工具
from . import langchain_tools  # noqa: F401
from . import specialized_tools  # noqa: F401

__all__ = [
    "tool_registry",
    "ToolRegistry",
    "tool_executor",
    "ToolExecutor",
    "ToolCallingLoop",
]
