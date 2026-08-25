---
change: kb-semantic-enrichment
design-doc: docs/superpowers/specs/2026-08-25-kb-semantic-enrichment-design.md
base-ref: 1470acdcd1a52bffacfd1ff94fed44e039293a68
---

# kb-semantic-enrichment 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务执行本计划。步骤用复选框（`- [ ]`）语法跟踪进度。

**Goal:** 在 P0 混合检索（向量 + BM25 + RRF + 精排）之上补齐语义增强层：查询整词同义词预处理、chunk 级元数据增强、按 category 的分领域 collection 路由（关键词路由 + 全库回退），提升耕地专业术语（交换性氢、有效钾等）的检索命中率。

**Architecture:** 新增纯函数 `synonyms.load_synonyms/normalize_query` 做整词同义词替换；新增 `category_router.route_category` 复用 `framework/agents/routing.py` 的题型关键词映射到领域 category；`ChromaVectorStore` 从单句柄改为按 category 的多 collection 多 BM25 句柄（命名 `kb_<slug(category)>`，空/other 归入 `enterprise_kb`），`search`/`hybrid_search` 支持「定向命中 + 全库回退」；入库侧 `docs.py` 为每个 chunk 写入 `category/treatment_type/chunk_index` 元数据。三个能力相互独立，可分别接入与回退。

**Tech Stack:** Python 3.10+、Flask、ChromaDB、jieba、rank_bm25、pytest。

## Global Constraints

- 本阶段**不新增** `framework/config.py` 配置项：同义词预处理与 category 路由无独立开关，回退由「空词表原样返回 / 未命中全库回退」保证（区别于 P0 的 `HYBRID_SEARCH_ENABLED`/`RERANK_ENABLED` 开关）。
- 同义词替换仅**整词匹配**：不做子串或正则贪婪替换；同义词两侧若接英文字母/数字/下划线则跳过，长同义词优先匹配（避免"水解性"误伤"水解性氮"）。
- collection 命名：`kb_<slug(category)>`；category 为空或 `other` 时归入默认 `enterprise_kb`（即 `Config.CHROMA_COLLECTION_NAME`）。
- category 路由策略：关键词/规则判断 + 全库回退，**不采用 LLM 判断**。
- 规范 category 词汇表（与 `framework/agents/capabilities.py` 的 `domain` 字段对齐）：`stability` / `grade` / `problem` / `acidification` / `organic_matter` / `fertility`。
- `page`/`section` **本阶段不写入**（`parse_document` 当前不产出页码/章节），留 P 后续改造解析器再补。
- 命名与路径严格遵循设计文档：
  - 新增 `framework/rag/soil_synonyms.json`、`framework/rag/synonyms.py`、`framework/rag/category_router.py`、`scripts/rebuild_collections.py`。
  - 修改 `framework/rag/chain.py`、`framework/vector_store/chroma_store.py`、`framework/api/routes/docs.py`。
- 语言：代码注释、测试断言说明使用简体中文。
- 提交信息格式：`feat(kb): ...` / `test(kb): ...`。
- 测试兼容：`tests/conftest.py` 默认关闭 function calling；`tests/test_hybrid_search.py` 与 `tests/test_reranker.py` 用 `__new__` 构造无初始化实例测纯函数与回退分支，改造 `ChromaVectorStore` 时必须保持 `hybrid_search` 关闭分支调用形态为 `self.search(query, n_results, filters)`（三个位置参数），并保持 `_rrf_fuse` 为静态方法。

---

## 组一：同义词预处理

### Task 1: 新增同义词词表与整词替换函数（tasks.md 1.1 + 1.2 + 1.4）

**Files:**
- Create: `framework/rag/soil_synonyms.json`
- Create: `framework/rag/synonyms.py`
- Test: `tests/test_synonyms.py`

**Interfaces:**
- Consumes: 无（纯新增）。
- Produces: `framework/rag/synonyms.py`：
  - `load_synonyms() -> dict`：读取词表 JSON 返回 `{规范词: [同义词...]}`；文件缺失/解析失败返回 `{}`，不抛异常。
  - `normalize_query(text: str) -> str`：整词同义词替换（同义词 → 规范词），未命中原样保留；词表为空或文本为空 → 原样返回。
  - 模块级常量 `_SYNONYM_PATH`、`_cache`（供测试 monkeypatch 复位缓存）。

- [x] **Step 1: 编写失败测试** `tests/test_synonyms.py`

```python
"""测试耕地领域同义词整词替换。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.rag.synonyms import normalize_query, load_synonyms


def test_load_synonyms_returns_dict():
    data = load_synonyms()
    assert isinstance(data, dict)
    assert "交换性氢" in data


def test_hit_replacement():
    # 命中：同义词 → 规范词
    assert normalize_query("可交换氢") == "交换性氢"


def test_hit_replacement_cjk_embedded():
    # 中文相邻（无空格）也视为整词命中
    assert normalize_query("土壤可交换氢含量偏高") == "土壤交换性氢含量偏高"


def test_unmatched_passthrough():
    # 规范词本身 / 未收录词 → 原样
    assert normalize_query("交换性氢") == "交换性氢"
    assert normalize_query("有机质含量") == "有机质含量"
    assert normalize_query("重金属污染") == "重金属污染"


def test_whole_word_ascii_boundary_no_misfire(monkeypatch):
    from framework.rag import synonyms as syn
    monkeypatch.setattr(syn, "load_synonyms", lambda: {"有效钾": ["速效钾"]})
    # 同义词两侧接英文/数字时视为更大词的一部分，跳过替换
    assert syn.normalize_query("abc速效钾") == "abc速效钾"
    assert syn.normalize_query("速效钾x") == "速效钾x"


def test_longest_first_avoid_substring_misfire(monkeypatch):
    from framework.rag import synonyms as syn
    # 长同义词"水解性氮"应先于短同义词"水解性"匹配
    monkeypatch.setattr(syn, "load_synonyms", lambda: {"碱解氮": ["水解性氮", "水解性"]})
    assert syn.normalize_query("水解性氮含量") == "碱解氮含量"


def test_empty_dict_passthrough(monkeypatch):
    from framework.rag import synonyms as syn
    monkeypatch.setattr(syn, "load_synonyms", lambda: {})
    assert syn.normalize_query("可交换氢") == "可交换氢"


def test_load_synonyms_missing_file_returns_empty(monkeypatch):
    from framework.rag import synonyms as syn
    monkeypatch.setattr(syn, "_cache", None)
    monkeypatch.setattr(syn, "_SYNONYM_PATH", "/nonexistent/path/soil_synonyms.json")
    assert syn.load_synonyms() == {}
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_synonyms.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'framework.rag.synonyms'`）

