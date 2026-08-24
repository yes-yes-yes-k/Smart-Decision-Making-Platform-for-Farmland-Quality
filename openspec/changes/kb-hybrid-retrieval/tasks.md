## 1. 分块修复

- [x] 1.1 新增 `framework/upload/chunker.py`，实现 `split_text(text, size, overlap)` 滑动窗口分块
- [ ] 1.2 在 `framework/api/routes/docs.py` 中用 `Config.CHUNK_SIZE`/`Config.CHUNK_OVERLAP` 替换 `content[i:i+800]` 硬编码，接入 chunker
- [x] 1.3 为 chunker 编写单元测试，覆盖重叠、空文本、小于 size 的文本

## 2. BM25 混合检索

- [ ] 2.1 在 `framework/vector_store/chroma_store.py` 中引入 BM25 索引（`rank_bm25` + `jieba`），随文档 add/delete 同步维护
- [ ] 2.2 新增混合检索入口：向量召回与 BM25 召回双路并行
- [ ] 2.3 实现 RRF（Reciprocal Rank Fusion）融合排序
- [ ] 2.4 为混合检索与 RRF 融合编写单元测试

## 3. Rerank 精排

- [ ] 3.1 新增 Rerank 服务（复用 SiliconFlow BGE-Reranker API），封装 rerank(query, candidates) 调用
- [ ] 3.2 在 `framework/rag/chain.py` 检索后接入精排：召回 20 → 精排取 top-5
- [ ] 3.3 为 Rerank 调用与降级（API 不可用时跳过精排）编写测试

## 4. 验证与回归

- [ ] 4.1 运行完整测试套件，确保现有 86 个测试无回归
- [ ] 4.2 端到端验证专业术语（交换性氢/有效钾）检索命中率提升