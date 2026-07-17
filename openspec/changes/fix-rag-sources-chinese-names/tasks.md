# Tasks: fix-rag-sources-chinese-names

- [x] Fix 1: 去掉 prompt 中的来源引用指示，answer 不再要求标注文档名
- [x] Fix 2: 去掉 context 中的文档名，只保留文档内容
- [x] Fix 3: sources 查询 kb_document 表获取中文原始文件名
- [x] Fix 4: chroma_store.py 添加 clear 方法支持清空向量存储
- [x] Fix 5: reindex_documents.py 清空向量存储 + source 设为 UUID（磁盘文件名），与 kb_document.file_path 对齐
- [x] Fix 6: chain.py 修复 metadata 为 None 时的空指针问题