- [x] **Step 3: 编写词表** `framework/rag/soil_synonyms.json`

```json
{
  "交换性氢": ["可交换氢", "交换性酸"],
  "有效钾": ["速效钾", "有效态钾"],
  "有效磷": ["速效磷", "有效态磷"],
  "有效氮": ["速效氮"],
  "碱解氮": ["水解性氮"],
  "阳离子交换量": ["CEC", "阳离子交换容量"],
  "有机质": ["腐殖质", "土壤有机质"],
  "全氮": ["总氮"],
  "全磷": ["总磷"],
  "全钾": ["总钾"],
  "容重": ["土壤容重", "体积质量"],
  "酸碱度": ["pH值", "酸度"],
  "培肥": ["培肥地力", "土壤培肥"],
  "秸秆还田": ["秸秆翻压", "秸秆覆盖"],
  "调理剂": ["土壤改良剂", "酸性土壤调理剂"],
  "石灰": ["生石灰", "石灰石"],
  "有机肥": ["农家肥", "堆肥"],
  "耕地": ["农田", "农地"],
  "障碍因素": ["障碍因子", "限制因素"],
  "质量等级": ["质量评级", "等级评定"],
  "稳定性": ["稳定程度"],
  "退化风险": ["地力退化"],
  "综合指数": ["耕地质量综合指数"],
  "土层厚度": ["耕层厚度", "有效土层厚度"],
  "持水量": ["田间持水量"],
  "孔隙度": ["土壤孔隙度", "总孔隙度"],
  "速效养分": ["有效养分含量"],
  "交换性钙": ["有效钙"],
  "交换性镁": ["有效镁"],
  "盐基饱和度": ["盐基交换饱和度"]
}
```

- [x] **Step 4: 编写最小实现** `framework/rag/synonyms.py`

```python
"""耕地领域同义词预处理：查询整词替换为规范术语。"""
from __future__ import annotations

import json
import os
import re
from typing import Dict

_SYNONYM_PATH = os.path.join(os.path.dirname(__file__), "soil_synonyms.json")
_ASCII_WORD = re.compile(r"[0-9A-Za-z_]")

_cache = None


def load_synonyms() -> Dict[str, list]:
    """读取词表 JSON 返回 {规范词: [同义词...]}；文件缺失/解析失败返回 {}，不抛异常。"""
    global _cache
    if _cache is not None:
        return _cache
    data: Dict[str, list] = {}
    try:
        with open(_SYNONYM_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data = loaded
    except Exception:
        data = {}
    _cache = data
    return data


def _is_word_char(ch: str) -> bool:
    """整词边界：英文字母/数字/下划线视为"词内字符"，两侧出现时不做替换。"""
    return bool(_ASCII_WORD.match(ch))


def normalize_query(text: str) -> str:
    """整词同义词替换：同义词 → 规范词。

    - 词表为空或文本为空 → 原样返回
    - 长同义词优先匹配，避免子串误伤（如"水解性氮"先于"水解性"）
    - 仅整词匹配：同义词两侧若接英文字母/数字/下划线则跳过
    """
    synonyms = load_synonyms()
    if not synonyms or not text:
        return text

    pairs = []
    for canonical, alts in synonyms.items():
        for alt in alts:
            pairs.append((alt, canonical))
    pairs.sort(key=lambda p: -len(p[0]))

    result = text
    for alt, canonical in pairs:
        pattern = re.compile(re.escape(alt))
        current = result

        def _repl(m, current=current):
            start, end = m.start(), m.end()
            if start > 0 and _is_word_char(current[start - 1]):
                return m.group(0)
            if end < len(current) and _is_word_char(current[end]):
                return m.group(0)
            return canonical

        result = pattern.sub(_repl, current)
    return result
```

- [x] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_synonyms.py -v`
Expected: PASS（8 个用例全绿）

- [x] **Step 6: 提交**

```bash
git add framework/rag/soil_synonyms.json framework/rag/synonyms.py tests/test_synonyms.py
git commit -m "feat(kb): add soil synonym dict and whole-word query normalizer"
```

---

### Task 2: 在 RAGChain 检索前接入同义词预处理（tasks.md 1.3）

**Files:**
- Modify: `framework/rag/chain.py:7-8`（加 import）、`framework/rag/chain.py:116-124`（`_retrieve_documents`）
- Test: `tests/test_reranker.py`（追加链级流程测试）

**Interfaces:**
- Consumes: `normalize_query(text: str) -> str`（Task 1 产出）。
- Produces: `_retrieve_documents(query, valid_doc_names)` 在调用 `hybrid_search` 前以 `normalize_query(query)` 作为召回 query；`rerank` 仍使用原始 `query`（设计文档仅要求「规范化后的 query 用于向量与 BM25 两路召回」）。

- [x] **Step 1: 新增 import**

在 `framework/rag/chain.py` 顶部 import 区（`from framework.rag.reranker import rerank_service` 之后）加入：

```python
from framework.rag.synonyms import normalize_query
```

- [x] **Step 2: 修改 `_retrieve_documents`**

把 `framework/rag/chain.py` 第 116-124 行：

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

改为：

```python
    def _retrieve_documents(self, query: str, valid_doc_names: Optional[set]) -> Dict[str, Any]:
        normalized_query = normalize_query(query)
        filters = {"source": {"$in": list(valid_doc_names)}} if valid_doc_names else None
        recalled = self.vector_store.hybrid_search(
            query=normalized_query, n_results=Config.RECALL_TOP_K, filters=filters)
        results = recalled["results"]
        if Config.RERANK_ENABLED and len(results) > Config.RETRIEVAL_TOP_K:
            results = rerank_service.rerank(query, results)
        return {"results": results[:Config.RETRIEVAL_TOP_K],
                "count": len(results[:Config.RETRIEVAL_TOP_K])}
