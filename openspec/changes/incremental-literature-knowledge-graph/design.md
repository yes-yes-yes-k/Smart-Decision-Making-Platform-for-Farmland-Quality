## Context

参见 `proposal.md` 的动机。当前生产图谱 `minimal-cultivated-land-kg-v0.4` 只有 38 个正式实体、66 条正式关系和 94 条带页码证据。它是经过材料级核验的最小图谱，不是可持续增量的知识平台。

当前关系采用有向类型边 `source --relation_type--> target`。实体为 `indicator`、`obstacle`、`measure`、`standard` 4 类；允许关系如下：

| 关系类型 | 方向 | 当前含义 |
|---|---|---|
| `addresses` | measure → obstacle | 措施治理或缓解障碍 |
| `improves_indicator` | measure → indicator | 措施直接改善指标 |
| `characterized_by` | obstacle → indicator | 障碍由指标表征 |
| `includes_indicator` | standard → indicator | 标准将指标纳入评价体系 |
| `prescribes_measurement` | standard → indicator | 标准规定指标测定/获取方法 |
| `assessment_basis` | standard → obstacle | 标准为障碍判定提供依据 |
| `classifies_basic_indicator` | standard → indicator | 标准把指标列为基础性指标 |
| `classifies_regional_supplementary_indicator` | standard → indicator | 标准把指标列为区域补充性指标 |
| `assigns_by_field_survey` | standard → indicator | 标准规定按实地踏勘赋值 |
| `assigns_by_laboratory_test` | standard → indicator | 标准规定按实验室检测赋值 |

每条正式关系使用 `(type, source, target)` 唯一确定，并保存审核信息和证据引用。初始构建器的“同句共现 + 触发词”产生过并列误判、方向错误和概念过宽，说明构图产品只能生成候选，不能代替领域 Schema 和审核。

现有文献 worker 完成 PostgreSQL 和 Chroma 写入后仅把文档置为 `completed`。生产检索器一次性加载整个 JSON 图谱；该方式适合当前规模，但不适合十万实体、百万证据、并发增量更新和低成本回滚。

### Capacity Envelope

本 change 使用以下统一容量基线进行设计和验收：

- 来源文档：100,000；
- 规范实体：100,000；
- 有效关系证据：1,000,000；
- 单次增量：1 至 10,000 份文档；
- 查询：常用 1 至 2 跳关系和 top-100 证据；
- worker：至少支持多个实例通过租约并行消费且无重复生效。

这些数字是架构容量目标，不代表首期上线即拥有对应业务数据。压测数据必须标记为 synthetic，不得进入生产语料。

## Goals / Non-Goals

**Goals:**

- 以 10 万文档/实体、百万证据为容量目标，消除运行时全图 JSON 内存加载和单文档触发全量重建。
- 复用成熟开源构图与存储能力，同时由项目掌控 Schema、候选契约、证据、审核和发布语义。
- 上传或批量导入的获批论文可自动进入候选流水线，失败不影响向量检索。
- 后端可替换：抽取器和图存储变化不得改变审核 API、正式实体 ID 或证据契约。
- 通过影子运行、双写/双读对比和可回滚切换逐步迁移，不一次性重写知识库。

**Non-Goals:**

- 不预先穷举完整农业本体；首期生产 schema 继承 v0.4。
- 不在上传请求线程执行论文构图。
- 不让开源产品自带 schema 或置信度阈值替代领域审核。
- 不在本 change 中替换 Chroma；只稳定图谱与 chunk 之间的公共引用契约。
- 不在首期启用未经离线验证的自动事实发布。

## Decisions

### 1. 平台契约归项目，开源能力通过适配器复用

定义三个稳定端口：

- `GraphExtractionBackend`：输入版本化 schema 与 page-aware chunks，输出统一实体、关系和证据候选；
- `GraphStore`：按活动 release 查询实体、关系、邻居和证据引用；
- `GraphJobExecutor`：按租约领取、续租、重试和完成幂等任务。

适配器不得把产品私有 ID 暴露为正式实体 ID，不得跳过候选表直接写生产关系。每次任务保存 backend 名称、版本、配置摘要和 schema 版本，使结果可复现、可横向比较。

替代方案是把业务直接建立在某一产品 SDK/数据模型之上，短期更快，但会把审核、证据和迁移成本锁死在供应商实现，故不采用。

