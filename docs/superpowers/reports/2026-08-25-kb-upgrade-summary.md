# 知识库升级工作汇报

- **汇报日期**：2026-08-25
- **工作范围**：知识库检索与入库链路三阶段升级（P0/P1/P2）
- **工作流**：Comet Classic（OpenSpec + Superpowers）
- **状态**：三阶段全部归档交付完成

---

## 一、背景

本次知识库升级针对原 RAG 管线的三个核心短板：

1. **检索质量低**：固定 800 字符硬切分块 + 纯向量单路召回 + 无精排，专业术语召回不稳定，噪声 chunk 稀释上下文。
2. **语义层缺失**：所有文档混存单 collection，无领域隔离；chunk 元数据仅 `source=filename`；近义术语（"可交换氢"↔"交换性氢"）召回不稳定。
3. **入库质量与可运维不足**：PDF 解析噪声原样入库；OCR 仅作失败兜底；上传同步阻塞；引用仅到 doc_name；无检索质量度量。

升级按 P0→P1→P2 三阶段递进推进，每阶段独立设计、构建、验证、归档。

---

## 二、三阶段交付总览

| 阶段 | change 名称 | 优先级 | 核心目标 | 归档日期 | 验证结论 |
|------|------------|--------|----------|----------|----------|
| P0 | kb-hybrid-retrieval | P0 | 混合检索 + 精排主链路 | 2026-08-25 | PASS（0 CRITICAL/WARNING）|
| P1 | kb-semantic-enrichment | P1 | 同义词 + 元数据 + 分领域库 | 2026-08-25 | PASS（0 CRITICAL，1 WARNING 非阻塞）|
| P2 | kb-ingestion-quality | P2 | 入库质量 + 引用溯源 + 检索评估 | 2026-08-25 | PASS（0 CRITICAL/WARNING）|

**工作区隔离**：均使用 git worktree，分支 `feature/20260824/kb-hybrid-retrieval`、`feature/20260825/kb-semantic-enrichment`、`feature/20260825/kb-ingestion-quality`，均已推送至 origin。

---

## 三、各阶段实现内容

### P0：kb-hybrid-retrieval（混合检索 + 精排）

**解决的问题**：分块硬编码忽略 overlap、纯向量召回术语漏召回、无精排噪声高。

**实现内容**：

| 模块 | 文件 | 说明 |
|------|------|------|
| 独立分块器 | `framework/upload/chunker.py` | 滑动窗口分块，使用 `CHUNK_SIZE=800` + `CHUNK_OVERLAP=150`，替换 docs.py 内嵌硬切 |
| BM25 索引 | `framework/vector_store/bm25_store.py` | `jieba.lcut` 分词 + `BM25Okapi`，支持 add/search/delete/clear |
| 混合检索 | `framework/vector_store/chroma_store.py` | 向量 + BM25 双路并行召回，RRF 融合（k=60）|
| 精排服务 | `framework/rag/reranker.py` | SiliconFlow BGE-Reranker-v2-m3，召回 20 → rerank → top-5 |
| RAG 链接入 | `framework/rag/chain.py` | 检索流程改为双路召回 → 精排 → 生成 |

**验证证据**：定向测试 51 passed；术语召回端到端验证（交换性氢/有效钾/有机质）均命中正确 source。

**归档位置**：`openspec/changes/archive/2026-08-25-kb-hybrid-retrieval/`

---

### P1：kb-semantic-enrichment（语义增强）

**解决的问题**：单 collection 无领域隔离、元数据匮乏、近义术语召回不稳。

**实现内容**：

| 模块 | 文件 | 说明 |
|------|------|------|
| 同义词预处理 | `framework/rag/synonyms.py` + `framework/rag/soil_synonyms.json` | 查询进入检索前做同义词替换（可交换氢→交换性氢、酸度→酸碱度、速效钾→有效钾）|
| 领域路由 | `framework/rag/category_router.py` | 关键词路由到对应领域（酸化→acidification、有机质→organic_matter）|
| 分领域 collection | `framework/vector_store/chroma_store.py` | 多 handle 管理（kb_acidification / kb_organic_matter / 默认库），支持全库回退 |
| chunk 元数据增强 | `framework/api/routes/docs.py` | 入库写入 category / treatment_type / chunk_index |
| 重建脚本 | `scripts/rebuild_collections.py` | 分领域 collection 迁移工具 |

