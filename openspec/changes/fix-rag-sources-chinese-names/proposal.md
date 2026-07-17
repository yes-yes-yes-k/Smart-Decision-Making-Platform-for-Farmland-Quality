# Proposal: fix-rag-sources-chinese-names

## 变更动机

1. answer 中包含文档来源引用（"根据《文档名》..."），用户希望 answer 只回答问题，不需要引用来源
2. sources 中的文档名目前是 UUID（如 `08c4dcc581e2488abbbf3ef3f4930fc7.pdf`），用户希望显示中文原始文件名，应从数据库 `kb_document` 表查询

## 目标

1. 修改 RAG prompt，去掉文档来源引用指示
2. 修改 `_build_context`，不再在 context 中包含文档名
3. 修改 `chat` 方法，从数据库查询中文原始文件名作为 sources

## 范围

仅修改 `framework/rag/chain.py`，不涉及接口变更或架构调整。