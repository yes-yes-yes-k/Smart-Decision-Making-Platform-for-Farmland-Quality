---
comet_change: kb-hybrid-retrieval
role: technical-design
canonical_spec: openspec
archived-with: 2026-08-25-kb-hybrid-retrieval
status: final
---

# kb-hybrid-retrieval 技术设计（Design Doc）

## 1. 背景与现状

当前知识库是朴素单跳 RAG 管线，代码事实如下：

- **分块**：`framework/api/routes/docs.py` 内嵌 `chunks = [content[i:i+800] for i in range(0, len(content), 800)]`，硬编码 800 字符、无 overlap。而 `framework/config.py` 已定义 `CHUNK_OVERLAP = 150`，但从未被读取——配置形同虚设。
- **检索**：`framework/vector_store/chroma_store.py` 的 `search()` 仅做纯向量召回（`n_results`，默认 5），通过 `where={"source": ...}` 过滤来源。
- **生成**：`framework/rag/chain.py` 的 `_retrieve_documents()` 用 `Config.RETRIEVAL_TOP_K=5` 召回，`_build_context()` 直接拼接结果，无重排序。
- **Embedding**：`framework/embedding/service.py` 走 SiliconFlow `BAAI/bge-m3`（`/embeddings`）；应用已用 PostgreSQL 16 + PostGIS。

三个直接问题：分块切碎语义；耕地专业术语（交换性氢、有效钾、障碍度、酸化治理）纯向量召回不稳；无二次排序导致噪声 chunk 稀释上下文。

## 2. 目标架构

对标 RAGFlow/Dify 的「双路召回 → 精排」主链路，改造后数据流：

```
上传文档 → parse_document → chunker.split_text(size, overlap)
                ↓
   Chroma.add_documents(texts, metas)  +  BM25Store.add_documents(texts, metas)
                ↓
查询 → chain._retrieve_documents
                ↓
   ChromaVectorStore.hybrid_search(query, RECALL_TOP_K=20, filters)
        ├─ vector 召回 (Chroma query, n=20)
        ├─ bm25  召回 (BM25Store.search, n=20)
        └─ RRF 融合去重 → top-20 候选
                ↓
   RerankService.rerank(query, candidates) → top-5
                ↓
   _build_context + LLM 生成
```

## 3. 组件设计

### 3.1 `framework/upload/chunker.py`（新增）

纯函数，无状态，与解析逻辑解耦（为 P1/P2 扩展结构与元数据预留空间）。

```python
def split_text(text: str, size: int = None, overlap: int = None) -> list[str]:
    # size/overlap 缺省读 Config.CHUNK_SIZE / Config.CHUNK_OVERLAP
    # size <= 0 或 text 空 → 返回 []
    # overlap >= size → 按 size 步长退化为无重叠切分（防死循环）
    # 滑动窗口: step = size - overlap
```

边界（必须覆盖并测试）：
- 空文本 / 空白文本 → `[]`。
- `len(text) < size` → 返回单个完整块。
- `overlap >= size` → 退化为 `step = size`（不重叠），避免无限循环。
- 最后一块不足 `size` 时仍然保留。

### 3.2 `framework/vector_store/bm25_store.py`（新增）

`BM25Store` 类，应用层维护独立的 BM25 语料，与 Chroma 无关但生命周期同步。

内部状态：
- `_texts: list[str]`：原始 chunk 文本（顺序即 index）。
- `_sources: list[str]`：每 chunk 的 `metadata["source"]`。
- `_model`：`rank_bm25.BM25Okapi`（惰性构建/重建）。

分词：`jieba.lcut`（中文为主，混合文本也兼容）。

方法：
- `add_documents(texts, metadatas)`：追加 `_texts`/`_sources`，全量重建 `_model`。
- `search(query, n_results, filters) -> list[dict]`：分词查询 → 计算 BM25 分数 → 若 `filters` 含 `{"source": {"$in": [...]}}` 则只保留命中 source → 返回 `{"content", "metadata": {"source": ...}, "score"}`，按分数降序取 top-n。
- `delete_by_source(source)`：移除该 source 全部条目并重建。
- `clear()`：清空。

**取舍**：写时全量重建（O(语料) 分词）而非增量更新。本项目语料规模（企业知识库文档）可接受，换取正确性与实现简单；后续语料变大再引入增量索引。

### 3.3 `framework/vector_store/chroma_store.py`（修改）

`ChromaVectorStore` 内组合一个 `self._bm25 = BM25Store()`，保持现有 `search()` 纯向量行为不变（向后兼容）：

- `add_documents()`：Chroma 写入成功后，同步 `self._bm25.add_documents(texts, metadatas)`。
- `delete_by_source()`：Chroma 删除后同步 `self._bm25.delete_by_source(source)`。
- `clear()`：同步 `self._bm25.clear()`。
- **新增 `hybrid_search(query, n_results, filters)`**：
  - 若 `not Config.HYBRID_SEARCH_ENABLED` → 直接 `return self.search(query, n_results, filters)`（回滚路径）。
  - 否则向量召回 `self.search(query, n_results, filters)` + BM25 召回 `self._bm25.search(query, n_results, filters)`，两路并行取数后 RRF 融合。

### 3.4 RRF 融合算法

融合键 `(source, content)` 去重（同一 chunk 在两路都命中时只保留一次；不同 source 的同文本保留各自）。