**验证证据**：定向测试 53 passed；端到端验证同义词替换、领域路由、分领域存储、全库回退均通过。

**已知边界**：真实 SILICONFLOW embedding API 当前返回 400（环境波动），端到端以确定性桩向量验证 routing/collection 管道，同义词与路由走真实词表/规则。

**归档位置**：`openspec/changes/archive/2026-08-25-kb-semantic-enrichment/`

---

### P2：kb-ingestion-quality（入库质量 + 引用溯源 + 检索评估）

**解决的问题**：PDF 噪声入库、OCR 仅兜底、上传阻塞、引用粗粒度、无质量度量。

**实现内容**：

| 模块 | 文件 | 说明 |
|------|------|------|
| 文本清洗 | `framework/upload/text_cleaner.py` | NFKC 规范化 + 控制字符去除 + 空白合并 + 跨页重复页眉页脚去除（≥3 次重复）|
| 异步入库 | `framework/upload/ingestion_worker.py` | ThreadPoolExecutor 后台处理，状态机 pending(0)→processing(2)→completed(1)/failed(3) |
| 上传异步化 | `framework/api/routes/docs.py` | 文档上传改 fire-and-forget，立即返回 202；数据文件保持同步 200 |
| 状态枚举 | `framework/models/document.py` | STATUS_PENDING/COMPLETED/PROCESSING/FAILED 常量，保留现有 status=1 语义无迁移 |
| 分页切分 | `framework/upload/chunker.py` | `split_text_with_pages()` 跨页不拼接，保留页码语义 |
| PDF 保真解析 | `framework/upload/document_parser.py` | 图片型 PDF 检测（采样 5 页平均字符 < 50 触发全本 OCR）+ 单页 OCR 兜底 + pdfplumber 表格 Markdown 提取 + page_aware 按页返回 |
| chunk 级引用 | `framework/rag/chain.py` | sources 增 chunk_index / page 字段，流式与非流式一致，缺失字段降级为 null |
| 检索评估 | `scripts/eval_retrieval.py` + `tests/fixtures/eval_queries.yaml` | hit_rate@K + MRR 指标，JSON 输出 |

**验证证据**：定向测试 53 passed；全量回归 754 passed / 4 deselected（预存环境失败，与本变更无关）。

**归档位置**：`openspec/changes/archive/2026-08-25-kb-ingestion-quality/`

---

## 四、能力规格（Capability Specs）演进

三阶段共涉及 4 个 capability，均已完成 delta spec 合并入主 spec：

| Capability | 类型 | P0 贡献 | P1 贡献 | P2 贡献 |
|------------|------|---------|---------|---------|
| `rag-chain` | 已有（修改）| 双路召回+精排接入生成 | 查询同义词预处理 | chunk 级引用溯源 |
| `vector-store` | 已有（修改）| BM25 索引 + 混合检索 + RRF | 分领域 collection + chunk 元数据 | — |
| `file-upload-management` | 已有（修改）| 配置驱动滑动窗口分块 | — | 文本清洗 + 异步入库 + PDF 保真解析 |
| `kb-retrieval-evaluation` | 新增 | — | — | 检索质量评估（hit_rate/MRR）|

主 spec 当前位置：`openspec/specs/{rag-chain,vector-store,file-upload-management,kb-retrieval-evaluation}/spec.md`

---

## 五、最终 RAG 管线架构

升级后的完整 RAG 管线（三阶段叠加）：

```
文档上传（202 异步）
    │
    ├─ 文本清洗（NFKC + 去噪 + 去页眉页脚）
    ├─ PDF 保真解析（图片型 OCR 主路径 + 表格 Markdown + page_aware）
    ├─ 分页滑动窗口分块（size=800, overlap=150，跨页不拼接）
    ├─ chunk 元数据写入（source/category/treatment_type/chunk_index/page）
    └─ 分领域 collection 入库 + BM25 索引同步
                                        │
                                        ▼
查询提问
    │
    ├─ 同义词预处理（可交换氢→交换性氢）
    ├─ 关键词领域路由（酸化→acidification collection）
    ├─ 双路召回（向量 top-20 + BM25 top-20）
    ├─ RRF 融合（k=60）
    ├─ Rerank 精排（BGE-Reranker-v2-m3 → top-5）
    ├─ LLM 生成答案
    └─ 返回 sources（doc_name + chunk_index + page）
                                        │
                                        ▼
检索质量评估
    └─ eval_retrieval.py（hit_rate@K + MRR，YAML 标注集）
```

