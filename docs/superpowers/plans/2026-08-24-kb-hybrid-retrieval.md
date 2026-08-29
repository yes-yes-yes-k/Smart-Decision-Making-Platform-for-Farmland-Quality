---
change: kb-hybrid-retrieval
design-doc: docs/superpowers/specs/2026-08-24-kb-hybrid-retrieval-design.md
base-ref: 71c072c2bba09f18fded4c113d6125a80eeb8af4
archived-with: 2026-08-25-kb-hybrid-retrieval
---

# kb-hybrid-retrieval 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务执行本计划。步骤用复选框（`- [x]`）语法跟踪进度。

**Goal:** 把当前「纯向量 top-5」RAG 检索链路改造为「配置驱动分块 → 双路召回（向量 + BM25）→ RRF 融合 → Rerank 精排 top-5」，提升耕地专业术语（交换性氢、有效钾等）的检索命中率。

**Architecture:** 分块逻辑从 `docs.py` 内嵌硬编码抽为纯函数 `split_text`；新增应用层 `BM25Store`（`jieba` + `rank_bm25`），由 `ChromaVectorStore` 在 add/delete/clear 时同步维护；新增 `hybrid_search()` 双路召回后用 RRF 融合；新增 `RerankService` 复用 SiliconFlow `BAAI/bge-reranker-v2-m3` 精排；`RAGChain._retrieve_documents()` 从「top-k 召回」改为「召回 20 → 精排 → 取 5」。全链路带独立开关（`HYBRID_SEARCH_ENABLED` / `RERANK_ENABLED` / `RECALL_TOP_K`）支持逐层回滚。

**Tech Stack:** Python 3.10+、Flask、ChromaDB、SiliconFlow Embedding/Rerank API、`jieba>=0.42.0`、`rank_bm25>=0.2.2`、pytest。

## Global Constraints

- 版本下限：新增依赖 `jieba>=0.42.0`、`rank_bm25>=0.2.2`（当前 `pyproject.toml` 均未声明）。
- 分块参数：`CHUNK_SIZE = 800`、`CHUNK_OVERLAP = 150`（`framework/config.py` 已存在，勿改动数值）。
- 召回参数（新增）：`RECALL_TOP_K = 20`、`RRF_K = 60`、`HYBRID_SEARCH_ENABLED = True`。
- 精排参数（新增）：`RERANK_ENABLED = True`、`RERANK_MODEL = "BAAI/bge-reranker-v2-m3"`、`RERANK_TIMEOUT = 30`（秒）。
- 最终送入生成仍为 `RETRIEVAL_TOP_K = 5`（已存在）。
- 融合去重键为 `(source, content)`：同一 chunk 两路命中只保留一次，不同 source 的同文本各自保留。
- 回滚开关：`RERANK_ENABLED=False` 只关精排；`HYBRID_SEARCH_ENABLED=False` 退回纯向量单路；`RECALL_TOP_K=5` 最接近旧行为。开关必须带环境变量覆盖。
- 降级原则：Rerank API 异常/超时/关闭 → 原顺序返回候选，不影响主链路；BM25 写时全量重建（语料规模可接受）。
- 命名与路径严格遵循设计文档：
  - 新增 `framework/upload/chunker.py`、`framework/vector_store/bm25_store.py`、`framework/rag/reranker.py`。
  - 修改 `framework/vector_store/chroma_store.py`、`framework/rag/chain.py`、`framework/api/routes/docs.py`、`framework/config.py`、`pyproject.toml`。
- 语言：代码注释与测试断言说明使用简体中文。

---

## 组一：分块修复

### Task 1: 新增无状态分块函数 `split_text`（tasks.md 1.1 + 1.3）

**Files:**
- Create: `framework/upload/chunker.py`
- Test: `tests/test_chunker.py`

**Interfaces:**
- Produces: `split_text(text: str, size: int = None, overlap: int = None) -> list[str]`。
  - `size` / `overlap` 缺省读 `Config.CHUNK_SIZE` / `Config.CHUNK_OVERLAP`（调用时解析，非定义时，保证测试可 monkeypatch）。
  - `size <= 0`、文本为空或纯空白 → 返回 `[]`。
  - `len(text) <= size` → 返回单个完整块 `[text]`。
  - 滑动窗口 `step = size - overlap`；`overlap >= size`（`step <= 0`）退化为 `step = size`（无重叠）。
  - 末块不足 `size` 仍保留。

- [x] **Step 1: 编写失败测试** `tests/test_chunker.py`

