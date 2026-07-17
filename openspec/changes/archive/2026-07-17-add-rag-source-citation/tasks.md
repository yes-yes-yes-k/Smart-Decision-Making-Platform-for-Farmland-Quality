# Tasks: add-rag-source-citation

- [x] 修改 `_build_prompt` 方法，在 prompt 中增加文档来源引用指示
- [x] 验证 RAG 回答中包含文档来源引用
- [x] 创建 `scripts/reindex_documents.py`，将 uploads/ 中的 PDF 重新索引到向量存储
- [x] 修改 RAG 回退行为：无本地文档时明确告知用户，优先使用本地知识库
- [x] 验证重新索引后 RAG 回答包含 sources
