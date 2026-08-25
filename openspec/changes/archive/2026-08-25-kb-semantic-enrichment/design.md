# kb-semantic-enrichment Design

## Context

在 P0（kb-hybrid-retrieval）落地混合检索 + 精排后，检索链路已具备双路召回与重排。本节补齐语义层（详见 proposal.md）。

## Goals / Non-Goals

**Goals:**
- 查询侧同义词/专业词表预处理，规范化专业术语。
- chunk 元数据从单一 `source` 扩展到 category/treatment_type/page/section/chunk_index。
- 按 category 拆分 collection 并路由，降低检索空间。

**Non-Goals:**
- 不改 P0 的分块/混合检索/精排策略。
- 不做 P2 的文本清洗/异步/OCR/溯源/评估。

## Decisions

1. **同义词词表用 JSON 配置文件（`soil_synonyms.json`），查询时全量加载内存做替换。**
   - 理由：耕地术语词表规模小（百级），无需数据库/词典服务；改动与维护成本最低。词表缺失时查询原样通过（不阻塞）。
   - 备选：LLM Query 改写（成本高、延迟大；留待后续按需引入）。

2. **chunk 元数据在入库阶段从 `kb_document` 表与解析结果计算后写入 Chroma metadata。**
   - 理由：解析阶段已能拿到分类/页码/章节，扩展 metadata 不改变向量化流程。

3. **分领域 collection 按 `category` 切名（如 `kb_<category>`），检索时按查询路由到的 category 定向检索，缺失 RRF 时回退全库。**
   - 理由：物理隔离降低召回信噪比；兼容现状（category 已在 `kb_document` 表存在）。

## Risks / Trade-offs

- [分领域 collection 需数据重建] → 提供迁移脚本，逐步重建；旧单库可保留为回退。
- [同义词替换可能误伤通用词] → 词表仅收录领域专属同义映射，仅整词匹配。

## Migration Plan

1. 新增同义词词表文件与加载/替换函数，接入 `chain.py` 检索前。
2. 扩展 `chroma_store` 元数据写入与多 collection 路由。
3. 更新 `docs.py` 入库写入 chunk 元数据。
4. 提供 collection 重建脚本，分 category 迁移。

## Open Questions

（无）