```

（`rerank` 仍用原始 `query`，遵循设计文档范围；`chat_stream()` 走同一个 `_retrieve_documents`，无需改动。）

- [x] **Step 3: 追加链级流程测试**（追加到 `tests/test_reranker.py` 末尾）

```python
def test_rag_chain_normalizes_query_before_recall(monkeypatch):
    from framework.rag.chain import rag_chain
    from framework.rag import chain as chain_mod

    monkeypatch.setattr(Config, "RECALL_TOP_K", 20)
    monkeypatch.setattr(Config, "RETRIEVAL_TOP_K", 5)
    monkeypatch.setattr(Config, "RERANK_ENABLED", False)

    recalled = {"results": [], "count": 0}
    seen = {}

    def fake_normalize(query):
        return query.replace("速效钾", "有效钾")

    monkeypatch.setattr(chain_mod, "normalize_query", fake_normalize)

    class FakeVS:
        def hybrid_search(self, query, n_results=None, filters=None):
            seen["query"] = query
            return recalled

    monkeypatch.setattr(rag_chain, "vector_store", FakeVS())

    rag_chain._retrieve_documents("速效钾含量", None)
    assert seen["query"] == "有效钾含量"
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_reranker.py tests/test_synonyms.py -v`
Expected: PASS（含新增链级流程测试 + 原有 5 个 reranker 用例全绿）

- [x] **Step 5: 提交**

```bash
git add framework/rag/chain.py tests/test_reranker.py
git commit -m "feat(kb): normalize query before hybrid recall"
```

---

## 组二：chunk 元数据增强

### Task 3: 入库写入 chunk 级元数据（tasks.md 2.1 + 2.2 + 2.3）

**Files:**
- Modify: `framework/api/routes/docs.py:120`（metadatas 构造）
- Test: `tests/test_metadata.py`

**Interfaces:**
- Consumes: `split_text(content) -> list[str]`（P0 已有）、`category`/`treatment_type`（`docs.py:80-81` 已从 form 读取）。
- Produces: 上传入库的 `metadatas` 逐 chunk 携带 `source`/`category`/`treatment_type`/`chunk_index`；`page`/`section` 不写入。`add_documents` 调用签名本任务不变（`category` 路由参数在 Task 6 引入）。

- [x] **Step 1: 编写失败测试** `tests/test_metadata.py`

```python
"""测试上传入库时写入 chunk 级元数据。"""
import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.api.app import create_app
from framework.models.user import db, User
from framework.config import Config, SQLiteConfig
from werkzeug.security import generate_password_hash


class CaptureVectorStore:
    def __init__(self):
        self.captured = None

    def add_documents(self, texts, metadatas=None, ids=None):
        self.captured = {"texts": texts, "metadatas": metadatas, "ids": ids}
        return len(texts) if texts else 0

    def delete_by_source(self, source_doc_name):
        return 0


@pytest.fixture
def client(monkeypatch):
    tmp_upload = tempfile.mkdtemp(prefix="test_meta_upload_")
    tmp_db_dir = tempfile.mkdtemp(prefix="test_meta_db_")
    tmp_db_path = os.path.join(tmp_db_dir, "test.db")

    original_folder = Config.UPLOAD_FOLDER
    original_db_uri = SQLiteConfig.SQLALCHEMY_DATABASE_URI
    Config.UPLOAD_FOLDER = tmp_upload
    SQLiteConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_db_path}"

    app = create_app("sqlite")
    app.config["TESTING"] = True

    capture_vs = CaptureVectorStore()
    monkeypatch.setattr("framework.api.routes.docs.vector_store", capture_vs)

    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = User(username="admin", password=generate_password_hash("admin123"),
                     nickname="管理员", role="admin", status=1)
        db.session.add(admin)
        db.session.commit()

    client = app.test_client()
    client._app = app
    client._capture_vs = capture_vs
    client._admin_id = admin.id

    yield client

    Config.UPLOAD_FOLDER = original_folder
    SQLiteConfig.SQLALCHEMY_DATABASE_URI = original_db_uri
    shutil.rmtree(tmp_upload, ignore_errors=True)
    shutil.rmtree(tmp_db_dir, ignore_errors=True)


