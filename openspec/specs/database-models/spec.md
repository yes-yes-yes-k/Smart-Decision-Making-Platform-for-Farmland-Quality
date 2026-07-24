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

