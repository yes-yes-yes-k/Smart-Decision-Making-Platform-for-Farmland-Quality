# vector-store Specification

## Purpose
TBD - created by archiving change migrate-and-unify-framework. Update Purpose after archive.

## Requirements

### Requirement: Chroma Vector Store Integration
The system SHALL integrate Chroma as the default vector store with persistent storage.

#### Scenario: Initialize vector store with persistent directory
- **WHEN** the system starts with CHROMA_PERSIST_DIR configured
- **THEN** the vector store SHALL initialize with the specified directory

#### Scenario: Add documents to vector store
- **WHEN** documents are submitted for storage
- **THEN** the system SHALL generate embeddings and store them in Chroma

#### Scenario: Search documents by similarity
- **WHEN** a query is submitted for semantic search
- **THEN** the system SHALL return the most relevant documents

#### Scenario: Delete documents by source
- **WHEN** a document is deleted from the system
- **THEN** the vector store SHALL remove all related embeddings

### Requirement: Collection Management
The system SHALL support managing multiple collections in the vector store.

#### Scenario: Create or get collection
- **WHEN** a collection name is specified
- **THEN** the system SHALL create the collection if it doesn't exist

#### Scenario: Clear collection
- **WHEN** a collection is cleared
- **THEN** all documents in the collection SHALL be removed

### Requirement: Metadata Support
The system SHALL support storing and filtering by document metadata.

#### Scenario: Store documents with metadata
- **WHEN** documents are added with metadata
- **THEN** the metadata SHALL be stored alongside the embeddings

#### Scenario: Filter search results by metadata
- **WHEN** a search query includes metadata filters
- **THEN** results SHALL be filtered by the specified metadata

### Requirement: Hybrid Search

系统 SHALL 支持混合检索：对查询同时执行向量相似度召回与 BM25 关键词召回，并用 RRF（Reciprocal Rank Fusion）融合两路结果后返回排序结果。

#### Scenario: Hybrid search combines vector and keyword paths
- **WHEN** 提交检索查询
- **THEN** 系统 SHALL 并行执行向量召回与 BM25 关键词召回
- **AND** 系统 SHALL 用 RRF 融合两路结果并返回排序后的文档

#### Scenario: BM25 keyword index maintained
- **WHEN** 文档被加入向量库或按 source 删除
- **THEN** 系统 SHALL 同步更新对应的 BM25 关键词索引

#### Scenario: Keyword recall catches terminology
- **WHEN** 查询包含高区分度专业术语（如"交换性氢"、"有效钾"）
- **THEN** 系统 SHALL 通过 BM25 关键词召回命中包含该术语的文档
