from __future__ import annotations
from langchain_core.tools import Tool
from framework.function_calling.registry import tool_registry
from framework.vector_store.chroma_store import vector_store

def document_search(query: str, n_results: int = 3) -> str:
    results = vector_store.search(query=query, n_results=n_results)
    if results["count"] == 0:
        return "未找到相关文档"

    formatted_results = []
    for i, result in enumerate(results["results"]):
        metadata = result.get("metadata", {})
        source = metadata.get("source", "unknown")
        content = result.get("content", "")[:300]
        formatted_results.append(f"文档{i+1}({source}): {content}")

    return "\n\n".join(formatted_results)

document_search_tool = Tool(
    name="document_search",
    func=document_search,
    description="搜索知识库中的相关文档，用于回答用户问题时查找参考资料",
)

tool_registry.register("document_search", document_search_tool)