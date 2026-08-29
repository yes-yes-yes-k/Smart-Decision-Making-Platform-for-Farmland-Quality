# vector-store Specification (Delta)

## MODIFIED Requirements

### Requirement: Metadata Support

The system SHALL support storing and filtering by document metadata, including chunk-level metadata such as page, section, category, and treatment_type.

#### Scenario: Store documents with metadata
- **WHEN** documents are added with metadata
- **THEN** the metadata SHALL be stored alongside the embeddings

#### Scenario: Store chunk-level metadata
- **WHEN** 文档被分块并入库
- **THEN** 每个 chunk SHALL 携带 category、treatment_type、chunk_index 元数据
- **AND** page、section 为后续阶段可选字段（当前解析器不产出，P1 不写入）

#### Scenario: Filter search results by metadata
- **WHEN** a search query includes metadata filters
- **THEN** results SHALL be filtered by the specified metadata

### Requirement: Collection Management

The system SHALL support managing multiple collections in the vector store, including domain-split collections routed by document category.

#### Scenario: Create or get collection
- **WHEN** a collection name is specified
- **THEN** the system SHALL create the collection if it doesn't exist

#### Scenario: Route to domain collection
- **WHEN** 文档按 category 入库或查询
- **THEN** 系统 SHALL 路由到该 category 对应的分领域 collection

#### Scenario: Clear collection
- **WHEN** a collection is cleared
- **THEN** all documents in the collection SHALL be removed