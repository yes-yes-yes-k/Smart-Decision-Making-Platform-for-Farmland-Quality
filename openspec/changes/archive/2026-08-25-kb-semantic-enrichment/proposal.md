# kb-semantic-enrichment Proposal

## Why

知识库当前存在三个语义层面的短板：所有文档集中在一个 `enterprise_kb` collection，chunk 元数据仅记录 `source=filename`，查询直接对原始文本向量化。这导致：检索无法按领域或治理类型隔离、无法按时间/分类过滤，且耕地领域近义术语（如「交换性氢 ↔ 可交换氢」）的向量召回不稳定。

本次在 P0 检索主链路基础上，补齐语义增强层。

## What Changes

- **查询同义词预处理**：新增耕地领域同义词/专业词表，查询进入检索前先做同义词替换。
- **chunk 级元数据增强**：入库时写入 `category`、`treatment_type`、`page`、`section`、`chunk_index` 等 chunk 级元数据。
- **分领域 collection**：按文档 `category` 拆分独立 collection，检索时路由到对应领域库。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `rag-chain`: 新增查询同义词预处理行为，查询在进入检索前先经过同义词/专业词表替换。
- `vector-store`: 元数据支持扩展到 chunk 级字段；collection 管理支持按文档分类拆分领域库并路由。

## Impact

- 代码：`framework/rag/chain.py`（查询预处理）、`framework/vector_store/chroma_store.py`（多 collection + 元数据）、`framework/embedding/service.py`（配合查询预处理）、`framework/api/routes/docs.py`（入库写入元数据）。
- 数据：新增同义词词表（如 `soil_synonyms.json`）。
- 无破坏性变更：旧 chunk 可保留，新入库文档携带新元数据；分领域 collection 需要一次数据迁移/重建。