### 2. 首选 Microsoft GraphRAG 抽取，OpenSPG 保留为可替换后端

首个适配器使用 Microsoft GraphRAG 的实体/关系/claim 抽取与增量能力，因为当前服务是 Python，接入成本低。只消费其结构化抽取结果，不直接采用其自由关系作为生产 schema，也不要求使用其默认 Parquet 输出作为平台事实源。

OpenSPG Builder 作为第二适配器和离线对照候选，适合后续需要更完整的领域建模、标准化与推理时评估。是否启用由同一金标集上的关系类型精确率、实体消歧准确率、证据定位率、吞吐、成本和运维复杂度决定。

Neo4j GraphRAG 可用于实验，但不作为首选：它会引入独立数据库运维，Community Edition 的可用性/安全能力与目标平台要求不完全一致。所有选型都通过 adapter conformance suite，而不是写死在业务代码中。

### 3. PostgreSQL + Apache AGE 作为目标图存储

项目已经以 PostgreSQL 为核心数据库。Apache AGE 提供属性图和 openCypher，并可复用 PostgreSQL 的事务、连接、备份、监控和既有运维能力，因此作为目标 `GraphStore`。工作流、证据和审核继续使用普通关系表；规范实体与关系及其可查询属性写入 AGE。

当前 JSON v0.4 由 `JsonGraphStore` 继续提供兼容读取，并作为 AGE 导入源和小规模审计导出。迁移期间对 JSON 与 AGE 执行代表性查询双读比较；一致性门槛通过后才切换 AGE 为主读。

### 4. 最小本体先行、版本化扩展

自动更新只要求先固定实体类型、关系类型与方向、稳定 ID、证据格式、审核状态和发布门槛。首期 schema 继承 v0.4；无法表达的新概念进入 `ontology_extension` 候选，经独立 schema 变更批准后才进入生产。

这避免“完整设计全部本体”的长周期，也防止开放标签造成同义关系泛滥。

### 5. 文献完成事件通过事务 outbox 驱动异步任务

文档只有在管理员审核通过、chunk 原子发布且 `processing_stage=completed` 后，才写入 `knowledge_document_indexed` outbox。消费者创建唯一任务：

`(document_id, content_sha256, graph_schema_version, extractor_backend, extractor_version)`。

任务通过数据库租约领取；worker 崩溃后租约到期可重领。幂等键保证至少一次投递下只有一次业务生效。上传、文献状态和向量可检索性不等待图谱任务。

### 6. 候选流水线统一抽取、规范化、消歧、验证和审核

1. 读取已持久化 page-aware chunks，不重新解析上传文件；
2. 调用配置的抽取后端并保存原始结果摘要；
3. 转换为统一候选契约，未知类型进入本体扩展候选；
4. 用稳定 ID、规范名、别名、标准编号和业务键消歧，模糊结果不得自动合并；
5. 以 `(type, canonical_source_id, canonical_target_id)` 合并关系，以证据 ID 去重；
6. 校验端点、方向、span、页码、chunk、原文哈希和来源状态；
7. 生成人工审核包，保留抽取后端、版本、置信度和校验结果。

### 7. 首期自动处理、人工发布

- **证据追加**：既有关系新增有效证据，可批量审核；
- **事实新增**：既有实体之间的新允许关系，必须审核；
- **新实体实例**：属于既有类型但需完成实体消歧审核；
- **本体扩展**：新实体类型、关系类型或方向变化，必须走 schema 变更。

只有离线金标评测和一段生产 shadow 期证明特定低风险类别达到批准门槛后，才可通过后续 OpenSpec 引入自动发布。

### 8. 关系库保存治理状态，AGE 保存活动知识视图

普通关系表新增：

- `kg_extraction_job`、`kg_entity_candidate`、`kg_relation_candidate`；
- `kg_candidate_evidence`、`kg_review_decision`；
- `kg_release`、`kg_release_change`、`kg_outbox_event`。

高基数字段建立组合/部分索引；任务和证据表按时间或哈希分区策略在规模测试后确定，迁移必须预留在线新增分区能力。AGE 节点/边保存正式 ID、schema 版本和有效发布区间，不复制审核全文。

### 9. 发布使用追加式有效区间，不复制整张图

批准的变更以 append-only 方式写入，并用 `valid_from_release` / `valid_to_release` 表示版本有效区间。发布事务先写变更和校验结果，最后原子更新 `active_release`。回滚只切换到已验证 release；快照 JSON/Parquet 在发布后异步导出用于审计、备份和离线分析，不参与在线切换。