```python
"""测试配置驱动的滑动窗口分块。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.upload.chunker import split_text


def test_empty_or_whitespace_text_returns_empty():
    assert split_text("") == []
    assert split_text("   ") == []


def test_size_non_positive_returns_empty():
    assert split_text("abc", size=0, overlap=0) == []
    assert split_text("abc", size=-1, overlap=0) == []


def test_text_shorter_than_size_returns_single_chunk():
    assert split_text("abc", size=800, overlap=150) == ["abc"]


def test_overlap_covers_segment():
    # 长度 1000、size 800、overlap 150 -> step 650，切出 2 块，末块从 650 开始
    text = "啊" * 1000
    chunks = split_text(text, size=800, overlap=150)
    assert len(chunks) == 2
    assert chunks[0] == text[:800]
    assert chunks[1] == text[650:]


def test_overlap_ge_size_degrades_to_no_overlap():
    # overlap == size -> step 退化为 size，无重叠，不产生死循环
    text = "啊" * 900
    chunks = split_text(text, size=800, overlap=800)
    assert chunks == [text[:800], text[800:]]


def test_last_short_chunk_kept():
    text = "a" * 805
    chunks = split_text(text, size=800, overlap=150)
    assert len(chunks) == 2
    assert chunks[-1] == text[650:]


def test_defaults_read_config():
    # 不传 size/overlap 时使用 Config.CHUNK_SIZE=800 / CHUNK_OVERLAP=150
    text = "啊" * 1000
    chunks = split_text(text)
    assert chunks[0] == text[:800]
    assert chunks[1] == text[650:]
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_chunker.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'framework.upload.chunker'`）

- [x] **Step 3: 编写最小实现** `framework/upload/chunker.py`

```python
from __future__ import annotations
from typing import List

from framework.config import Config


def split_text(text: str, size: int = None, overlap: int = None) -> List[str]:
    """滑动窗口分块，参数缺省读 Config.CHUNK_SIZE / Config.CHUNK_OVERLAP。

    - size <= 0 或文本为空/纯空白 → 返回 []
    - len(text) <= size → 返回单个完整块
    - step = size - overlap；overlap >= size 时退化为 step = size（无重叠）
    - 末块不足 size 仍保留
    """
    if size is None:
        size = Config.CHUNK_SIZE
    if overlap is None:
        overlap = Config.CHUNK_OVERLAP

    if not text or not text.strip() or size <= 0:
        return []
    if len(text) <= size:
        return [text]

    step = size - overlap
    if step <= 0:
        step = size  # overlap >= size 时退化为无重叠，避免无限循环

    chunks: List[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += step
    return chunks
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_chunker.py -v`
Expected: PASS（7 个用例全绿）

- [x] **Step 5: 提交**

```bash
git add framework/upload/chunker.py tests/test_chunker.py
git commit -m "feat(kb): add config-driven sliding window chunker"
```

---

### Task 2: 接入 chunker 到上传入库流程（tasks.md 1.2）

**Files:**
- Modify: `framework/api/routes/docs.py:9-10`（加 import）、`framework/api/routes/docs.py:116-119`（替换硬编码分块）

**Interfaces:**
- Consumes: `split_text(content) -> list[str]`（Task 1 产出）。
- Produces: 上传路由 `chunks` / `metadatas` / `chunk_count` 语义不变，仅分块来源从硬编码 800 无重叠改为配置驱动重叠分块。

- [x] **Step 1: 新增 import**

在 `framework/api/routes/docs.py` 顶部 import 区（`from framework.upload.document_parser import parse_document` 之后）加入：

```python
from framework.upload.chunker import split_text
```

- [x] **Step 2: 替换硬编码分块**

把 `framework/api/routes/docs.py` 第 116-119 行：

```python
        content = parse_document(file_path, file_type)
        chunks = []
        if content:
            chunks = [content[i:i+800] for i in range(0, len(content), 800)]
            metadatas = [{"source": file.filename} for _ in chunks]
```

改为：

```python
        content = parse_document(file_path, file_type)
        chunks = []
        if content:
            chunks = split_text(content)
            metadatas = [{"source": file.filename} for _ in chunks]
```

（`added_count` / `chunk_count` / 后续入库逻辑不动。）

- [x] **Step 3: 验证导入与既有上传回归**

Run: `python -m pytest tests/test_upload.py tests/test_docs_dedup.py -v`
Expected: PASS（`test_upload.py` 与 `test_docs_dedup.py` 全部通过；`test_docs_dedup.py` 里 mock 了 `framework.api.routes.docs.vector_store`，`split_text` 是无依赖纯函数，上传流程照常执行）。

