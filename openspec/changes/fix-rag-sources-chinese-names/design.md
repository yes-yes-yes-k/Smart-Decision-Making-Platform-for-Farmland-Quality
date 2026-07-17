# Design: fix-rag-sources-chinese-names

## 实现方案

### Fix 1: 去掉 prompt 中的来源引用指示

`_build_prompt` 方法：移除"回答时必须在引用文档内容处标注来源，格式为'根据《文档名》...'"

### Fix 2: 去掉 context 中的文档名

`_build_context` 方法：不再在 context 中包含文档名，只保留内容

### Fix 3: sources 查询数据库中文文件名

在 `chat` 方法中，sources 构建时查询 `kb_document` 表：
- 使用 `file_path`（UUID 文件名）匹配数据库记录
- 获取 `doc_name`（中文原始文件名）
- 若数据库无记录，回退使用 metadata 中的 source（UUID）

### Fix 4: chroma_store.py 添加 clear 方法

向量存储原本没有清空方法，重新索引时旧文档会残留。新增 `clear()` 方法：获取所有 id 后批量删除，返回删除前的文档数。

### Fix 5: reindex_documents.py 清空 + source 对齐 file_path

根因：向量存储中的旧 source（UUID）与 kb_document 表的 file_path（UUID）不匹配（0/11 匹配），导致 chain.py 的 `_query_doc_names` 查询返回空，sources 回退到 UUID。

修复：
1. reindex 脚本先调用 `vector_store.clear()` 清空旧文档
2. source 设为磁盘文件名（UUID），与 kb_document.file_path 对齐
3. chain.py 查询 `file_path IN (source)` 即可匹配，返回中文 doc_name

### Fix 6: chain.py 修复 metadata None 问题

检索结果中 metadata 可能为 None，`metadata.get(...)` 会抛出 AttributeError。改为 `result.get("metadata") or {}`。