该模型避免每次发布复制十万实体或重写百万证据，同时保持可追溯版本语义。

### 10. 证据生命周期独立于关系生命周期

删除、撤回、重新解析或权威状态变化时，按 `document_id + content_sha256` 失效旧证据并重算支持数。仍有其他有效证据的关系保留；零证据关系创建待审核移除变更，不立即影响活动 release。

### 11. 查询路径保持证据权限安全

RAG 通过 `GraphStore` 执行有界 1 至 2 跳查询，返回稳定实体/关系 ID 和证据引用；证据正文必须再经现有向量存储的权限过滤接口解析。禁止从 AGE 属性直接返回未授权论文原文。

查询必须有 top-k、最大跳数、超时和结果大小限制，避免高连接度节点造成无界遍历。

### 12. 规模验收使用可重复基准而非主观判断

仓库新增 synthetic 数据生成器和 benchmark manifest。标准基准至少覆盖 100,000 文档元数据、100,000 实体、1,000,000 关系证据及 100,000 待处理任务；记录硬件、PostgreSQL/AGE 版本、索引、并发和数据分布。

在参考环境中：

- 单文档更新不得扫描或重写全图；
- 1 至 2 跳 top-100 图查询（不含 LLM 与向量正文读取）P95 SHALL 不超过 1 秒；
- 发布激活和已验证版本回滚 SHALL 在 60 秒内完成且不中断向量检索；
- 100,000 任务在重复投递和 worker 重启下 SHALL 保持计数守恒、无重复业务生效；
- 备份恢复后 SHALL 通过实体、关系、证据和活动版本校验。

如果参考环境无法达标，必须先优化索引、分区、查询或 worker 并发，再扩大业务回填；不得通过降低数据规模宣称通过。

## Risks / Trade-offs

- [GraphRAG/OpenSPG 输出语义不稳定] → 统一候选契约、封闭 schema、金标评测、shadow 模式和人工审核。
- [引入 AGE 增加数据库扩展运维] → 固定兼容版本、健康检查、备份恢复演练、JSON 回退适配器和双读切换。
- [开源组件升级破坏结果] → 锁定版本、SBOM/许可证清单、adapter conformance suite 和升级前结果差异报告。
- [候选数量导致审核积压] → 三元组/证据去重、风险分队列、批量证据审核和积压 SLO。
- [高连接度节点拖慢图查询] → 有界跳数、top-k、查询超时、方向/类型过滤和慢查询监控。
- [关系证据与 Chroma chunk 漂移] → 保存 document/content/chunk/quote 多级标识，重解析时失效旧证据。
- [双写期间存储不一致] → outbox、幂等 upsert、定期校验和对账，AGE 未通过门槛前不作为主读。
- [100,000 文档回填成本高] → dry-run 估算、限流、断点续跑、按领域分批和相同版本结果缓存。

## Migration Plan

1. 从 v0.4 提取 `minimal-cultivated-land-kg-schema-v1` 和 backend-neutral 候选/证据契约。
2. 建立 GraphRAG adapter、stub adapter 和 conformance suite；用 94 条已审核证据完成 shadow 评测。
3. 上线任务/候选/审核/outbox 表和租约 worker，不启用生产发布。
4. 在非生产 PostgreSQL 安装并验证 Apache AGE；实现 `JsonGraphStore` 与 `AgeGraphStore`。
5. 导入 v0.4 到 AGE，执行结构校验、证据解析和代表性查询双读对比。
6. 用 10 篇论文完成上传触发、候选、审核、AGE 变更、发布和回滚试点。
7. 运行 10k 中间规模与完整容量基准；只有通过后才将 AGE 切为主读，JSON 保留为回退。
8. 启用新上传实时触发，再分批回填现有文献；根据积压和质量逐步扩大批次。
9. 异常时暂停消费者、切回 `JsonGraphStore` 或上一健康 release；文献与向量索引不回滚，候选审计保留。

## Open Questions

- 参考生产硬件规格将在部署环境确定后写入 benchmark profile；容量规模、查询边界和通过阈值不因此改变。
- OpenSPG adapter 是否进入正式运行取决于 GraphRAG shadow 评测结果；无论选择哪一实现，统一契约和验收标准保持不变。