```python
def _rrf_fuse(vector_docs, bm25_docs, k=Config.RRF_K):
    score = {}; docref = {}
    for rank, d in enumerate(vector_docs):
        key = (d["metadata"].get("source"), d["content"])
        score[key] = score.get(key, 0) + 1.0 / (k + rank + 1)
        docref[key] = d
    for rank, d in enumerate(bm25_docs):
        key = (d["metadata"].get("source"), d["content"])
        score[key] = score.get(key, 0) + 1.0 / (k + rank + 1)
        docref[key] = d
    return [docref[k] for k, _ in sorted(score.items(), key=lambda kv: -kv[1])]
```

切到 `n_results` 长度后返回 `{"results": [...], "count": len(...)}`（与 `search()` 返回结构一致，`chain.py` 无需改返回解析）。

### 3.5 `framework/rag/reranker.py`（新增）

`RerankService` + 单例 `rerank_service`，与 `embedding/service.py` 同栈（requests 直连 SiliconFlow）：

```python
def rerank(self, query, candidates: list[dict]) -> list[dict]:
    # 不可用或空候选 → 原样返回
    # POST {base}/rerank
    #   json: {"model": Config.RERANK_MODEL, "query": query,
    #          "documents": [c["content"] for c in candidates],
    #          "top_n": min(len(candidates), Config.RETRIEVAL_TOP_K)}
    # 返回 results 含 index + relevance_score，按 relevance_score 重排候选
    # 异常/超时/RERANK_ENABLED=False → 返回 candidates 原顺序（降级）
```

SiliconFlow rerank 模型 `BAAI/bge-reranker-v2-m3`（与 bge-m3 Embedding 同系）。降级路径保证精排失败不影响主链路。

### 3.6 `framework/rag/chain.py`（修改）

仅改 `_retrieve_documents()`：

```python
def _retrieve_documents(self, query, valid_doc_names):
    filters = {"source": {"$in": list(valid_doc_names)}} if valid_doc_names else None
    recalled = self.vector_store.hybrid_search(
        query=query, n_results=Config.RECALL_TOP_K, filters=filters)
    results = recalled["results"]
    if Config.RERANK_ENABLED and len(results) > Config.RETRIEVAL_TOP_K:
        results = rerank_service.rerank(query, results)
    return {"results": results[:Config.RETRIEVAL_TOP_K],
            "count": len(results[:Config.RETRIEVAL_TOP_K])}
```

`chat()` / `chat_stream()` 的来源收集逻辑不变（结果仍带 `metadata.source`）。

### 3.7 `framework/api/routes/docs.py`（修改）

```python
from framework.upload.chunker import split_text
...
chunks = split_text(content) if content else []
metadatas = [{"source": file.filename} for _ in chunks]
```

移除 `content[i:i+800]` 硬编码。

### 3.8 `framework/config.py`（修改）

新增配置项（均带环境变量覆盖与默认值）：

```python
RECALL_TOP_K = 20                  # 混合召回阶段候选数
RETRIEVAL_TOP_K = 5                # 已存在，精排后取 top-K
RRF_K = 60                         # RRF 平滑常数
HYBRID_SEARCH_ENABLED = True       # 混合检索开关（回滚）
RERANK_ENABLED = True              # 精排开关（回滚）
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
RERANK_TIMEOUT = 30                # 秒
```

### 3.9 `pyproject.toml`（修改）

在 `dependencies` 新增 `jieba>=0.42.0` 与 `rank_bm25>=0.2.2`（当前均未声明，需补充）。

## 4. 测试策略

新增测试（`tests/`，沿用 pytest + `tests/conftest.py` 既有 fixture）：

- `tests/test_chunker.py`：overlap 实际覆盖、空文本、小于 size、`overlap>=size` 退化、末块截断。
- `tests/test_bm25_store.py`：add/search/delete_by_source/clear、source 过滤、专业术语命中（构造含「交换性氢」「有效钾」的语料，查询「交换性氢」应命中）。
- `tests/test_hybrid_search.py` / 并入 `test_rag.py`：RRF 去重与排序、`HYBRID_SEARCH_ENABLED=False` 回退纯向量、`filters` 透传。
- `tests/test_reranker.py`：mock requests 校验请求体与重排；API 异常 → 降级原顺序。

回归：`pytest` 全量，现有 86 测试无回归（重点 `test_rag.py`、`test_upload.py`、`test_docs_dedup.py`）。

端到端：手动上传含术语文档后查询「交换性氢 / 有效钾」，对比改前命中率。

## 5. 回滚计划

逐层开关，出现回归可独立关闭而不回滚代码：

1. `RERANK_ENABLED=False` → 只关精排，退回「双路召回取 top-K」。
2. `HYBRID_SEARCH_ENABLED=False` → 退回纯向量单路。
3. `RECALL_TOP_K` 调回 5 → 行为最接近旧版。

## 6. 风险与边界

- jieba 分词对耕地术语切分不当 → 查询与语料同侧分词一致即可命中（召回依赖相同的 token 生成路径），术语优化留待 kb-semantic-enrichment。
- 新旧 chunk 不一致 → 仅影响新入库文档，需在文档中提示用户重新入库。
- BM25 写时重建 → 大语料写入变慢，短期可接受。
- Rerank API 延迟/资费 → 限定候选数 ≤20、仅在超 top-K 时触发，失败降级。
- Chroma 持久化目录旧 `_type` 兼容问题（历史已知）→ 不在本 change 处理，沿用现有自愈逻辑。
