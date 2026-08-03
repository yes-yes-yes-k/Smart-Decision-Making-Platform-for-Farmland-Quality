from __future__ import annotations
from typing import Dict, Optional, Any, List
from langchain_core.tools import Tool

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, tool: Tool, schema: Optional[Dict] = None) -> None:
        self._tools[name] = {
            "tool": tool,
            "schema": schema or tool.args if hasattr(tool, 'args') else None,
        }

    def get(self, name: str) -> Optional[Tool]:
        entry = self._tools.get(name)
        return entry["tool"] if entry else None

    def list(self) -> List[Dict[str, Any]]:
        tools_info = []
        for name, entry in self._tools.items():
            tool = entry["tool"]
            tools_info.append({
                "name": name,
                "description": tool.description if hasattr(tool, 'description') else "",
                "schema": entry.get("schema", {}),
            })
        return tools_info

    def deregister(self, name: str) -> None:
        if name in self._tools:
            del self._tools[name]

    def get_all(self) -> Dict[str, Tool]:
        return {name: entry["tool"] for name, entry in self._tools.items()}

tool_registry = ToolRegistry()
