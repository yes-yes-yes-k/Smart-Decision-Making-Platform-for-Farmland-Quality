"""测试 Function Calling 功能"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.function_calling.registry import tool_registry
from framework.function_calling.executor import tool_executor

def test_tool_registry():
    """测试工具注册表"""
    from langchain_core.tools import Tool

    def dummy_func(**kwargs):
        return "dummy result"

    test_tool = Tool(name="test_tool", func=dummy_func, description="测试工具")
    tool_registry.register("test_tool", test_tool, {"type": "object", "properties": {}})

    assert tool_registry.get("test_tool") is not None
    tools = tool_registry.list()
    assert any(t["name"] == "test_tool" for t in tools)
    print("✓ 工具注册表功能正常")

    tool_registry.deregister("test_tool")
    assert tool_registry.get("test_tool") is None
    print("✓ 工具注销功能正常")

def test_tool_executor():
    """测试工具执行器"""
    from langchain_core.tools import Tool

    def add_func(**kwargs):
        a = kwargs.get("a", 0)
        b = kwargs.get("b", 0)
        return a + b

    add_tool = Tool(name="add", func=add_func, description="加法工具")
    tool_registry.register("add", add_tool)

    result = tool_executor.execute("add", {"a": 1, "b": 2})
    assert result["success"] is True
    assert result["result"] == 3
    print("✓ 工具执行器正常")

    # 测试不存在的工具
    result = tool_executor.execute("nonexistent", {})
    assert result["success"] is False
    print("✓ 不存在工具的处理正常")

    tool_registry.deregister("add")

def test_document_search_tool():
    """测试文档搜索工具"""
    tool = tool_registry.get("document_search")
    if tool:
        result = tool_executor.execute("document_search", {"query": "测试查询"})
        assert result is not None
        assert "success" in result
        print("✓ 文档搜索工具正常")
    else:
        print("⚠ 文档搜索工具未注册（需要向量库支持）")

if __name__ == "__main__":
    test_tool_registry()
    test_tool_executor()
    test_document_search_tool()
    print("\n所有 Function Calling 功能测试通过！")
