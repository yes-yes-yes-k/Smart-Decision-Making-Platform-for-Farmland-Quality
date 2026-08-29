# kb-hybrid-retrieval Design

## Context

当前检索链路状态（详见 proposal.md）：

- 分块逻辑内嵌在 `framework/api/routes/docs.py`，硬编码 `content[i:i+800]`，无 overlap。
- 检索在 `framework/vector_store/chroma_store.py` 中仅做纯向量 `query`（top-5），通过 `where` 过滤 source。
- `framework/rag/chain.py` 将 top-5 结果直接拼接进 prompt，无重排序。
- Embedding 使用 SiliconFlow `BAAI/bge-m3`；应用已使用 PostgreSQL 16 + PostGIS。

## Goals / Non-Goals

**Goals:**
- 分块改为配置驱动（CHUNK_SIZE + CHUNK_OVERLAP），独立为可复用模块。
- 引入 BM25 关键词索引与向量召回组成双路召回，RRF 融合。
- 在生成前增加 Rerank 精排，召回 20 → 精排取 top-5。

**Non-Goals:**
- 不做同义词词表、chunk 元数据增强、分领域 collection（属 kb-semantic-enrichment）。
- 不做文本清洗、异步、OCR、引用溯源、评估（属 kb-ingestion-quality）。
- 不替换 Chroma 为 Milvus/Qdrant/ES。

## Decisions

1. **BM25 通道选型：应用层 `rank_bm25` + `jieba` 优先，PostgreSQL `pg_bigm` 为备选。**
   - 理由：避免引入 Elasticsearch 的运维负担；应用层 BM25 索引与 Chroma 共存，改动最小。`pg_bigm` 适合中文 n-gram 全文检索，可后续平滑切换。
   - 备选：直接引入 ES（成本高，暂不采用）。

2. **融合算法：RRF（Reciprocal Rank Fusion）。**
   - 理由：无需调权重、对异构分数鲁棒，是 RAGFlow/Hybrid-RAG 等开源方案的标准做法，实现简单可解释。

3. **Rerank 复用 SiliconFlow BGE-Reranker API。**
   - 理由：与现有 `bge-m3` Embedding 同栈，接入延迟可接受；避免自建 cross-encoder 的模型部署成本。
   - 备选：Qwen3-Reranker（同 API 可选，保留切换空间）。

4. **分块独立为 `framework/upload/chunker.py`，纯函数 `split_text(text, size, overlap)`。**
   - 理由：与解析逻辑解耦，便于后续（P1/P2）在 chunker 上扩展结构与元数据。

## Risks / Trade-offs

- [BM25 中文分词质量依赖 jieba 词典] → 耕地术语词库可在后续（kb-semantic-enrichment）补充，本次先用默认词典 + 用户自定义词。
- [分块参数变化导致新旧 chunk 不一致] → 本次仅影响新入库文档；设计说明中提示用户重新入库以获得完整效果，不改动既有旧 chunk。
- [Rerank 增加一次 API 调用延迟] → 限定在召回后 top-20 内精排，且仅当候选数超过最终 top-K 时触发，控制成本。

## Migration Plan

1. 新增 `chunker.py` 并接入 `docs.py` 入库流程。
2. 在 `chroma_store.py` 增加 BM25 索引维护（add/delete 同步）与混合检索入口。
3. 在 `chain.py` 检索后插入 Rerank 步骤。
4. 回滚：各步骤均有独立开关（config 项），出现回归可逐步关闭。

## Open Questions

（无——BM25 通道与 Rerank 模型的具体实现细节不改变 spec、方案或任务拆分，可在 build 阶段定夺。）