- [x] **Step 4: 提交**

```bash
git add framework/api/routes/docs.py
git commit -m "feat(kb): route upload chunking through chunker"
```

---

## 组二：BM25 混合检索

### Task 3: 新增 BM25 索引与依赖（tasks.md 2.1 索引本体）

**Files:**
- Create: `framework/vector_store/bm25_store.py`
- Modify: `pyproject.toml:21-22`（`dependencies` 增两行）
- Test: `tests/test_bm25_store.py`

**Interfaces:**
- Produces: `class BM25Store`：
  - `add_documents(texts: List[str], metadatas: Optional[List[dict]] = None) -> int`
  - `search(query: str, n_results: int = 20, filters: Optional[dict] = None) -> List[dict]`
    - 返回 `[{"content": str, "metadata": {"source": str}, "score": float}, ...]`，按分数降序取 top-n。
    - `filters` 形如 `{"source": {"$in": [...]}}` 时只保留命中 source 的条目。
  - `delete_by_source(source: str) -> int`（返回移除条数）
  - `clear() -> int`（返回清空前条数）

- [x] **Step 1: 声明并安装依赖**

在 `pyproject.toml` 的 `dependencies` 列表中（`"chromadb>=0.5.0",` 这一行之后）加入两行：

```toml
    "jieba>=0.42.0",
    "rank_bm25>=0.2.2",
```

安装到当前环境：

Run: `pip install "jieba>=0.42.0" "rank_bm25>=0.2.2"`
Expected: 安装成功，无报错。

- [x] **Step 2: 编写失败测试** `tests/test_bm25_store.py`

```python
"""测试应用层 BM25 关键词索引。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.vector_store.bm25_store import BM25Store


def _make_store():
    store = BM25Store()
    store.add_documents(
        ["土壤交换性氢含量影响土壤酸度", "有效钾是作物重要养分指标"],
        [{"source": "soil.pdf"}, {"source": "fertilizer.pdf"}],
    )
    return store


def test_add_and_search_returns_scored_docs():
    store = _make_store()
    results = store.search("交换性氢", n_results=5)
    assert len(results) >= 1
    assert results[0]["metadata"]["source"] == "soil.pdf"
    assert "content" in results[0] and "score" in results[0]


def test_search_hits_terminology():
    store = _make_store()
    results = store.search("有效钾", n_results=5)
    assert any(r["metadata"]["source"] == "fertilizer.pdf" for r in results)


def test_source_filter_includes_only_allowed():
    store = _make_store()
    results = store.search("有效钾", n_results=5, filters={"source": {"$in": ["fertilizer.pdf"]}})
    assert len(results) == 1
    assert results[0]["metadata"]["source"] == "fertilizer.pdf"


def test_delete_by_source():
    store = _make_store()
    assert store.delete_by_source("soil.pdf") == 1
    assert store.search("交换性氢", n_results=5) == []


def test_clear():
    store = _make_store()
    assert store.clear() == 2
    assert store.search("交换性氢", n_results=5) == []
```

- [x] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_bm25_store.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'framework.vector_store.bm25_store'`）

- [x] **Step 4: 编写最小实现** `framework/vector_store/bm25_store.py`

```python
from __future__ import annotations
from typing import List, Optional, Dict

import jieba
from rank_bm25 import BM25Okapi


