from __future__ import annotations
from typing import Dict, Any, List, Optional
from framework.function_calling.registry import tool_registry

class ToolExecutor:
    def __init__(self):
        self._registry = tool_registry

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._registry.get(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"工具 {tool_name} 未注册",
            }

        try:
            result = tool.run(**arguments)
            return {
                "success": True,
                "result": result,
                "tool_name": tool_name,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"工具执行失败: {str(e)}",
                "tool_name": tool_name,
            }

    def execute_batch(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for tool_info in tools:
            tool_name = tool_info.get("name")
            arguments = tool_info.get("arguments", {})
            result = self.execute(tool_name, arguments)
            results.append(result)
        return results

tool_executor = ToolExecutor()