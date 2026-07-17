# Proposal: fix-rag-answer-and-sources

## 问题描述

RAG 回答存在 3 个 bug：

1. **answer 为空** — LLM 调用超时（timeout=30s），fallback 返回 `content: ""`，导致回答为空
2. **sources 格式冗余** — sources 包含 content（截断）和 score，用户只需要文档名
3. **文档名为 UUID** — reindex 脚本用磁盘文件名（UUID），而非原始文件名

## 根因分析

1. `framework/llm/service.py` L33: `timeout=30` 对 RAG 长 prompt 不够；L75: fallback 返回空 content
2. `framework/rag/chain.py` L30-37: sources 包含 content + score
3. `scripts/reindex_documents.py`: 用 `os.listdir` 的 UUID 文件名作为 source，未查询数据库原始文件名

## 修复目标

1. 增加 LLM 超时到 60s，fallback 返回有意义提示而非空字符串
2. sources 简化为仅包含 doc_name
3. reindex 脚本查询数据库 kb_document 表获取原始文件名
