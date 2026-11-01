## Purpose

为审核通过并完成索引的文献提供证据可追溯、可人工治理、可版本发布和可回滚的增量知识图谱更新能力，同时保证候选抽取失败不影响文献与向量检索的可用性。

## ADDED Requirements

### Requirement: Versioned Minimal Graph Schema

系统 SHALL 使用版本化 schema 定义正式实体类型、关系类型、允许的源/目标方向、稳定标识规则、证据契约和运行时兼容范围。首个增量 schema SHALL 兼容现有 v0.4 的 `indicator`、`obstacle`、`measure`、`standard` 实体及其 10 类正式关系。

#### Scenario: Extractor proposes an allowed relation
- **WHEN** 抽取器提出 `measure -> addresses -> obstacle` 且两个端点可解析为既有正式实体
- **THEN** 系统 SHALL 按当前 schema 接受其进入事实候选校验

#### Scenario: Extractor invents an unknown relation type
- **WHEN** 抽取器输出当前 schema 未定义的关系类型或非法端点方向
- **THEN** 系统 SHALL NOT 创建可发布事实关系，并 SHALL 将其记录为本体扩展候选或结构化拒绝结果

### Requirement: Extraction Backend Conformance

系统 SHALL 通过统一候选契约调用开源或自定义抽取后端。后端输出 SHALL 在进入实体消歧前保留后端名称、版本、配置摘要和原始结果指纹；每个生产后端 SHALL 通过相同的 schema、证据和幂等一致性测试。

#### Scenario: GraphRAG adapter extracts candidates
- **WHEN** GraphRAG adapter 从带页码 chunk 中返回实体和关系
- **THEN** 系统 SHALL 将结果转换为统一候选契约并执行项目定义的 schema、证据和审核规则

#### Scenario: Adapter fails conformance tests
- **WHEN** 某抽取 adapter 不能稳定保留证据位置、幂等身份或受控关系类型
- **THEN** 系统 SHALL NOT 允许该 adapter 用于生产任务

### Requirement: Idempotent Post-index Extraction

系统 SHALL 仅对已审核、公开、处理完成且 chunk 已原子发布的文献异步创建图谱抽取任务。任务 SHALL 以文档、内容哈希、graph schema 版本和抽取器版本组成幂等身份，且图谱失败 SHALL NOT 改变文献已完成状态。

#### Scenario: Approved paper finishes indexing
- **WHEN** 一篇获批论文的全部 chunk 已成功发布且文档进入 `completed`
- **THEN** 系统 SHALL 异步创建一次对应版本的图谱抽取任务

#### Scenario: Completion event is delivered twice
- **WHEN** 同一文档、内容哈希、schema 和抽取器版本的完成事件被重复消费
- **THEN** 系统 SHALL 复用原任务或返回其结果，不得生成重复候选和证据

#### Scenario: Graph extraction fails
- **WHEN** 图谱抽取因模型超时或候选校验失败而结束
- **THEN** 文献 SHALL 保持公开可检索的 `completed` 状态，图谱任务 SHALL 独立记录失败码与可重试性

### Requirement: Evidence-grounded Candidate Extraction

每个关系候选 SHALL 引用持久化文档、页码、chunk、原文 span、原文哈希、schema 版本和抽取器版本。系统 SHALL 验证 span 可在引用 chunk 中定位且哈希一致；不能满足证据契约的候选 SHALL NOT 进入审核队列。

#### Scenario: Candidate evidence resolves exactly
- **WHEN** 候选的原文 span、页码和 chunk 可在当前文档内容中精确解析且哈希一致
- **THEN** 系统 SHALL 保存证据并允许候选继续消歧和审核

#### Scenario: Candidate quote is fabricated or stale
- **WHEN** 候选原文不能在引用 chunk 中定位或内容哈希已经变化
- **THEN** 系统 SHALL 拒绝该证据并 SHALL NOT 将关系标记为可审核或可发布

### Requirement: Canonical Entity Resolution

系统 SHALL 在创建事实候选前使用稳定 ID、规范名称、别名、标准编号和受控业务键解析关系端点。模糊匹配结果 SHALL 进入待确认状态，不得自动合并；属于既有类型的新实体实例 SHALL 经实体审核后才能成为正式关系端点。

#### Scenario: Alias resolves to one canonical entity
- **WHEN** 论文术语通过受控别名唯一匹配一个正式实体
- **THEN** 系统 SHALL 将关系候选端点绑定到该实体的稳定 ID，并保留原始提及文本

#### Scenario: Mention has multiple plausible entities
- **WHEN** 一个术语可能映射到多个实体且无法用编号或上下文唯一消歧
- **THEN** 系统 SHALL 将候选标记为 `needs_entity_resolution`，不得自动发布

### Requirement: Candidate Deduplication and Risk Classification

系统 SHALL 以关系类型和规范源/目标实体合并事实候选，以稳定证据 ID 去重，并区分“既有关系证据追加”“允许类型的新事实”“新实体实例”和“本体扩展”风险级别。

#### Scenario: New paper supports an existing relation
- **WHEN** 新论文为生产图中相同 `(type, source, target)` 提供不同的有效证据
- **THEN** 系统 SHALL 创建证据追加候选而不是重复关系，并 SHALL 更新候选支持文档统计

#### Scenario: Same evidence is extracted repeatedly
- **WHEN** 相同文档位置和原文哈希的证据被多次抽取
- **THEN** 系统 SHALL 只保留一个有效证据记录

