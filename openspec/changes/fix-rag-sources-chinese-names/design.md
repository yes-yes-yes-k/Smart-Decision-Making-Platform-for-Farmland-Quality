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