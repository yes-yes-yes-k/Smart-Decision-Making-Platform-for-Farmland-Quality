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

