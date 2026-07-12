"""测试 RAG 问答功能"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.rag.chain import rag_chain
from framework.vector_store.chroma_store import vector_store

def test_rag_chain_initialization():
    """测试 RAG 链初始化"""
    assert rag_chain is not None
    assert rag_chain.llm_service is not None
    assert rag_chain.vector_store is not None
    print("✓ RAG 链初始化成功")

def test_rag_chat_without_documents():
    """测试无文档时的 RAG 问答"""
    result = rag_chain.chat("测试问题")
    assert "answer" in result or "content" in result
    print("✓ 无文档 RAG 问答成功")

def test_vector_store_operations():
    """测试向量存储操作"""
    # 测试添加文档
    count = vector_store.add_documents(
        texts=["测试文档内容"],
        metadatas=[{"source": "test.pdf"}],
        ids=["test_doc_1"]
    )
    assert count == 1
    print("✓ 向量存储添加文档成功")

    # 测试搜索
    results = vector_store.search("测试", n_results=1)
    assert results["count"] >= 0
    print("✓ 向量存储搜索成功")

    # 测试统计
    stats = vector_store.get_collection_stats()
    assert "count" in stats
    print(f"✓ 向量存储统计成功: {stats}")

    # 清理测试数据
    vector_store.delete_by_source("test.pdf")
    print("✓ 向量存储清理成功")

def test_rag_with_context():
    """测试带上下文的 RAG 问答"""
    # 添加测试文档
    vector_store.add_documents(
        texts=["土壤酸化是指土壤pH值降低的过程"],
        metadatas=[{"source": "test_context.pdf"}],
        ids=["test_context_1"]
    )

    result = rag_chain.chat("什么是土壤酸化？")
    assert result is not None
    print("✓ 带上下文 RAG 问答成功")

    # 清理
    vector_store.delete_by_source("test_context.pdf")

if __name__ == "__main__":
    test_rag_chain_initialization()
    test_rag_chat_without_documents()
    test_vector_store_operations()
    test_rag_with_context()
    print("\n所有 RAG 问答功能测试通过！")