class BM25Store:
    """应用层 BM25 关键词索引，与 Chroma 无关但生命周期同步。

    取舍：写时全量重建（O(语料) 分词），换取正确性与实现简单。
    """

    def __init__(self):
        self._texts: List[str] = []
        self._sources: List[str] = []
        self._model = None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return jieba.lcut(text)

    def _rebuild(self) -> None:
        if not self._texts:
            self._model = None
        else:
            self._model = BM25Okapi([self._tokenize(t) for t in self._texts])

    def add_documents(self, texts: List[str], metadatas: Optional[List[Dict]] = None) -> int:
        metadatas = metadatas or []
        for i, text in enumerate(texts):
            source = ""
            if i < len(metadatas) and metadatas[i]:
                source = metadatas[i].get("source", "")
            self._texts.append(text)
            self._sources.append(source)
        self._rebuild()
        return len(texts)

    def search(self, query: str, n_results: int = 20, filters: Optional[Dict] = None) -> List[Dict]:
        if not self._model:
            return []

        tokens = self._tokenize(query)
        scores = self._model.get_scores(tokens)

        allowed = None
        if filters and isinstance(filters.get("source"), dict) and "$in" in filters["source"]:
            allowed = set(filters["source"]["$in"])

        scored = []
        for i, s in enumerate(scores):
            if allowed is not None and self._sources[i] not in allowed:
                continue
            scored.append((s, i))
        scored.sort(key=lambda x: -x[0])

        results = []
        for s, i in scored[:n_results]:
            results.append({
                "content": self._texts[i],
                "metadata": {"source": self._sources[i]},
                "score": float(s),
            })
        return results

    def delete_by_source(self, source: str) -> int:
        kept_texts, kept_sources = [], []
        removed = 0
        for text, src in zip(self._texts, self._sources):
            if src == source:
                removed += 1
            else:
                kept_texts.append(text)
                kept_sources.append(src)
        self._texts = kept_texts
        self._sources = kept_sources
        self._rebuild()
        return removed

    def clear(self) -> int:
        count = len(self._texts)
        self._texts = []
        self._sources = []
        self._model = None
        return count
```

- [x] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_bm25_store.py -v`
Expected: PASS（5 个用例全绿）

- [x] **Step 6: 提交**

```bash
git add framework/vector_store/bm25_store.py tests/test_bm25_store.py pyproject.toml
git commit -m "feat(kb): add app-level BM25 keyword index"
```

---

### Task 4: 在 ChromaVectorStore 接入 BM25 同步 + `hybrid_search` + RRF（tasks.md 2.1 同步 + 2.2 + 2.3）

**Files:**
- Modify: `framework/vector_store/chroma_store.py:7`（加 import）、`:36-39`（`__init__`）、`:125-148`（`add_documents`）、`:188-199`（`delete_by_source`）、`:214-229`（`clear`），新增 `hybrid_search` 与 `_rrf_fuse`
- Modify: `framework/config.py:49-51` 之后（新增 `RECALL_TOP_K` / `RRF_K` / `HYBRID_SEARCH_ENABLED`）

**Interfaces:**
- Consumes: `BM25Store`（Task 3）、`Config.RECALL_TOP_K` / `Config.RRF_K` / `Config.HYBRID_SEARCH_ENABLED`（本任务新增）。
- Produces: `hybrid_search(query: str, n_results: int = 20, filters: Optional[dict] = None) -> Dict[str, Any]`，返回结构与 `search()` 一致 `{"results": [...], "count": N}`（`chain.py` 无需改返回解析）。
- 保持 `search()` 纯向量行为不变（向后兼容）。

- [x] **Step 1: 新增配置项** `framework/config.py`

在 `RETRIEVAL_TOP_K = 5`（约第 51 行）之后新增：

```python
    RECALL_TOP_K = int(os.environ.get("RECALL_TOP_K") or 20)      # 混合召回阶段候选数
    RRF_K = int(os.environ.get("RRF_K") or 60)                    # RRF 平滑常数
    HYBRID_SEARCH_ENABLED = os.environ.get("HYBRID_SEARCH_ENABLED", "true").lower() == "true"
```

（`RETRIEVAL_TOP_K = 5` 已存在，精排后取 top-K，勿重复定义。）

- [x] **Step 2: 修改 `framework/vector_store/chroma_store.py`**

（1）顶部 import 区（`from framework.embedding.service import embedding_service` 之后）加：

```python
from framework.vector_store.bm25_store import BM25Store
```

（2）`__init__` 增加 BM25 实例：

```python
    def __init__(self):
        self._client = None
        self._collection = None
        self._bm25 = BM25Store()
        self._init_client()
```

（3）`add_documents`：Chroma 写入成功后同步 BM25（在 `return len(texts)` 之前）：

```python
            self._collection.add(
                ids=ids or [f"doc_{i}" for i in range(len(texts))],
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas or [],
            )
            self._bm25.add_documents(texts, metadatas)
            return len(texts)
```

（4）`delete_by_source`：Chroma 删除后同步 BM25：

```python
    def delete_by_source(self, source_doc_name: str) -> int:
        if not self._collection:
            return 0

        try:
            count_before = self._collection.count()
            self._collection.delete(where={"source": source_doc_name})
            count_after = self._collection.count()
            self._bm25.delete_by_source(source_doc_name)
            return count_before - count_after
        except Exception as e:
            print(f"删除失败: {e}")
            return 0
```

（5）`clear`：清空 Chroma 后同步 BM25：

