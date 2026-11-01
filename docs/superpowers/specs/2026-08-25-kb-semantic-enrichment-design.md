---
comet_change: kb-semantic-enrichment
role: technical-design
canonical_spec: openspec
---

# kb-semantic-enrichment 技术设计

## 1. 概述

在 P0（kb-hybrid-retrieval）落地混合检索（向量 + BM25 + RRF）+ 精排后，本节补齐语义增强层：查询同义词预处理、chunk 级元数据增强、分领域 collection 路由。三个能力相互独立，可分别接入与回退。

## 2. 数据流

```
用户查询
  → [新增] normalize_query() 同义词替换（整词）
  → [新增] route_category() 关键词路由，得到目标 category（可能为空）
  → hybrid_search(query, category)
       ├─ 命中 category 且 collection 存在 → 定向检索 kb_<category>
       └─ 否则 → 全库回退（并行检索所有 collection 后 RRF 聚合）
  → rerank → top-K
```

入库侧：

```
parse_document → split_text（chunks）
  → 计算 metadatas：source/category/treatment_type/chunk_index
  → add_documents(chunks, metadatas, category)
       └─ 路由写入 kb_<category>（空/other → enterprise_kb）
```

## 3. 组件设计

### 3.1 同义词预处理

**新增 `framework/rag/soil_synonyms.json`**

JSON 结构：`{规范词: [同义词列表]}`。初始 20–50 组种子词，聚焦耕地领域高频近义术语（如 `"交换性氢": ["可交换氢", "交换性酸"]`、`"有效钾": ["速效钾"]`）。

**新增 `framework/rag/synonyms.py`**

- `load_synonyms() -> dict`：读取 JSON 全量加载进内存；文件缺失/解析失败返回 `{}`，不抛异常。
- `normalize_query(text: str) -> str`：对 query 做整词替换（同义词 → 规范词），未命中的词原样保留。替换按词表条目逐条扫描，优先长词先匹配避免子串误伤。

边界条件：
- 词表为空 → 原样返回。
- 仅整词匹配（不做子串或正则贪婪替换），避免通用词误伤。

接入点：`chain.py._retrieve_documents`（以及 `chat`/`chat_stream` 的检索入口）在调用 `hybrid_search` 前调用 `normalize_query`。规范化后的 query 用于向量与 BM25 两路召回，保证术语对齐。

### 3.2 chunk 级元数据

**修改 `framework/api/routes/docs.py`**

上传入库时，`metadatas` 从 `[{"source": file.filename}]` 扩展为逐 chunk：

```python
metadatas = [{
    "source": file.filename,
    "category": category,
    "treatment_type": treatment_type,
    "chunk_index": i,
} for i in range(len(chunks))]
```

字段来源：
- `category`/`treatment_type`：来自上传 form（`Document` 表已有，默认 `other`）。
- `chunk_index`：分块序号（0-based）。

`page`/`section` 本阶段不写入（`parse_document` 当前仅返回纯文本，不产出页码/章节信息），留 P 后续改造解析器后再补。

**`chroma_store.add_documents`** 已透传完整 metadata，无需改签名；但需增加 `category` 参数用于路由（见 3.3）。

### 3.3 分领域 collection

**修改 `framework/vector_store/chroma_store.py`**

从单句柄改为按 category 的多句柄：

```python
self._collections: Dict[str, Any] = {}   # category → Collection
self._bm25: Dict[str, BM25Store] = {}    # category → BM25Store
```

collection 命名：`kb_<slug(category)>`；`category` 为空或 `other` 时归入默认 `enterprise_kb`（保持与现状兼容）。

关键方法改造：
- `add_documents(texts, metadatas, category=None)`：按 `category` 路由到目标 collection 并同步写入对应 BM25。
- `search(query, n_results, filters, category=None)` / `hybrid_search(...)`：`category` 命中且 collection 存在时定向检索；否则全库回退——遍历所有 collection 分别召回后 RRF 聚合。
- `_get_collection(category)`：懒创建 named collection。
- `clear`/`delete_by_source`/`get_collection_stats`：按需扩展为多 collection 语义（删除按 category 定位）。

**新增 `framework/rag/category_router.py`**

- `route_category(query: str) -> Optional[str]`：用耕地领域关键词规则（复用 `routing.py` 中题型关键词映射到 category 语义）判断查询目标 category；无法判断返回 `None`。
- 命中且 collection 存在 → 定向；否则全库回退（由 `chroma_store` 处理）。

**新增 `scripts/rebuild_collections.py`**

迁移脚本：读 `kb_document` 表反查 `file_path → category`，将旧 `enterprise_kb` 中的 chunk 按 category 迁移到分领域 collection。旧单库保留为 fallback，迁移期间检索回退全库不受影响。

## 4. 路由策略（已确认）

- 关键词/规则判断 + 全库回退（无 LLM 延迟、可回退、可控）。
- 不采用 LLM 判断（增加延迟与成本），不采用仅物理隔离（无定向收益）。

## 5. 技术风险与缓解

| 风险 | 缓解 |
|------|------|
| 多 collection 数据重建破坏现有检索 | 提供迁移脚本；旧 `enterprise_kb` 保留为 fallback；检索自动回退全库 |
| 同义词替换误伤通用词 | 仅整词匹配、仅领域专属词、词表精标 + 单元测试 |
| BM25 多实例内存增长 | 每个 collection 独立小 BM25，耕地词表规模小，可接受 |
| category 值未收录导致频繁回退全库 | `slug` 规范命名 + 默认 `other` 兜底 + 回退路径保证正确性 |

## 6. 测试策略

单元测试：
- `test_synonyms.py`：命中替换、未命中原样、整词匹配不误伤、词表缺失不抛错。
- `test_metadata.py`（或并入现有 upload 测试）：chunk 携带 `category`/`treatment_type`/`chunk_index`。
- `test_category_router.py`：命中定向、未命中回退（返回 None）、缺 collection 回退全库。

回归测试：
- 运行完整测试套件，确保 P0（混合检索 + 精排）+ P1 无回归。

## 7. Spec Patch

回写 `openspec/changes/kb-semantic-enrichment/specs/vector-store/spec.md` 的 "Store chunk-level metadata" 场景：

- P1 SHALL 保证每个 chunk 携带 `category`、`treatment_type`、`chunk_index`。
- `page`、`section` 标注为后续阶段可选字段（当前解析器不产出，P1 不写入）。

原因：用户决策「先写已有字段」与该场景当前「SHALL 携带 category、treatment_type、page、section、chunk_index」冲突，需修正 delta spec 使其与实现一致。