# 验证报告：fix-rag-sources-chinese-names

**日期**：2026-07-17
**Change**：fix-rag-sources-chinese-names
**工作流**：tweak
**验证模式**：light

## 改动概述

修改 3 个文件：
1. `framework/rag/chain.py`：
   - `_build_prompt`：移除来源引用指示
   - `_build_context`：不再包含文档名
   - 新增 `_query_doc_names` 方法查询 kb_document 表获取中文 doc_name
   - 修复 metadata 为 None 时的空指针问题
2. `framework/vector_store/chroma_store.py`：
   - 新增 `clear()` 方法支持清空向量存储
3. `scripts/reindex_documents.py`：
   - 索引前清空向量存储，避免残留过时文档
   - source 设为磁盘文件名（UUID），与 kb_document.file_path 对齐

## 根因分析

向量存储中的旧 source（11 个 UUID）与 kb_document 表的 file_path（13 个 UUID）完全不匹配（0/11 匹配），导致 chain.py 的 `_query_doc_names` 查询 `file_path IN (source)` 返回空，sources 回退到 UUID。

修复方案：清空向量存储，重新索引时 source 设为磁盘文件名（UUID），与 kb_document.file_path 对齐。

## 轻量验证结果（6 项）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部任务已完成 | PASS | 6/6 tasks 已勾选 |
| 2 | 改动文件与 tasks.md 一致 | PASS | 3 个代码文件改动（chain.py, chroma_store.py, reindex_documents.py） |
| 3 | 编译通过 | PASS | import 成功 |
| 4 | 相关测试通过 | PASS | RAG 查询验证通过，sources 显示中文 doc_name |
| 5 | 无明显安全问题 | PASS | 仅修改 prompt、context 格式、数据库查询和向量存储清空 |
| 6 | 代码审查 | SKIP | review_mode: off |

## 功能验证

重新索引后向量存储状态：
- 文档片段数：646
- 唯一 source 数：11（全部为 UUID 磁盘文件名）
- 数据库匹配数：11/11（全部匹配 kb_document.file_path）
- 不匹配数：0

RAG 查询验证（查询"耕地质量等级评价的标准是什么"）：
- 检索到 5 个文档片段
- sources 最终显示：
  - 关于细化转发《补充耕地质量验收办法(试行)》(征求意见稿)的通知.pdf
  - 农业农村部办公厅关于印发《补充耕地质量鉴定技术规范(试行)》的通知.pdf

## 结论

验证通过。sources 现在显示中文 doc_name（从 kb_document 表查询），answer 不再包含文档来源引用。
