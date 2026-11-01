# database-models Specification (Delta)

## ADDED Requirements

### Requirement: Literature Document Metadata

`kb_document` SHALL 支持文献类型、稳定标识、书目元数据、来源元数据、权威状态、解析质量、处理失败信息和管理员审核审计。旧文档在新增字段为空时 SHALL 继续可读取和检索。

#### Scenario: Academic paper metadata persisted
- **WHEN** 学术论文上传请求通过校验
- **THEN** 文档 SHALL 保存 `document_kind=academic_paper`、title、language、规范化 DOI 和 bibliographic metadata
- **AND** provenance SHALL 保存来源类别、交叉类别和来源 URL

#### Scenario: Standard authority defaults to unverified
- **WHEN** 标准文档未提供已审核权威状态
- **THEN** `authority_status` SHALL 为 `unverified`
- **AND** SHALL NOT 被描述为已确认现行标准

#### Scenario: User submission review is persisted
- **WHEN** 管理员批准或驳回用户文献提交
- **THEN** 文档 SHALL 保存 `review_status`、`reviewed_by`、`reviewed_at` 和可选 `review_note`
- **AND** 批准记录 SHALL 保存最终确认的领域标签
- **AND** 审核通过并完成索引的文档 SHALL 保存 `visibility_scope=public`

#### Scenario: Rejected status is represented explicitly
- **WHEN** 管理员驳回用户文献提交
- **THEN** 文档 SHALL 保存 `status=4` 和 `processing_stage=rejected`
- **AND** 原有 status 0 至 3 的语义 SHALL 保持不变

### Requirement: Ingestion Batch Persistence

系统 SHALL 提供 `kb_ingestion_batch` 保存批次键、manifest hash、来源类型、状态、计数、配置快照、摘要及生命周期时间。

#### Scenario: Batch counters are consistent
- **WHEN** 批次进入终态
- **THEN** completed、failed、skipped、review 和 cancelled 计数之和 SHALL 等于 total_count

### Requirement: Ingestion Item and Attempt Persistence

系统 SHALL 提供 `kb_ingestion_item` 保存批次项、document 关联、attempt、相对来源、源哈希、幂等键、state、stage、progress、审核状态、失败信息、质量摘要、配置快照和时间戳。

#### Scenario: Retry preserves previous attempt
- **WHEN** failed item 被重试
- **THEN** 新 attempt_no SHALL 递增
- **AND** 旧 attempt 的阶段、错误和时间 SHALL 保留

#### Scenario: Derived-file policy is auditable
- **WHEN** CAJ ingestion item 被创建
- **THEN** item 或其所属 batch 的 `config_snapshot` SHALL 保存生效的 `LITERATURE_RETAIN_DERIVED_PDF` 值

### Requirement: Normalized Identifier Constraints

系统 SHALL 对 DOI、标准号、batch key 和用户范围 idempotency key 使用规范化值和适当索引。约束 SHALL 支持确定性重复检查，同时不得破坏跨用户逻辑隔离。

#### Scenario: DOI normalization
- **WHEN** DOI 分别以 `https://doi.org/10.x/y`、`doi:10.x/y` 和 `10.x/y` 提交
- **THEN** 系统 SHALL 得到相同 `doi_normalized`

### Requirement: Failure Details Persisted Safely

文档和 ingestion item SHALL 保存稳定 failure_code、脱敏 failure_message 和 retryable。数据库可保存受限内部诊断引用，但普通 API SHALL NOT 返回 traceback、凭据或绝对路径。

#### Scenario: Worker fails after document creation
- **WHEN** 后台 worker 抛出异常
- **THEN** 文档 SHALL 进入 status=3
- **AND** 对应 item SHALL 保存失败阶段、错误码和 retryable
- **AND** 文档 SHALL NOT 永久停留 processing
