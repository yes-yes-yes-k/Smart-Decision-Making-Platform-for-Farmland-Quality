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

### Requirement: Query Synonym Preprocessing

系统 SHALL 在查询进入检索前，依据耕地领域同义词/专业词表对查询做同义词替换，用规范化术语改写查询后再向量化与检索。

#### Scenario: Synonym replacement applies to query
- **WHEN** 查询包含词表中已登记的同义词（如"可交换氢"）
- **THEN** 系统 SHALL 将其替换为规范术语（如"交换性氢"）后进入检索

#### Scenario: Unmatched terms pass through
- **WHEN** 查询不包含词表中的任何词条
- **THEN** 系统 SHALL 保持查询原样，不做改写

### Requirement: Chunk-level Source Citation

系统 SHALL 在返回答案时，将来源引用精确到具体 chunk 或其所在页码/章节，使用户可回看原文片段。

#### Scenario: Answer cites chunk-level source
- **WHEN** RAG 查询被回答且命中某文档的若干 chunk
- **THEN** 系统 SHALL 在 `sources` 中为每个命中 chunk 输出包含以下字段的对象：
  - `doc_name`：原文档名（保留现有字段，向前兼容）
  - `chunk_index`：chunk 在该文档中的序号（从 0 开始）
  - `page`：chunk 所属页码（从 1 开始；非分页格式如 txt/docx/xlsx 为 `null`）

#### Scenario: Sources field structure example
- **WHEN** 命中某文档的第 2 个 chunk（来自第 5 页）
- **THEN** 系统 SHALL 在 `sources` 中包含形如 `{"doc_name": "xxx.pdf", "chunk_index": 1, "page": 5}` 的对象

#### Scenario: Metadata missing degrades gracefully
- **WHEN** 命中 chunk 的 metadata 缺失 `chunk_index` 或 `page` 字段（如旧数据）
- **THEN** 系统 SHALL 在 sources 对应字段返回 `null`
- **AND** 系统 SHALL NOT 抛出异常或丢弃该 source

#### Scenario: Cross-page chunk boundary
- **WHEN** chunk 跨越多页（本期设计为不拼接，但作为边界说明）
- **THEN** 系统 SHALL 取 chunk 起始所属页作为 `page` 值
- **AND** 系统 SHALL NOT 在 `page` 字段返回多个页码（避免歧义）

#### Scenario: Streaming and non-streaming consistency
- **WHEN** 同一查询分别走 `chat()` 与 `chat_stream()` 路径
- **THEN** 系统 SHALL 在两条路径返回结构相同的 `sources` 对象
- **AND** 系统 SHALL NOT 在流式路径省略 `chunk_index` 或 `page` 字段
