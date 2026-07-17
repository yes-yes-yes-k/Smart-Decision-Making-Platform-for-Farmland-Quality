# 验证报告：add-rag-source-citation

**日期**：2026-07-17
**Change**：add-rag-source-citation
**工作流**：tweak
**验证模式**：light

## 改动概述

1. 修改 `framework/rag/chain.py` 的 `_build_prompt`，增加文档来源引用指示和本地知识库优先指示
2. 修改 `framework/rag/chain.py` 的 `chat` 方法，无文档时增加 notice 字段告知用户
3. 新建 `scripts/reindex_documents.py`，将 uploads/ 中的 PDF 重新索引到向量存储
4. 安装 PyPDF2 依赖（PDF 解析所需）

## 轻量验证结果（6 项）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部任务已完成 | PASS | 5/5 tasks 已勾选 |
| 2 | 改动文件与 tasks.md 一致 | PASS | framework/rag/chain.py（5 insertions, 2 deletions）+ scripts/reindex_documents.py（57 insertions） |
| 3 | 编译通过 | PASS | import 成功 |
| 4 | 相关测试通过 | PASS | pytest tests/test_rag.py → 4 passed |
| 5 | 无明显安全问题 | PASS | 仅修改 prompt 和回退行为，无硬编码密钥 |
| 6 | 代码审查 | SKIP | review_mode: off |

## 额外验证

- 向量存储文档数：0 → 646（重新索引后）
- 检索测试："耕地质量评价的标准是什么" → 返回匹配文档（count > 0）
- Prompt 包含来源引用指示和本地知识库优先指示

## 结论

验证通过。RAG 回答将包含文档来源引用，向量存储已索引 646 个文档片段。
