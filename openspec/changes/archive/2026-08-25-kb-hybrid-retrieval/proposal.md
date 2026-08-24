# kb-hybrid-retrieval Proposal

## Why

当前知识库检索是一条朴素单跳 RAG 管线：文档上传后按**固定 800 字符硬切**分块，检索时仅做**纯向量相似度召回**（top-5），结果直接拼接进 prompt 由 LLM 生成。这带来三个直接问题：

1. 分块代码硬编码 `content[i:i+800]`，完全忽略配置中的 `CHUNK_OVERLAP=150`，语义在块边界被切断。
2. 耕地领域大量高区分度专业术语（交换性氢、有效钾、障碍度、酸化治理）在向量空间中的召回准确率不稳定，纯向量检索容易漏召回。
3. 召回结果无二次排序，噪声 chunk 直接进入 prompt，稀释上下文并降低答案质量。

本次对标 RAGFlow/Dify 的「双路召回 → 精排」主路径，升级检索主链路，是知识库升级中收益最直接的第一层。

## What Changes

- **分块修复**：新增独立分块模块 `framework/upload/chunker.py`，使用 `Config.CHUNK_SIZE=800` 与 `Config.CHUNK_OVERLAP=150` 做滑动窗口分块，替换 `docs.py` 内嵌的固定 800 字符硬切逻辑。
- **混合召回**：在向量库层新增 BM25 关键词索引，检索时向量召回与 BM25 召回双路并行，用 RRF（Reciprocal Rank Fusion）合并排序。
- **精排（Rerank）**：在 RAG 链生成前增加精排步骤，扩大召回量（20）后用 rerank 模型重排取 top-5。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `rag-chain`: 检索流程由「单路向量召回」改为「双路召回（向量 + BM25）+ Rerank 精排」后送入生成。
- `vector-store`: 新增 BM25 关键词索引与混合检索能力，支持向量与关键词双路召回并用 RRF 融合。
- `file-upload-management`: 文档分块由固定字符硬切改为配置驱动（size + overlap）的滑动窗口分块。

## Impact

- 代码：`framework/rag/chain.py`、`framework/vector_store/chroma_store.py`、`framework/api/routes/docs.py`、`framework/config.py`；新增 `framework/upload/chunker.py`。
- 依赖：新增 BM25 实现（优先用 PostgreSQL `pg_trgm`/`pg_bigm` 或轻量 `rank_bm25` + `jieba`，避免引入 ES 运维负担）；rerank 复用 SiliconFlow 的 BGE-Reranker API。
- 无破坏性变更：现有向量存储 Collection 结构保持不变；分块参数变化仅影响新入库文档，需要提示用户重新入库以获得完整效果。