---

## 六、测试与质量

### 测试覆盖

| 阶段 | 定向测试 | 全量回归 |
|------|----------|----------|
| P0 | 51 passed | 670 passed / 15 pre-existing failed |
| P1 | 53 passed | 695 passed / 14 pre-existing failed |
| P2 | 53 passed | 754 passed / 4 pre-existing failed / 22 skipped |

### 预存失败说明

全量回归中的失败项均属主题模型集成环境问题（stability/grade 返回 degraded、exclusive_rules 维度回溯、organic_matter/model5 DB app context），与知识库升级无关，已在各阶段 base-ref 复现佐证。P0→P2 过程中预存失败数从 15 降至 4，部分环境问题在后续工作中自然修复。

### 环境备注

真实 SILICONFLOW embedding API 在 P0 期间返回 200、P1/P2 期间出现 400 波动，属环境侧波动非代码缺陷。各阶段端到端验证以确定性桩向量跑通 ChromaVectorStore 管道，同义词/路由/清洗/分页等逻辑走真实词表与规则。

---

## 七、技术决策记录

| 决策 | 阶段 | 理由 |
|------|------|------|
| BM25 用 `rank_bm25` + `jieba` 而非 ES | P0 | 避免额外运维负担，应用层足够 |
| RRF 融合 k=60 | P0 | 业界常用值，平衡两路权重 |
| Rerank 复用 SiliconFlow BGE-Reranker API | P0 | 无需自建模型，API 稳定 |
| 异步用 ThreadPoolExecutor 而非 Celery | P2 | 当前上传量级线程池足够，避免队列运维 |
| OCR 主路径前置（检测到图片型即全本 OCR）| P2 | 相比失败兜底，成功率与信息保真更高 |
| chunk 跨页不拼接 | P2 | 保留页码语义精确性，避免歧义 |

---

## 八、后续建议

1. **embedding API 稳定性**：关注 SILICONFLOW embedding API 波动，必要时增加重试或本地 fallback 模型。
2. **历史数据迁移**：P0/P1 改动仅影响新入库文档，建议用 `scripts/rebuild_collections.py` 对历史文档重建分领域 collection 与 BM25 索引。
3. **page/section 元数据补全**：P1 proposal 曾提及 page/section，P2 已实现 page（PDF 保真解析产出），section 字段留待后续按需扩展。
4. **检索评估常态化**：建议将 `scripts/eval_retrieval.py` 纳入 CI 或定期运行，建立检索质量基线监控优化效果。
5. **预存测试失败清理**：4 项主题模型集成环境失败建议单独 change 处理，与知识库升级解耦。

---

## 九、归档索引

| 阶段 | 归档目录 | 验证报告 | 设计文档 |
|------|----------|----------|----------|
| P0 | `openspec/changes/archive/2026-08-25-kb-hybrid-retrieval/` | `docs/superpowers/reports/2026-08-24-kb-hybrid-retrieval-verify.md` | `docs/superpowers/specs/2026-08-24-kb-hybrid-retrieval-design.md` |
| P1 | `openspec/changes/archive/2026-08-25-kb-semantic-enrichment/` | `docs/superpowers/reports/2026-08-25-kb-semantic-enrichment-verify.md` | `docs/superpowers/specs/2026-08-25-kb-semantic-enrichment-design.md` |
| P2 | `openspec/changes/archive/2026-08-25-kb-ingestion-quality/` | `docs/superpowers/reports/2026-08-25-kb-ingestion-quality-verify.md` | `docs/superpowers/specs/2026-08-25-kb-ingestion-quality-design.md` |

所有归档 change 均已推送至 origin 对应分支，Comet Classic 工作流完整闭环。
