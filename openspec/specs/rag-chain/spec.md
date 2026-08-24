# rag-chain Specification

## Purpose
TBD - created by archiving change migrate-and-unify-framework. Update Purpose after archive.

## Requirements

### Requirement: RAG Question Answering

The system SHALL provide a RAG chain that combines hybrid retrieval (vector + BM25) with reranking and generation.

#### Scenario: Execute RAG query
- **WHEN** a user submits a question
- **THEN** the system SHALL retrieve relevant documents via hybrid retrieval, rerank them, and generate an answer

#### Scenario: Rerank retrieved candidates
- **WHEN** 混合检索召回的候选文档数量大于最终需要的 top-K
- **THEN** 系统 SHALL 对候选文档做精排（rerank），仅保留最相关的 top-K 送入生成

#### Scenario: Return answer with sources
- **WHEN** a RAG query is executed
- **THEN** the system SHALL return the answer along with source references

#### Scenario: Handle missing documents
- **WHEN** no relevant documents are found for a query
- **THEN** the system SHALL inform the user that there is insufficient information

### Requirement: Conversation History Integration
The system SHALL support passing conversation history to the RAG chain.

#### Scenario: Maintain conversation context
- **WHEN** a user continues a conversation
- **THEN** the RAG chain SHALL consider previous messages

#### Scenario: Limit history window
- **WHEN** conversation history exceeds the limit
- **THEN** the system SHALL only use the most recent messages

### Requirement: Source Validation
The system SHALL validate that retrieved sources exist in the database.

#### Scenario: Filter invalid sources
- **WHEN** retrieved documents reference non-existent sources
- **THEN** the system SHALL filter out those sources from results
