from __future__ import annotations
from typing import Dict, Any, Callable, Optional
from langchain_core.tools import Tool
from framework.function_calling.registry import tool_registry

class CustomTool:
    def __init__(self, name: str, description: str, schema: Dict[str, Any], func: Callable):
        self.name = name
        self.description = description
        self.schema = schema
        self.func = func

def register_custom_tool(tool: CustomTool) -> None:
    def tool_wrapper(**kwargs):
        return tool.func(**kwargs)

    langchain_tool = Tool(
        name=tool.name,
        func=tool_wrapper,
        description=tool.description,
    )

    tool_registry.register(tool.name, langchain_tool, tool.schema)
