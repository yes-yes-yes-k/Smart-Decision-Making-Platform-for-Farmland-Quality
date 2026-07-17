# Proposal: add-rag-source-citation

## 变更动机

当前 RAG 链存在两个问题：
1. 回答文本不引用文档来源 — 虽然 `sources` 字段包含检索到的文档信息，但 LLM 回答本身不标注来源
2. sources 为空 — 向量存储（ChromaDB）中 0 文档，uploads/ 中 29 个 PDF 未被索引，导致 RAG 回答全部来自 LLM 通用知识而非本地知识库

## 目标

1. 修改 RAG prompt，指示 LLM 在回答中引用文档来源
2. 创建重新索引脚本，将 uploads/ 中的 PDF 文档索引到向量存储
3. 修改 RAG 行为：当本地知识库无匹配文档时，明确告知用户而非默认回退到 LLM 通用知识

## 范围

- `framework/rag/chain.py`：修改 prompt 和无文档时的回退行为
- `scripts/reindex_documents.py`（新建）：重新索引 uploads/ 文档到向量存储