```python
    def clear(self) -> int:
        """清空集合中的所有文档，返回删除前的文档数"""
        if not self._collection:
            return 0
        try:
            count_before = self._collection.count()
            if count_before == 0:
                self._bm25.clear()
                return 0
            all_data = self._collection.get()
            ids = all_data.get("ids", [])
            if ids:
                self._collection.delete(ids=ids)
            self._bm25.clear()
            return count_before
        except Exception as e:
            print(f"清空集合失败: {e}")
            return 0
```

（6）新增 `hybrid_search` 与 `_rrf_fuse`（放在 `search()` 方法之后、`delete_by_source()` 之前）：

```python
    def hybrid_search(self, query: str, n_results: int = 20, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """双路召回：向量 + BM25，RRF 融合去重后取 top-n。

        Config.HYBRID_SEARCH_ENABLED=False 时回退纯向量单路（回滚路径）。
        """
        if not Config.HYBRID_SEARCH_ENABLED:
            return self.search(query, n_results, filters)

        vector_res = self.search(query, n_results, filters)
        bm25_docs = self._bm25.search(query, n_results, filters)
        fused = self._rrf_fuse(vector_res["results"], bm25_docs, k=Config.RRF_K)
        fused = fused[:n_results]
        return {"results": fused, "count": len(fused)}

    @staticmethod
    def _rrf_fuse(vector_docs: List[Dict], bm25_docs: List[Dict], k: int = 60) -> List[Dict]:
        """RRF 融合：以 (source, content) 为键去重并累加倒数排名分。"""
        score: Dict[tuple, float] = {}
        docref: Dict[tuple, Dict] = {}
        for rank, d in enumerate(vector_docs):
            key = (d.get("metadata", {}).get("source"), d.get("content"))
            score[key] = score.get(key, 0.0) + 1.0 / (k + rank + 1)
            docref[key] = d
        for rank, d in enumerate(bm25_docs):
            key = (d.get("metadata", {}).get("source"), d.get("content"))
            score[key] = score.get(key, 0.0) + 1.0 / (k + rank + 1)
            docref[key] = d
        return [docref[k] for k, _ in sorted(score.items(), key=lambda kv: -kv[1])]
```

- [x] **Step 3: 语法与导入自检**

Run: `python -c "from framework.vector_store.chroma_store import ChromaVectorStore; print(hasattr(ChromaVectorStore, 'hybrid_search'), hasattr(ChromaVectorStore, '_rrf_fuse'))"`
Expected: `True True`（注意：此命令会初始化真实 Chroma 持久化目录，属预期行为，无需网络）。

- [x] **Step 4: 提交**

```bash
git add framework/vector_store/chroma_store.py framework/config.py
git commit -m "feat(kb): add hybrid search with RRF fusion into vector store"
```

---

### Task 5: 混合检索与 RRF 融合单测（tasks.md 2.4）

**Files:**
- Test: `tests/test_hybrid_search.py`

**Interfaces:**
- Consumes: `ChromaVectorStore._rrf_fuse(vector_docs, bm25_docs, k)`（Task 4）、`ChromaVectorStore.hybrid_search(query, n_results, filters)`、`Config.HYBRID_SEARCH_ENABLED`。
- 本任务全程离线（不触发 Chroma 持久化初始化、不依赖 embedding API）：用 `ChromaVectorStore.__new__` 构造无初始化实例，只测纯函数与回退分支。

- [x] **Step 1: 编写测试** `tests/test_hybrid_search.py`

```python
"""测试混合检索 RRF 融合与回退（离线，不依赖 embedding/Chroma 初始化）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.vector_store.chroma_store import ChromaVectorStore


def _doc(source, content):
    return {"content": content, "metadata": {"source": source}}


def test_rrf_fuse_dedup_and_rank():
    vector_docs = [
        _doc("a.pdf", "文本A"),
        _doc("b.pdf", "文本B"),
    ]
    bm25_docs = [
        _doc("b.pdf", "文本B"),  # 与向量路重叠
        _doc("c.pdf", "文本C"),
    ]
    fused = ChromaVectorStore._rrf_fuse(vector_docs, bm25_docs, k=60)
    contents = [d["content"] for d in fused]
    # 两路都命中 b.pdf，融合分最高，应排第一；且无重复项
    assert contents[0] == "文本B"
    assert len(contents) == 3
    assert set(contents) == {"文本A", "文本B", "文本C"}


def test_rrf_fuse_same_content_diff_source_kept_separate():
    vector_docs = [_doc("a.pdf", "相同文本")]
    bm25_docs = [_doc("b.pdf", "相同文本")]
    fused = ChromaVectorStore._rrf_fuse(vector_docs, bm25_docs, k=60)
    # 键含 source，不同 source 的同文本各自保留
    assert len(fused) == 2


def test_hybrid_search_disabled_falls_back_to_vector(monkeypatch):
    from framework.config import Config
    monkeypatch.setattr(Config, "HYBRID_SEARCH_ENABLED", False)

    store = ChromaVectorStore.__new__(ChromaVectorStore)
    calls = {}

    def fake_search(query, n_results, filters=None):
        calls["args"] = (query, n_results, filters)
        return {"results": [], "count": 0}

    store.search = fake_search
    result = store.hybrid_search("查询", n_results=20, filters=None)

    assert result == {"results": [], "count": 0}
    assert calls["args"] == ("查询", 20, None)
```

