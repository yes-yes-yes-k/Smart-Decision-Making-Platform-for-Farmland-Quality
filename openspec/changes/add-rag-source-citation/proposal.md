# Proposal: add-rag-source-citation

## 变更动机

当前 RAG 链在回答用户问题时，虽然 `sources` 字段已包含检索到的文档来源信息（doc_name、content、score），但 LLM 生成的回答文本本身不会引用文档来源。用户希望回答中明确标注信息来源于哪个文档。

## 目标

修改 RAG 链的 prompt，指示 LLM 在回答中引用文档来源（如"根据《文档名》..."），使回答自带来源引用。

## 范围

仅修改 `framework/rag/chain.py` 的 `_build_prompt` 方法，调整 prompt 模板。不涉及接口变更、数据库 schema 或跨模块协调。
