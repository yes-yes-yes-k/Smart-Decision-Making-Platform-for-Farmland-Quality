# Design: fix-rag-answer-and-sources

## 修复方案

### Fix 1: LLM 超时和 fallback

`framework/llm/service.py`:
- L33: `timeout=30` → `timeout=60`
- L75: fallback content 从 `""` 改为提示信息

### Fix 2: sources 简化

`framework/rag/chain.py` L30-37:
- 从 `{doc_name, content, score}` 简化为 `{doc_name}`

### Fix 3: reindex 文件名

`scripts/reindex_documents.py`:
- 查询 `kb_document` 表，用 `file_path` 匹配 UUID 文件名，获取 `doc_name`（原始名）
- 若数据库无记录，回退用磁盘文件名