- [x] **Step 2: 运行测试确认通过**

Run: `python -m pytest tests/test_hybrid_search.py -v`
Expected: PASS（3 个用例全绿）。

- [x] **Step 3: 提交**

```bash
git add tests/test_hybrid_search.py
git commit -m "test(kb): cover RRF fusion and hybrid fallback"
```

---

## 组三：Rerank 精排

### Task 6: 新增 Rerank 服务与降级（tasks.md 3.1 + 3.3）

**Files:**
- Create: `framework/rag/reranker.py`
- Modify: `framework/config.py`（新增 `RERANK_ENABLED` / `RERANK_MODEL` / `RERANK_TIMEOUT`）
- Test: `tests/test_reranker.py`

**Interfaces:**
- Consumes: `Config.SILICONFLOW_API_KEY` / `Config.SILICONFLOW_BASE_URL`（已存在）、`Config.RETRIEVAL_TOP_K`（已存在）、本任务新增的 `RERANK_ENABLED` / `RERANK_MODEL` / `RERANK_TIMEOUT`。
- Produces: `class RerankService`：
  - `is_available() -> bool`：`RERANK_ENABLED and SILICONFLOW_API_KEY` 均真。
  - `rerank(query: str, candidates: List[dict]) -> List[dict]`：
    - 不可用或空候选 → 原样返回。
    - `POST {SILICONFLOW_BASE_URL}/rerank`，`json={"model": RERANK_MODEL, "query": query, "documents": [c["content"] ...], "top_n": min(len(candidates), RETRIEVAL_TOP_K)}`。
    - 返回的 `results` 含 `index` + `relevance_score`，按 `relevance_score` 降序重排 `candidates`。
    - 异常/超时 → 返回 `candidates` 原顺序（降级）。
  - 单例 `rerank_service = RerankService()`。

- [x] **Step 1: 新增配置项** `framework/config.py`

在 Task 4 新增的 `HYBRID_SEARCH_ENABLED` 之后新增：

```python
    RERANK_ENABLED = os.environ.get("RERANK_ENABLED", "true").lower() == "true"
    RERANK_MODEL = os.environ.get("RERANK_MODEL") or "BAAI/bge-reranker-v2-m3"
    RERANK_TIMEOUT = int(os.environ.get("RERANK_TIMEOUT") or 30)
```

- [x] **Step 2: 编写失败测试** `tests/test_reranker.py`

```python
"""测试 Rerank 精排调用与降级路径。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.rag.reranker import RerankService
from framework.config import Config

CANDIDATES = [
    {"content": "文本一", "metadata": {"source": "a.pdf"}},
    {"content": "文本二", "metadata": {"source": "b.pdf"}},
    {"content": "文本三", "metadata": {"source": "c.pdf"}},
]


def test_rerank_disabled_returns_original(monkeypatch):
    monkeypatch.setattr(Config, "RERANK_ENABLED", False)
    svc = RerankService()
    assert svc.is_available() is False
    assert svc.rerank("q", CANDIDATES) == CANDIDATES


def test_rerank_empty_candidates_returns_empty(monkeypatch):
    monkeypatch.setattr(Config, "RERANK_ENABLED", True)
    monkeypatch.setattr(Config, "SILICONFLOW_API_KEY", "sk-test")
    svc = RerankService()
    assert svc.rerank("q", []) == []


def test_rerank_reranks_by_relevance(monkeypatch):
    monkeypatch.setattr(Config, "RERANK_ENABLED", True)
    monkeypatch.setattr(Config, "SILICONFLOW_API_KEY", "sk-test")

    import requests

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [
                {"index": 2, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.7},
            ]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert json["model"] == Config.RERANK_MODEL
        assert json["query"] == "q"
        assert json["documents"] == ["文本一", "文本二", "文本三"]
        assert json["top_n"] == 3  # min(len(candidates)=3, RETRIEVAL_TOP_K=5)
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    svc = RerankService()
    ranked = svc.rerank("q", CANDIDATES)
    # index 2 分数高排第一，index 0 次之
    assert [d["content"] for d in ranked] == ["文本三", "文本一"]


def test_rerank_api_exception_falls_back(monkeypatch):
    monkeypatch.setattr(Config, "RERANK_ENABLED", True)
    monkeypatch.setattr(Config, "SILICONFLOW_API_KEY", "sk-test")

    import requests

    def fake_post(url, headers=None, json=None, timeout=None):
        raise requests.exceptions.Timeout("mock timeout")

    monkeypatch.setattr(requests, "post", fake_post)
    svc = RerankService()
    assert svc.rerank("q", CANDIDATES) == CANDIDATES
```