def _login(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.get_json()["data"]["token"]


def test_upload_writes_chunk_metadata(client):
    token = _login(client)
    content = "土壤" * 1000  # 足够长以产生多块
    resp = client.post(
        "/api/v1/docs/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file": (io.BytesIO(content.encode("utf-8")), "meta.txt"),
            "category": "acidification",
            "treatment_type": "regulation",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200

    captured = client._capture_vs.captured
    assert captured is not None
    metadatas = captured["metadatas"]
    texts = captured["texts"]
    assert len(metadatas) == len(texts) > 0
    for i, meta in enumerate(metadatas):
        assert meta["source"] == "meta.txt"
        assert meta["category"] == "acidification"
        assert meta["treatment_type"] == "regulation"
        assert meta["chunk_index"] == i
    # page / section 本阶段不写入
    assert "page" not in metadatas[0]
    assert "section" not in metadatas[0]
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_metadata.py -v`
Expected: FAIL（`assert meta["category"] == "acidification"` 失败：当前 metadatas 仅含 `source`）

- [x] **Step 3: 修改 metadatas 构造** `framework/api/routes/docs.py:120`

把：

```python
            chunks = split_text(content)
            metadatas = [{"source": file.filename} for _ in chunks]
```

改为：

```python
            chunks = split_text(content)
            metadatas = [{
                "source": file.filename,
                "category": category,
                "treatment_type": treatment_type,
                "chunk_index": i,
            } for i in range(len(chunks))]
```

（`added_count` / `chunk_count` / 后续入库逻辑不动；`category`/`treatment_type` 已定义于 `docs.py:80-81`。）

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_metadata.py -v`
Expected: PASS（1 个用例全绿）

- [x] **Step 5: 提交**

```bash
git add framework/api/routes/docs.py tests/test_metadata.py
git commit -m "feat(kb): store chunk-level category/treatment_type/chunk_index metadata"
```

---

## 组三：分领域 collection

### Task 4: ChromaVectorStore 多 collection 路由（tasks.md 3.1）

**Files:**
- Modify: `framework/vector_store/chroma_store.py`（`import re`、`__init__`、`_init_client`、新增 `slugify`/`collection_name_for`/`_get_collection`/`_targeted_collection`/`_bm25_for`/`_bm25_search`/`_search_in`，改造 `add_documents`/`search`/`hybrid_search`/`delete_by_source`/`get_collection_stats`/`clear`）
- Test: `tests/test_collection_routing.py`

**Interfaces:**
- Consumes: `BM25Store`（P0 已有）、`Config.CHROMA_COLLECTION_NAME`（已存在）。
- Produces:
  - 模块级纯函数：`slugify(category: str) -> str`、`collection_name_for(category: Optional[str]) -> str`。
  - `add_documents(texts, metadatas=None, ids=None, category=None) -> int`
  - `search(query, n_results=3, filters=None, category=None) -> Dict[str, Any]`
  - `hybrid_search(query, n_results=20, filters=None, category=None) -> Dict[str, Any]`
  - 实例方法 `_get_collection(category)` / `_targeted_collection(category)` / `_bm25_for(category)` / `_bm25_search(query, n_results, filters, category)` / `_search_in(collection, query, n_results, filters)`。
  - 保持 `hybrid_search` 关闭分支 `return self.search(query, n_results, filters)`（3 位置参数）以兼容 `tests/test_hybrid_search.py`；保持 `_rrf_fuse` 为静态方法、`search()` 返回 `{"results": [...], "count": N}` 与 `results[*].content/.metadata/.distance` 结构不变。

- [x] **Step 1: 编写失败测试** `tests/test_collection_routing.py`

```python
"""测试分领域 collection 路由（离线，不触发 Chroma 初始化）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.config import Config
from framework.vector_store.chroma_store import (
    ChromaVectorStore,
    slugify,
    collection_name_for,
)


class FakeCollection:
    def __init__(self, name):
        self.name = name


class FakeClient:
    def __init__(self):
        self.created = []

    def create_collection(self, name, embedding_function=None):
        self.created.append(name)
        return FakeCollection(name)


def test_slugify_normalizes():
    assert slugify(" Acidification ") == "acidification"
    assert slugify("organic_matter") == "organic_matter"
    # 纯中文无 ASCII → 归一为 other（回退到默认库）
    assert slugify("酸化改良") == "other"


def test_collection_name_default_for_other():
    assert collection_name_for(None) == Config.CHROMA_COLLECTION_NAME
    assert collection_name_for("") == Config.CHROMA_COLLECTION_NAME
    assert collection_name_for("other") == Config.CHROMA_COLLECTION_NAME


def test_collection_name_specific():
    assert collection_name_for("acidification") == "kb_acidification"


def test_get_collection_routes_by_category():
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store._client = FakeClient()
    store._collections = {}
    store._bm25 = {}

    c1 = store._get_collection("acidification")
    c2 = store._get_collection("acidification")
    assert c1 is c2  # 懒创建后缓存命中
    assert c1.name == "kb_acidification"
    assert store._client.created == ["kb_acidification"]


def test_get_collection_default_for_other_category():
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store._client = FakeClient()
    store._collections = {}
    store._bm25 = {}
    c = store._get_collection("other")
    assert c.name == Config.CHROMA_COLLECTION_NAME


def test_targeted_collection_hit_and_miss():
    acid = FakeCollection("kb_acidification")
    default = FakeCollection(Config.CHROMA_COLLECTION_NAME)

    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store._collections = {Config.CHROMA_COLLECTION_NAME: default, "kb_acidification": acid}
    store._bm25 = {}

    # 命中：category 具体且 collection 存在 → 定向
    assert store._targeted_collection("acidification") is acid
    # 未命中：collection 不存在 → 全库回退
    assert store._targeted_collection("grade") is None
    # 空 / other → 全库回退
    assert store._targeted_collection(None) is None
    assert store._targeted_collection("other") is None
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_collection_routing.py -v`
Expected: FAIL（`ImportError: cannot import name 'slugify' from 'framework.vector_store.chroma_store'`）

- [x] **Step 3: 编写实现** `framework/vector_store/chroma_store.py`

（1）import 区加入 `import re`（在 `import shutil` 之后）：

```python
import os
import re
import shutil
```

（2）`__init__` 改为多句柄（第 37-41 行）：

```python
    def __init__(self):
        self._client = None
        self._collections: Dict[str, Any] = {}
        self._bm25: Dict[str, BM25Store] = {}
        self._init_client()
```

（3）类定义之前新增模块级纯函数：

```python
def slugify(category: str) -> str:
    """将 category 规范化为 ASCII slug；无 ASCII 字符时归为 'other'。"""
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", category.strip().lower())
    return slug.strip("_") or "other"


def collection_name_for(category: Optional[str]) -> str:
    """计算 collection 名：空/other → 默认 enterprise_kb；否则 kb_<slug>。"""
    if not category:
        return Config.CHROMA_COLLECTION_NAME
    if category.strip().lower() == "other":
        return Config.CHROMA_COLLECTION_NAME
    return f"kb_{slugify(category)}"
```

（4）`_init_client` 中所有 `self._collection = ...` 改为写入默认名键；关键两处创建点改为：

```python
            try:
                self._collections[default_name] = self._client.create_collection(
                    name=default_name,
                    embedding_function=NoOpEmbeddingFunction(),
                )
                print(f"[Chroma] 集合 '{default_name}' 初始化完成")
            except Exception as e:
                print(f"[Chroma] 创建集合失败: {e}，清理持久化目录后重试")
                try:
                    self._client = None
                    shutil.rmtree(persist_dir, ignore_errors=True)
                    os.makedirs(persist_dir, exist_ok=True)
                    self._client = chromadb.PersistentClient(
                        path=persist_dir,
                        settings=Settings(
                            anonymized_telemetry=False,
                            allow_reset=False,
                        )
                    )
                    self._collections[default_name] = self._client.create_collection(
                        name=default_name,
                        embedding_function=NoOpEmbeddingFunction(),
                    )
                    print(f"[Chroma] 集合 '{default_name}' 初始化完成（已重建持久化目录）")
                except Exception as e2:
                    print(f"Chroma初始化失败: {e2}")
```

（在 `_init_client` 开头 `persist_dir = ...` 之后加 `default_name = Config.CHROMA_COLLECTION_NAME`，并将原 `collection_name` 引用替换为 `default_name`；`need_recreate` 检测逻辑不变，仅名称变量替换。）

（5）新增实例方法 `_get_collection` / `_targeted_collection` / `_bm25_for`（放在 `_init_client` 之后）：

```python
    def _get_collection(self, category: Optional[str] = None):
        """按 category 懒创建/获取 collection（空/other → 默认 enterprise_kb）。"""
        name = collection_name_for(category)
        if name not in self._collections:
            collection = self._client.create_collection(
                name=name, embedding_function=NoOpEmbeddingFunction())
            self._collections[name] = collection
        return self._collections[name]

    def _targeted_collection(self, category: Optional[str] = None):
        """category 具体且对应 collection 已存在 → 返回；否则 None（全库回退）。"""
        if not category or category.strip().lower() == "other":
            return None
        return self._collections.get(collection_name_for(category))

    def _bm25_for(self, category: Optional[str] = None) -> BM25Store:
        """按 category 懒获取 BM25 索引（空/other → 默认）。"""
        name = collection_name_for(category)
        if name not in self._bm25:
            self._bm25[name] = BM25Store()
        return self._bm25[name]
```

（6）`add_documents` 改为按 category 路由写入（第 127-151 行）：

```python
    def add_documents(self, texts: List[str], metadatas: Optional[List[Dict]] = None,
                      ids: Optional[List[str]] = None, category: Optional[str] = None) -> int:
        """添加文档：按 category 路由到分领域 collection，并同步对应 BM25。"""
        if not self._client:
            return 0

        if not embedding_service.is_available():
            print("[Chroma] embedding_service 不可用，跳过向量化")
            return 0

        try:
            embeddings = embedding_service.embed_documents(texts)

            collection = self._get_collection(category)
            collection.add(
                ids=ids or [f"doc_{i}" for i in range(len(texts))],
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas or [],
            )
            self._bm25_for(category).add_documents(texts, metadatas)
            return len(texts)
        except Exception as e:
            print(f"添加文档失败: {e}")
            return 0
```

（7）`search` 拆出 `_search_in` 并支持 category 定向/全库回退（第 153-189 行）：

```python
    def _search_in(self, collection, query: str, n_results: int,
                   filters: Optional[Dict]) -> List[Dict]:
        """对单个 collection 做向量召回，返回 [{content, metadata, distance}...]。"""
        query_embedding = embedding_service.embed_query(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filters,
        )
        formatted: List[Dict] = []
        for i in range(len(results.get("documents", []))):
            docs = results["documents"][i]
            metas = results.get("metadatas", [[]])[i]
            dists = results.get("distances", [[]])[i]
            for j, doc in enumerate(docs):
                formatted.append({
                    "content": doc,
                    "metadata": metas[j] if j < len(metas) else {},
                    "distance": dists[j] if j < len(dists) else 0,
                })
        return formatted

    def search(self, query: str, n_results: int = 3, filters: Optional[Dict] = None,
               category: Optional[str] = None) -> Dict[str, Any]:
        if not self._collections:
            return {"results": [], "count": 0}

        if not embedding_service.is_available():
            print("[Chroma] embedding_service 不可用，无法搜索")
            return {"results": [], "count": 0}

        try:
            target = self._targeted_collection(category)
            if target is not None:
                formatted = self._search_in(target, query, n_results, filters)
            else:
                formatted = []
                for collection in self._collections.values():
                    formatted.extend(self._search_in(collection, query, n_results, filters))
                # 全库回退：向量距离越小越相关，升序取 top-n
                formatted.sort(key=lambda r: r.get("distance", 0))
                formatted = formatted[:n_results]
            return {"results": formatted, "count": len(formatted)}
        except Exception as e:
            print(f"搜索失败: {e}")
            return {"results": [], "count": 0}
```

（8）`hybrid_search` 支持 category 并新增 `_bm25_search`（第 191-203 行）：

```python
    def hybrid_search(self, query: str, n_results: int = 20, filters: Optional[Dict] = None,
                      category: Optional[str] = None) -> Dict[str, Any]:
        """双路召回：向量 + BM25，RRF 融合（支持 category 定向，否则全库回退）。

        Config.HYBRID_SEARCH_ENABLED=False 时回退纯向量单路（回滚路径）。
        """
        if not Config.HYBRID_SEARCH_ENABLED:
            return self.search(query, n_results, filters)

        vector_res = self.search(query, n_results, filters, category)
        bm25_docs = self._bm25_search(query, n_results, filters, category)
        fused = self._rrf_fuse(vector_res["results"], bm25_docs, k=Config.RRF_K)
        fused = fused[:n_results]
        return {"results": fused, "count": len(fused)}

    def _bm25_search(self, query: str, n_results: int, filters: Optional[Dict],
                     category: Optional[str] = None) -> List[Dict]:
        """BM25 召回：category 定向时单库；否则聚合所有分领域 BM25 后取 top-n。"""
        if self._targeted_collection(category) is not None:
            return self._bm25_for(category).search(query, n_results, filters)
        all_docs: List[Dict] = []
        for store in self._bm25.values():
            all_docs.extend(store.search(query, n_results, filters))
        all_docs.sort(key=lambda d: -d.get("score", 0.0))
        return all_docs[:n_results]
```

（9）`delete_by_source` / `get_collection_stats` / `clear` 改为多 collection 语义（第 220-264 行）：

```python
    def delete_by_source(self, source_doc_name: str) -> int:
        """从所有 collection 删除指定 source 的文档，并同步各 BM25。"""
        if not self._collections:
            return 0
        total_removed = 0
        for collection in self._collections.values():
            try:
                count_before = collection.count()
                collection.delete(where={"source": source_doc_name})
                count_after = collection.count()
                total_removed += count_before - count_after
            except Exception as e:
                print(f"删除失败: {e}")
        for store in self._bm25.values():
            try:
                store.delete_by_source(source_doc_name)
            except Exception as e:
                print(f"BM25 删除失败: {e}")
        return total_removed

    def get_collection_stats(self) -> Dict[str, Any]:
        if not self._collections:
            return {"count": 0, "name": ""}
        total = 0
        names = []
        for name, collection in self._collections.items():
            names.append(name)
            try:
                total += collection.count()
            except Exception as e:
                print(f"获取统计失败: {e}")
        return {"count": total, "name": ",".join(names)}

    def clear(self) -> int:
        """清空所有 collection 及其 BM25，返回删除前总文档数。"""
        if not self._collections:
            return 0
        total_removed = 0
        for collection in self._collections.values():
            try:
                count_before = collection.count()
                if count_before == 0:
                    continue
                all_data = collection.get()
                ids = all_data.get("ids", [])
                if ids:
                    collection.delete(ids=ids)
                total_removed += count_before
            except Exception as e:
                print(f"清空集合失败: {e}")
        for store in self._bm25.values():
            store.clear()
        return total_removed
```

（`_rrf_fuse` 静态方法保持不变；`delete_by_source` 改为遍历所有 collection 以覆盖未记录 category 的存量数据。）

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_collection_routing.py tests/test_hybrid_search.py -v`
Expected: PASS（`test_collection_routing.py` 6 个用例 + `test_hybrid_search.py` 3 个用例全绿；`hybrid_search` 关闭分支调用形态未变，`_rrf_fuse` 未受影响）

- [x] **Step 5: 提交**

```bash
git add framework/vector_store/chroma_store.py tests/test_collection_routing.py
git commit -m "feat(kb): route vector store into per-category collections"
```

---

### Task 5: 新增 category 关键词路由（tasks.md 3.1 路由组件）

**Files:**
- Create: `framework/rag/category_router.py`
- Test: `tests/test_category_router.py`

**Interfaces:**
- Consumes: `QUESTION_TYPE_1_KEYWORDS` ~ `QUESTION_TYPE_6_KEYWORDS`（复用 `framework/agents/routing.py` 中的题型关键词）。
- Produces: `route_category(query: str) -> Optional[str]`：判断查询目标 category slug（`stability`/`grade`/`problem`/`acidification`/`organic_matter`/`fertility`），无法判断返回 `None`（由 `chroma_store` 走全库回退）。

- [x] **Step 1: 编写失败测试** `tests/test_category_router.py`

```python
"""测试耕地领域关键词路由。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.rag.category_router import route_category


def test_route_acidification():
    assert route_category("我的田酸化严重吗") == "acidification"


def test_route_organic_matter():
    assert route_category("如何提升有机质") == "organic_matter"


def test_route_grade():
    assert route_category("这块地质量等级是多少") == "grade"


def test_route_problem():
    assert route_category("耕地有什么障碍因素") == "problem"


def test_route_stability():
    assert route_category("等级稳定性如何") == "stability"


def test_route_unknown_returns_none():
    assert route_category("今天天气怎么样") is None
    assert route_category("") is None
    assert route_category(None) is None
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_category_router.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'framework.rag.category_router'`）

- [x] **Step 3: 编写实现** `framework/rag/category_router.py`

```python
"""耕地领域查询分类路由：关键词规则 + 全库回退（无 LLM）。"""
from __future__ import annotations

from typing import Optional

from framework.agents.routing import (
    QUESTION_TYPE_1_KEYWORDS,
    QUESTION_TYPE_2_KEYWORDS,
    QUESTION_TYPE_3_KEYWORDS,
    QUESTION_TYPE_4_KEYWORDS,
    QUESTION_TYPE_5_KEYWORDS,
    QUESTION_TYPE_6_KEYWORDS,
)

# question_type → 领域 collection 的 category slug（与 capabilities.domain 对齐）
_TYPE_TO_CATEGORY = {
    1: "stability",
    2: "grade",
    3: "problem",
    4: "acidification",
    5: "organic_matter",
    6: "fertility",
}

# 判定优先级：更"领域专属"的关键词组先判，避免泛化词抢占
_TYPE_ORDER = (4, 5, 3, 2, 1, 6)

_KEYWORDS_BY_TYPE = {
    1: QUESTION_TYPE_1_KEYWORDS,
    2: QUESTION_TYPE_2_KEYWORDS,
    3: QUESTION_TYPE_3_KEYWORDS,
    4: QUESTION_TYPE_4_KEYWORDS,
    5: QUESTION_TYPE_5_KEYWORDS,
    6: QUESTION_TYPE_6_KEYWORDS,
}


def route_category(query: Optional[str]) -> Optional[str]:
    """判断查询目标 category；无法判断返回 None（由调用方全库回退）。"""
    if not query:
        return None
    for qtype in _TYPE_ORDER:
        keywords = _KEYWORDS_BY_TYPE.get(qtype) or []
        if keywords and any(kw in query for kw in keywords):
            return _TYPE_TO_CATEGORY[qtype]
    return None
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_category_router.py -v`
Expected: PASS（7 个用例全绿）

- [x] **Step 5: 提交**

```bash
git add framework/rag/category_router.py tests/test_category_router.py
git commit -m "feat(kb): add keyword-based category router for retrieval"
```

---

### Task 6: 检索链路与入库接入 category 路由（tasks.md 3.1 接线 + 3.3）

**Files:**
- Modify: `framework/rag/chain.py:7-8`（加 import）、`framework/rag/chain.py:116-124`（`_retrieve_documents`）
- Modify: `framework/api/routes/docs.py:121`（`add_documents` 传 `category`）
- Modify: `tests/test_reranker.py:87-89`（FakeVS.hybrid_search 增 `category`）
- Modify: `tests/test_docs_dedup.py:21-24`（MockVectorStore.add_documents 增 `category=None`）
- Modify: `tests/test_metadata.py`（CaptureVectorStore 捕获 category + 追加断言）
- Test: `tests/test_reranker.py`（追加路由接线测试）、`tests/test_metadata.py`（追加 category 透传断言）

**Interfaces:**
- Consumes: `route_category(query) -> Optional[str]`（Task 5）、`ChromaVectorStore.hybrid_search(..., category=None)`（Task 4）。
- Produces: `_retrieve_documents` 先 `normalize_query` 再 `route_category(normalized_query)`，将 category 传入 `hybrid_search`；入库侧 `docs.py` 将 form `category` 传入 `add_documents(category=...)`。

- [x] **Step 1: chain.py 加 import**

在 `framework/rag/chain.py` 顶部 import 区（`from framework.rag.synonyms import normalize_query` 之后）加入：

```python
from framework.rag.category_router import route_category
```

- [x] **Step 2: chain.py 修改 `_retrieve_documents`**

把 `framework/rag/chain.py` 第 116-124 行：

```python
    def _retrieve_documents(self, query: str, valid_doc_names: Optional[set]) -> Dict[str, Any]:
        normalized_query = normalize_query(query)
        filters = {"source": {"$in": list(valid_doc_names)}} if valid_doc_names else None
        recalled = self.vector_store.hybrid_search(
            query=normalized_query, n_results=Config.RECALL_TOP_K, filters=filters)
        results = recalled["results"]
        if Config.RERANK_ENABLED and len(results) > Config.RETRIEVAL_TOP_K:
            results = rerank_service.rerank(query, results)
        return {"results": results[:Config.RETRIEVAL_TOP_K],
                "count": len(results[:Config.RETRIEVAL_TOP_K])}
```

改为：

```python
    def _retrieve_documents(self, query: str, valid_doc_names: Optional[set]) -> Dict[str, Any]:
        normalized_query = normalize_query(query)
        category = route_category(normalized_query)
        filters = {"source": {"$in": list(valid_doc_names)}} if valid_doc_names else None
        recalled = self.vector_store.hybrid_search(
            query=normalized_query, n_results=Config.RECALL_TOP_K, filters=filters,
            category=category)
        results = recalled["results"]
        if Config.RERANK_ENABLED and len(results) > Config.RETRIEVAL_TOP_K:
            results = rerank_service.rerank(query, results)
        return {"results": results[:Config.RETRIEVAL_TOP_K],
                "count": len(results[:Config.RETRIEVAL_TOP_K])}
```

- [x] **Step 3: docs.py 传 category 入库**

把 `framework/api/routes/docs.py` 第 121 行：

```python
            added_count = vector_store.add_documents(chunks, metadatas)
```

改为：

```python
            added_count = vector_store.add_documents(chunks, metadatas, category=category)
```

- [x] **Step 4: 更新受影响测试的 mock 签名**

（1）`tests/test_reranker.py` 第 87-89 行：

```python
    class FakeVS:
        def hybrid_search(self, query, n_results=None, filters=None, category=None):
            return recalled
```

（2）`tests/test_docs_dedup.py` 第 21-24 行：

```python
    def add_documents(self, texts, metadatas=None, ids=None, category=None):
        if self._should_fail:
            raise RuntimeError("mock vector store failure")
        return len(texts) if texts else 0
```

（3）`tests/test_metadata.py` 中 `CaptureVectorStore.add_documents` 增加 category 捕获：

```python
    def add_documents(self, texts, metadatas=None, ids=None, category=None):
        self.captured = {"texts": texts, "metadatas": metadatas, "ids": ids, "category": category}
        return len(texts) if texts else 0
```

- [x] **Step 5: 追加链级路由接线测试**（追加到 `tests/test_reranker.py` 末尾）

```python
def test_rag_chain_routes_category_and_passes_to_search(monkeypatch):
    from framework.rag.chain import rag_chain
    from framework.rag import chain as chain_mod

    monkeypatch.setattr(Config, "RECALL_TOP_K", 20)
    monkeypatch.setattr(Config, "RETRIEVAL_TOP_K", 5)
    monkeypatch.setattr(Config, "RERANK_ENABLED", False)

    seen = {}
    monkeypatch.setattr(chain_mod, "normalize_query", lambda q: q)
    monkeypatch.setattr(chain_mod, "route_category", lambda q: "acidification")

    class FakeVS:
        def hybrid_search(self, query, n_results=None, filters=None, category=None):
            seen["category"] = category
            return {"results": [], "count": 0}

    monkeypatch.setattr(rag_chain, "vector_store", FakeVS())

    rag_chain._retrieve_documents("土壤酸化严重吗", None)
    assert seen["category"] == "acidification"
```

- [x] **Step 6: 追加入库 category 透传断言**（追加到 `tests/test_metadata.py` 末尾）

```python
def test_upload_passes_category_to_vector_store(client):
    token = _login(client)
    content = "土壤" * 1000
    resp = client.post(
        "/api/v1/docs/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file": (io.BytesIO(content.encode("utf-8")), "meta2.txt"),
            "category": "acidification",
            "treatment_type": "regulation",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert client._capture_vs.captured["category"] == "acidification"
```

- [x] **Step 7: 运行测试确认通过**

Run: `python -m pytest tests/test_reranker.py tests/test_metadata.py tests/test_docs_dedup.py tests/test_category_router.py tests/test_synonyms.py -v`
Expected: PASS（新增 + 既有用例全绿；`test_docs_dedup.py` 的 mock 已接受 `category` 关键字）

- [x] **Step 8: 提交**

```bash
git add framework/rag/chain.py framework/api/routes/docs.py tests/test_reranker.py tests/test_docs_dedup.py tests/test_metadata.py
git commit -m "feat(kb): wire category routing into retrieval and upload"
```

---

### Task 7: 分领域 collection 重建脚本（tasks.md 3.2）

**Files:**
- Create: `scripts/rebuild_collections.py`

**Interfaces:**
- Consumes: `ChromaVectorStore.add_documents(texts, metadatas, ids, category)`（Task 4）、`Config.CHROMA_PERSIST_DIR` / `Config.CHROMA_COLLECTION_NAME`（已存在）。
- Produces: 脚本 `rebuild_collections()`：读取 `kb_document` 表构建 `source → category` 映射，将旧 `enterprise_kb` 中的 chunk 按 category 迁移到分领域 collection；category 为空/other 的 chunk 仍留在默认库，不重复写入。

- [x] **Step 1: 编写脚本** `scripts/rebuild_collections.py`

```python
"""按 category 将 enterprise_kb 旧 chunk 迁移到分领域 collection。

旧 enterprise_kb 保留为 fallback；category 为空/other 的 chunk 仍留在默认库，不重复写入。
使用方法:
    python scripts/rebuild_collections.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
import sqlite3
from chromadb.config import Settings

from framework.config import Config
from framework.vector_store.chroma_store import vector_store


def _build_source_category_map() -> dict:
    """读 kb_document 表，构建 source(doc_name/file_path) → category 映射。"""
    mapping = {}
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           'instance', 'development.db')
    if not os.path.exists(db_path):
        print(f"数据库不存在: {db_path}")
        return mapping
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT doc_name, file_path, category FROM kb_document")
        for doc_name, file_path, category in cursor.fetchall():
            cat = category or "other"
            mapping[doc_name] = cat
            mapping[file_path] = cat
        conn.close()
        print(f"数据库中找到 {len(mapping)} 条 source→category 映射")
    except Exception as e:
        print(f"查询数据库失败: {e}")
    return mapping


def rebuild_collections():
    source_cat = _build_source_category_map()

    persist_dir = os.path.abspath(Config.CHROMA_PERSIST_DIR)
    client = chromadb.PersistentClient(
        path=persist_dir,
        settings=Settings(anonymized_telemetry=False, allow_reset=False),
    )

    old = client.get_collection(name=Config.CHROMA_COLLECTION_NAME)
    data = old.get()
    ids = data.get("ids", [])
    documents = data.get("documents", [])
    metadatas = data.get("metadatas", [])

    migrated = 0
    skipped = 0
    for i, doc_id in enumerate(ids):
        text = documents[i]
        meta = dict(metadatas[i] or {})
        source = meta.get("source", "")
        category = source_cat.get(source, "other")
        if not category or category.strip().lower() == "other":
            skipped += 1
            continue
        meta["category"] = category
        vector_store.add_documents([text], [meta], [doc_id], category=category)
        migrated += 1

    print(f"\n迁移完成: 迁移 {migrated} 个 chunk，跳过 {skipped} 个（留在默认库）")


if __name__ == "__main__":
    print("=" * 50)
    print("分领域 collection 重建脚本")
    print("=" * 50)
    rebuild_collections()
```

- [x] **Step 2: 语法自检**

Run: `python -c "import ast; ast.parse(open('scripts/rebuild_collections.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [x] **Step 3: 提交**

```bash
git add scripts/rebuild_collections.py
git commit -m "feat(kb): add collection rebuild script for category migration"
```

---

## 组四：验证与回归

### Task 8: 全量回归测试（tasks.md 4.1）

**Files:** 无代码改动。

- [ ] **Step 1: 运行完整测试套件**

Run: `python -m pytest -q`
Expected: 全部通过，无回归。重点关注：`tests/test_rag.py`、`tests/test_upload.py`、`tests/test_docs_dedup.py`、`tests/test_config.py`，以及本次新增的 `test_synonyms.py` / `test_metadata.py` / `test_collection_routing.py` / `test_category_router.py`，兼 P0 的 `test_chunker.py` / `test_bm25_store.py` / `test_hybrid_search.py` / `test_reranker.py`。

- [ ] **Step 2: 若出现回归，逐层排查**

   1. `HYBRID_SEARCH_ENABLED=False`（环境变量）重跑，确认是否混合检索引入。
   2. 检查 `test_hybrid_search.py::test_hybrid_search_disabled_falls_back_to_vector`（回退分支调用形态）与 `_rrf_fuse` 是否被破坏。
   3. 检查 `test_docs_dedup.py` 的 mock `add_documents` 是否已接受 `category` 关键字。

   修复后回到 Step 1 重跑，直至全绿。

- [ ] **Step 3: 记录结果**

在 `docs/superpowers/reports/` 下由执行者输出 verify 报告（本 change 归档流程的一部分），记录通过数与收敛过程。

---

### Task 9: 端到端术语命中与领域路由验证（tasks.md 4.2）

**Files:** 无代码改动（手动验证）。

- [ ] **Step 1: 准备含术语与 category 的文档**

准备两份含「可交换氢」「速效钾」等耕地术语的 txt/md 文档，分别以 `category=acidification`、`category=organic_matter` 上传（走 `/api/v1/docs/upload`，新入库才走新元数据 + 分领域 collection；旧 chunk 不受影响）。

- [ ] **Step 2: 上传并查询**

   1. 上传文档 A（category=acidification，含「可交换氢」）。
   2. 上传文档 B（category=organic_matter，含「速效钾」）。
   3. 通过问答接口查询「可交换氢含量如何影响酸度」「速效钾有什么养分意义」。

- [ ] **Step 3: 验证同义词替换与领域路由**

   1. 确认「可交换氢」查询经 `normalize_query` 改写为「交换性氢」后命中文档 A 的 chunk，且 `sources` 正确。
   2. 确认「酸化严重」类查询经 `route_category` 路由到 `kb_acidification`；「有机质」类查询路由到 `kb_organic_matter`；无法判定的查询回退全库仍能返回结果。
   3. 对 P0 前未迁移的旧 chunk，确认走全库回退后检索不受影响（旧 `enterprise_kb` 保留为 fallback）。

- [ ] **Step 4: 记录结论**

在 verify 报告注明「可交换氢 / 速效钾 命中率提升、领域路由命中，符合预期」；若某术语因 jieba 默认词典切分不当而未命中，记录为已知边界（术语词库优化留待后续 change）。