### Requirement: Human Review Gate

首期所有新增实体、事实关系和证据追加 SHALL 在进入生产发布前具有明确的批准记录。审核记录 SHALL 保存审核人、时间、决定、理由、审核时 schema/抽取器版本和被审核值；抽取置信度不得替代审核决定。

#### Scenario: High-confidence candidate has no review
- **WHEN** 候选置信度高于配置阈值但尚无批准记录
- **THEN** 系统 SHALL NOT 将其包含在生产发布制品中

#### Scenario: Reviewer rejects a candidate
- **WHEN** 授权审核人以理由拒绝实体、关系或证据候选
- **THEN** 系统 SHALL 保留拒绝审计且 SHALL NOT 在后续相同版本发布中包含该候选

#### Scenario: Non-admin attempts review
- **WHEN** 未授权用户尝试批准、拒绝或发布图谱候选
- **THEN** 系统 SHALL 拒绝请求且不得改变候选或发布状态

### Requirement: Atomic Versioned Publication

系统 SHALL 从当前生产版本、已批准增量和已批准证据撤销生成追加式版本变更。发布前 SHALL 验证 schema 兼容、端点和方向、有效证据、重复关系/证据、孤立正式实体、审核覆盖、代表性查询以及变更校验和；只有全部通过时才 SHALL 原子切换活动 release。审计快照 SHALL 在发布后异步生成，不得阻塞活动版本切换。

#### Scenario: Release passes all gates
- **WHEN** 增量版本通过全部结构、证据、审核、查询和校验和检查
- **THEN** 系统 SHALL 创建带父版本和差异摘要的发布记录，并原子切换 `active_release`

#### Scenario: Release contains an evidence-free relation
- **WHEN** 待发布版本包含没有有效证据的正式关系
- **THEN** 系统 SHALL 拒绝发布并保持当前生产版本不变

#### Scenario: Runtime cannot load the new release
- **WHEN** 新版本在图存储健康检查或主读切换时失败
- **THEN** 系统 SHALL 继续使用上一个健康 release 或兼容 `GraphStore`；若不存在健康图谱后端，则 SHALL 关闭图谱增强并保留向量检索

### Requirement: Audited Release Rollback

授权管理员 SHALL 能将生产活动版本回滚到任一仍被保留且校验通过的兼容发布。回滚 SHALL 记录操作者、原因、来源版本和目标版本，不得删除失败版本的审计信息。

#### Scenario: Administrator rolls back a faulty release
- **WHEN** 管理员选择一个兼容且校验通过的历史版本并提交回滚原因
- **THEN** 系统 SHALL 原子切换活动版本并记录完整回滚审计

### Requirement: Evidence Lifecycle and Document Withdrawal

文档删除、撤回、重新解析或内容哈希变化时，系统 SHALL 使旧版本文档提供的证据失效。关系仍有其他有效证据时 SHALL 保留；失去全部有效证据时 SHALL 进入待审核移除状态，而不是在生产图中立即消失。

#### Scenario: One of several supporting papers is withdrawn
- **WHEN** 某关系有三篇有效支持文献且其中一篇被撤回
- **THEN** 系统 SHALL 失效该文档证据并保留由另外两篇文献支持的关系

#### Scenario: Last evidence becomes unavailable
- **WHEN** 一条正式关系的最后一条有效证据被撤回或无法解析
- **THEN** 系统 SHALL 创建待审核移除候选，并在批准和下一次发布前保持当前生产版本不变

### Requirement: Candidate and Release Administration API

系统 SHALL 为授权管理员提供图谱任务查询/重试、候选筛选与详情、实体消歧、候选审核、发布预览、发布和回滚接口。系统 MUST NOT 提供绕过候选与证据直接创建生产关系的接口。

#### Scenario: Reviewer inspects a relation candidate
- **WHEN** 授权审核人查询候选详情
- **THEN** 系统 SHALL 返回规范端点、关系语义、风险级别、所有有效证据、抽取与校验版本及历史审核记录

#### Scenario: Client tries to create a production edge directly
- **WHEN** 客户端提交未引用候选和证据的生产关系写入请求
- **THEN** 系统 SHALL 拒绝请求

### Requirement: Historical Corpus Backfill

系统 SHALL 支持以 dry-run、限批、断点续跑和幂等方式为现有已审核、公开、处理完成的文献创建图谱任务。历史回填 SHALL 与实时上传使用相同 schema、抽取、校验和审核流程。

#### Scenario: Backfill dry-run
- **WHEN** 管理员对历史公开语料执行图谱回填 dry-run
- **THEN** 系统 SHALL 报告符合条件、已处理、预计新任务和跳过原因，且不得创建任务或候选

#### Scenario: Interrupted backfill resumes
- **WHEN** 回填在部分文档完成后中断并使用相同版本参数恢复
- **THEN** 系统 SHALL 跳过已经有同幂等身份结果的文档并从未完成位置继续

### Requirement: Knowledge Graph Observability

系统 SHALL 暴露任务吞吐、失败率、待审积压、候选风险分布、审核时延、发布差异、无证据关系、孤立实体、当前活动版本和最近回滚状态，且 SHALL 对路径、原文和用户信息进行脱敏或权限控制。

#### Scenario: Operator checks graph health
- **WHEN** 授权运维人员查询图谱健康状态
- **THEN** 系统 SHALL 返回活动发布、schema、制品校验状态、任务积压和最近失败摘要，不得泄露未授权论文正文