- [x] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_reranker.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'framework.rag.reranker'`）

- [x] **Step 4: 编写最小实现** `framework/rag/reranker.py`

```python
from __future__ import annotations
from typing import List, Dict

import requests

from framework.config import Config


class RerankService:
    """SiliconFlow BGE-Reranker 精排，与 embedding/service.py 同栈（requests 直连）。"""

    def is_available(self) -> bool:
        return bool(Config.RERANK_ENABLED and Config.SILICONFLOW_API_KEY)

    def rerank(self, query: str, candidates: List[Dict]) -> List[Dict]:
        if not self.is_available() or not candidates:
            return candidates

        top_n = min(len(candidates), Config.RETRIEVAL_TOP_K)
        try:
            resp = requests.post(
                f"{Config.SILICONFLOW_BASE_URL}/rerank",
                headers={
                    "Authorization": f"Bearer {Config.SILICONFLOW_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": Config.RERANK_MODEL,
                    "query": query,
                    "documents": [c.get("content", "") for c in candidates],
                    "top_n": top_n,
                },
                timeout=Config.RERANK_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            items = sorted(
                data.get("results", []),
                key=lambda x: x.get("relevance_score", 0.0),
                reverse=True,
            )
            ranked = [candidates[item["index"]] for item in items
                      if 0 <= item.get("index", -1) < len(candidates)]
            return ranked if ranked else candidates
        except Exception as e:
            print(f"[Rerank] API 调用失败，降级原顺序: {e}")
            return candidates


rerank_service = RerankService()
```

- [x] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_reranker.py -v`
Expected: PASS（4 个用例全绿）

- [x] **Step 6: 提交**

```bash
git add framework/rag/reranker.py framework/config.py tests/test_reranker.py
git commit -m "feat(kb): add SiliconFlow rerank service with degradation"
```

---

### Task 7: 在 RAGChain 检索后接入精排（tasks.md 3.2）

**Files:**
- Modify: `framework/rag/chain.py:2-7`（加 import）、`framework/rag/chain.py:115-124`（`_retrieve_documents`）
- Test: `tests/test_reranker.py`（追加链级流程单测）

**Interfaces:**
- Consumes: `vector_store.hybrid_search(query, n_results, filters)`（Task 4）、`rerank_service.rerank(query, candidates)`（Task 6）、`Config.RECALL_TOP_K` / `Config.RETRIEVAL_TOP_K` / `Config.RERANK_ENABLED`。
- Produces: `_retrieve_documents(query, valid_doc_names) -> {"results": [...], "count": N}`，结果始终截断到 `RETRIEVAL_TOP_K`；`chat()` / `chat_stream()` 来源收集逻辑不变（结果仍带 `metadata.source`）。

- [x] **Step 1: 新增 import**

在 `framework/rag/chain.py` 顶部 import 区（`from framework.vector_store.chroma_store import vector_store` 之后）加入：

```python
from framework.rag.reranker import rerank_service
```

- [x] **Step 2: 替换 `_retrieve_documents`**

把 `framework/rag/chain.py` 第 115-124 行：

```python
    def _retrieve_documents(self, query: str, valid_doc_names: Optional[set]) -> Dict[str, Any]:
        filters = None
        if valid_doc_names:
            filters = {"source": {"$in": list(valid_doc_names)}}

        return self.vector_store.search(
            query=query,
            n_results=Config.RETRIEVAL_TOP_K,
            filters=filters,
        )
```

改为：

```python
    def _retrieve_documents(self, query: str, valid_doc_names: Optional[set]) -> Dict[str, Any]:
        filters = {"source": {"$in": list(valid_doc_names)}} if valid_doc_names else None
        recalled = self.vector_store.hybrid_search(
            query=query, n_results=Config.RECALL_TOP_K, filters=filters)
        results = recalled["results"]
        if Config.RERANK_ENABLED and len(results) > Config.RETRIEVAL_TOP_K:
            results = rerank_service.rerank(query, results)
        return {"results": results[:Config.RETRIEVAL_TOP_K],
                "count": len(results[:Config.RETRIEVAL_TOP_K])}
```

（`chat_stream()` 走同一个 `_retrieve_documents`，无需改动。）

- [x] **Step 3: 追加链级流程测试**（追加到 `tests/test_reranker.py` 末尾）

```python
def test_rag_chain_retrieve_triggers_rerank(monkeypatch):
    from framework.rag.chain import rag_chain
    from framework.rag import reranker as reranker_mod

    monkeypatch.setattr(Config, "RECALL_TOP_K", 20)
    monkeypatch.setattr(Config, "RETRIEVAL_TOP_K", 5)
    monkeypatch.setattr(Config, "RERANK_ENABLED", True)

    recalled = {
        "results": [{"content": f"c{i}", "metadata": {"source": "s"}} for i in range(20)],
        "count": 20,
    }

    class FakeVS:
        def hybrid_search(self, query, n_results=None, filters=None):
            return recalled

    monkeypatch.setattr(rag_chain, "vector_store", FakeVS())

    seen = {}

    def fake_rerank(query, candidates):
        seen["n"] = len(candidates)
        return list(reversed(candidates))[:5]

    monkeypatch.setattr(reranker_mod.rerank_service, "rerank", fake_rerank)

    result = rag_chain._retrieve_documents("查询农耕", {"s"})
    assert seen["n"] == 20
    assert result["count"] == 5
    assert len(result["results"]) == 5
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_reranker.py -v`
Expected: PASS（5 个用例全绿，含新增链级流程测试）

- [x] **Step 5: 提交**

```bash
git add framework/rag/chain.py tests/test_reranker.py
git commit -m "feat(kb): wire rerank between recall and generation"
```

---

## 组四：验证回归

### Task 8: 全量回归测试（tasks.md 4.1）

**Files:** 无代码改动。

- [x] **Step 1: 运行完整测试套件**

Run: `python -m pytest -q`
Expected: 全部通过，现有 86 个测试无回归。重点关注：`tests/test_rag.py`、`tests/test_upload.py`、`tests/test_docs_dedup.py`、`tests/test_config.py`，以及本次新增的 `test_chunker.py` / `test_bm25_store.py` / `test_hybrid_search.py` / `test_reranker.py`。

- [x] **Step 2: 若出现回归，按回滚计划逐层排查**

   1. `RERANK_ENABLED=False` 重跑，确认是否精排引入。
   2. `HYBRID_SEARCH_ENABLED=False` 重跑，确认是否混合检索引入。
   3. `RECALL_TOP_K=5`（环境变量）重跑，对齐旧行为。

   修复后回到 Step 1 重跑，直至全绿。

- [x] **Step 3: 记录结果**

在 `docs/superpowers/reports/` 下由执行者输出 verify 报告（本 change 归档流程的一部分），记录通过数与收敛过程。

---

### Task 9: 端到端术语命中验证（tasks.md 4.2）

**Files:** 无代码改动（手动验证）。

- [x] **Step 1: 准备含术语文档**

准备一份含「交换性氢」「有效钾」等耕地术语的 txt/md/docx 文档。

- [x] **Step 2: 上传并查询**

   1. 通过上传接口 `/api/v1/docs/upload` 上传该文档（新入库才会走新分块 + BM25 索引；旧 chunk 不受影响）。
   2. 通过问答接口查询「土壤交换性氢含量如何影响酸度」「有效钾的作物养分意义」等。

- [x] **Step 3: 对比命中率**

对照改前（纯向量 top-5）的命中情况，确认术语查询能命中含术语的 chunk 且来源（`sources`）正确。

- [x] **Step 4: 记录结论**

若命中率提升明显，在 verify 报告注明「交换性氢 / 有效钾 命中率提升，符合预期」；若某术语因 jieba 默认词典切分不当未命中，记录为已知边界（术语词库优化留待 `kb-semantic-enrichment`，与本 change 的非目标一致）。

---
