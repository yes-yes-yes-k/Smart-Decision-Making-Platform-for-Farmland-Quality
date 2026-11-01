# database-models Specification

## Purpose
TBD - created by archiving change migrate-and-unify-framework. Update Purpose after archive.

## Requirements

### Requirement: Database Models
The system SHALL provide database models for users, conversations, messages, and documents.

#### Scenario: User model
- **WHEN** a user is created
- **THEN** the system SHALL store user information including username and password hash

#### Scenario: Conversation model
- **WHEN** a conversation is created
- **THEN** the system SHALL store conversation metadata linked to a user

#### Scenario: Message model
- **WHEN** a message is sent
- **THEN** the system SHALL store message content linked to a conversation

#### Scenario: Document model
- **WHEN** a document is uploaded
- **THEN** the system SHALL store document metadata and status

### Requirement: ORM Integration
The system SHALL use SQLAlchemy ORM for database operations.

#### Scenario: Query database
- **WHEN** a query is executed via SQLAlchemy
- **THEN** the system SHALL return results from the database

#### Scenario: Transaction management
- **WHEN** multiple operations need to be atomic
- **THEN** the system SHALL use database transactions

### Requirement: Data Migration Support
The system SHALL support migrating data from org-backend.

#### Scenario: Migrate user data
- **WHEN** a data migration is initiated
- **THEN** user data from the source database SHALL be migrated

#### Scenario: Migrate conversation data
- **WHEN** a data migration is initiated
- **THEN** conversation and message data SHALL be migrated

#### Scenario: Migrate document data
- **WHEN** a data migration is initiated
- **THEN** document metadata SHALL be migrated

### Requirement: Soil Data Models
系统 SHALL 提供 8 张土壤数据的 SQLAlchemy 模型，按数据源分表存储乐昌市土壤数据。模型包括：三普表层土（ThirdSurveyTopsoil）、三普剖面理化（ThirdSurveyProfile）、三普立地条件（ThirdSurveySiteCondition）、三普容重（ThirdSurveyBulkDensity）、二普点（SecondSurveyPoint）、测土配方（FormulaFertilization）、农业化学化（AgriChemicalization）、粮食产量（GrainYield）。

#### Scenario: 三普表层土模型
- **WHEN** 数据库表被创建
- **THEN** `ThirdSurveyTopsoil` 模型 SHALL 包含 pH、有机质、有效磷、速效钾、阳离子交换量等土壤理化指标字段，并支持经纬度定位

#### Scenario: 三普剖面理化模型
- **WHEN** 数据库表被创建
- **THEN** `ThirdSurveyProfile` 模型 SHALL 包含剖面深度、土壤质地、容重、孔隙度等剖面理化数据字段

#### Scenario: 测土配方模型
- **WHEN** 数据库表被创建
- **THEN** `FormulaFertilization` 模型 SHALL 包含 pH、有机质、有效磷、速效钾等测土配方表层土数据字段

#### Scenario: 农业化学化模型
- **WHEN** 数据库表被创建
- **THEN** `AgriChemicalization` 模型 SHALL 包含年份、县区、化肥施用量等农业化学化指标字段

#### Scenario: 粮食产量模型
- **WHEN** 数据库表被创建
- **THEN** `GrainYield` 模型 SHALL 包含年份、县区、粮食作物播种面积、产量等字段

#### Scenario: 模型注册与建表
- **WHEN** `init_db.py` 运行 `db.create_all()`
- **THEN** 系统 SHALL 创建全部 8 张土壤数据表，表名使用复数形式（如 `third_survey_topsoils`）

### Requirement: DataFile 数据文件模型
系统 SHALL 提供 `DataFile` SQLAlchemy 模型（位于 `framework/models/data_file.py`），对应数据库表 `kb_data_file`，用于存储用户上传的数据文件（raw_data/improved_data 分类）的元数据。`DataFile` 模型 SHALL 被 `framework/api/routes/docs.py` 导入，支持数据文件上传接口的存储和查询功能。

`DataFile` 模型 SHALL 包含以下字段：
- `id`：主键，自增整数
- `doc_name`：原始文件名（字符串）
- `file_path`：存储路径/新文件名（字符串）
- `file_type`：文件类型（字符串）
- `file_size`：文件大小，字节（整数）
- `category`：文件分类（字符串，如 raw_data/improved_data）
- `treatment_type`：治理类型（字符串，可选）
- `status`：状态标志（整数，如 1=有效）
- `create_by`：创建者用户 ID（整数）
- `create_time`：创建时间（datetime，默认当前时间）

`DataFile` 模型 SHALL 提供 `to_dict()` 方法，返回包含上述字段的字典。

#### Scenario: 数据文件上传存储
- **WHEN** 用户上传一个分类为 `raw_data` 的数据文件，且文件通过查重检查
- **THEN** 系统 SHALL 创建 `DataFile` 实例，填充 doc_name/file_path/file_type/file_size/category/treatment_type/status/create_by 字段
- **AND** 系统 SHALL 将实例添加到数据库会话并提交
- **AND** 系统 SHALL 返回包含 `data_file.to_dict()` 的成功响应

#### Scenario: DataFile 模型导入可用
- **WHEN** `framework/api/routes/docs.py` 执行 `from framework.models.data_file import DataFile`
- **THEN** 导入 SHALL 成功，不抛出 ModuleNotFoundError
- **AND** `DataFile` SHALL 可用于构造数据文件实例

#### Scenario: to_dict 方法返回完整字段
- **WHEN** 调用 `DataFile` 实例的 `to_dict()` 方法
- **THEN** 返回的字典 SHALL 包含 id/doc_name/file_path/file_type/file_size/category/treatment_type/status/create_by/create_time 字段

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

### Requirement: 会话当前分析对象持久化

`Conversation` SHALL 保存 `analysis_object` JSON、`context_version` 和 `analysis_object_updated_at`。`analysis_object` 可空；`context_version` SHALL 默认为 0，并在对象设置、切换或清空成功时递增。

#### Scenario: 新会话默认无分析对象

- **WHEN** 系统创建新会话
- **THEN** `analysis_object` SHALL 为 null
- **AND** `context_version` SHALL 为 0

#### Scenario: 成功切换对象后持久化

- **WHEN** `AnalysisContextService` 成功验证并切换对象
- **THEN** Conversation SHALL 原子写入规范对象、更新时间并递增上下文版本

### Requirement: 消息分析上下文快照

`Message` SHALL 提供 `analysis_context_snapshot` JSON 字段，保存消息生成时的计算模式、规范对象和上下文版本。历史消息序列化 SHALL 返回该快照，不得使用会话当前对象替换历史快照。

#### Scenario: 切换对象后查看旧消息

- **WHEN** 一条消息在地块 P001 上生成，随后会话切换到地块 P002
- **THEN** 旧消息的 `analysis_context_snapshot` SHALL 继续指向 P001

#### Scenario: 对象不足提示保存快照

- **WHEN** 系统生成 `needs_analysis_object` 助手提示
- **THEN** 用户消息和助手提示 SHALL 保存当时的空对象或不足尺度对象快照
