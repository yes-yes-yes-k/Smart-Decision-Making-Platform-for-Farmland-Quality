# Comet Design Handoff

- Change: migrate-and-unify-framework
- Phase: design
- Mode: compact
- Context hash: afd6bc5ab11dfba8f2c50444da2ab4ef03629ea65e523f03da0fe2dff4b4ecba

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/migrate-and-unify-framework/proposal.md

- Source: openspec/changes/migrate-and-unify-framework/proposal.md
- Lines: 1-38
- SHA256: 6c5907d2c61ce94c5695c6969d05ccfdb105f5663d5fd3adcdada547f0b18d43

```md
## Why

当前存在两个独立的项目（AI_culti_demo 和 org-backend），各自拥有独立的 LLM 服务、嵌入模型、向量存储和工作流编排能力，导致代码重复、维护成本高、功能难以协同。需要将这两个项目的核心能力迁移到统一框架中，整合 RAG、Function Calling 和多智能体架构，支持六个专业模型的并发处理，提升系统整体效率和可扩展性。

## What Changes

- 迁移 `AI_culti_demo -send` 的 LangGraph 多智能体工作流、LLM 服务、嵌入服务、专业评估模型到统一框架
- 迁移 `org-backend` 的 RAG 问答链、Chroma 向量存储、数据库模型、JWT 认证、文件上传和文档管理到统一框架
- 开发统一的框架架构，整合 RAG、Function Calling 和多智能体组件
- 支持六个专业模型的并发处理能力
- 统一嵌入模型配置，支持多种模型切换
- 合并 HTTP 服务，提供统一的 API 接口

## Capabilities

### New Capabilities

- `unified-llm-service`: 统一的 LLM 服务封装，支持多种模型和配置
- `unified-embedding-service`: 统一的嵌入服务，支持多种嵌入模型切换
- `vector-store`: 内置 Chroma 向量存储，支持文档向量化和语义检索
- `rag-chain`: RAG 问答链，整合检索与生成
- `multi-agent-orchestrator`: 多智能体编排器，支持六个专业模型并发处理
- `function-calling-system`: 函数调用系统，混合使用 LangChain Tools 和自定义接口
- `database-models`: 数据库模型，包含用户、对话、消息、文档等
- `jwt-authentication`: JWT 认证系统
- `file-upload-management`: 文件上传和文档管理

### Modified Capabilities

- `callable-thematic-model-stubs`: 扩展支持六个专业模型的并发调用接口
- `county-smart-diagnosis`: 集成多智能体工作流，支持并发模型调用

## Impact

- 代码结构重构：新增 `framework/` 目录作为统一框架核心
- API 接口变更：合并原有 HTTP 服务，提供统一 API
- 依赖更新：整合两个项目的依赖，移除重复包
- 数据迁移：需要迁移 org-backend 的数据库表结构和向量库数据
- 配置统一：整合配置管理，支持环境变量和配置文件
```

## openspec/changes/migrate-and-unify-framework/design.md

- Source: openspec/changes/migrate-and-unify-framework/design.md
- Lines: 1-193
- SHA256: 8b0a6408bbd3e08afac3826ec44e89d610c64d4b7b9254bdda4d44901098ea77

[TRUNCATED]

```md
## Context

当前存在两个独立项目：
1. **AI_culti_demo -send**: 包含 LangGraph 多智能体工作流、LLM 服务（DeepSeek-V4-Flash）、嵌入服务（bge-large-zh-v1.5）、酸化评估模型、石灰需求量计算等专业模型
2. **org-backend**: 包含 RAG 问答链、Chroma 向量存储、嵌入模型（bge-m3）、数据库模型、JWT 认证、文件上传管理

这两个项目各自独立运行，存在代码重复、配置分散、功能难以协同的问题。需要构建一个统一框架，将两者的核心能力整合，支持六个专业模型的并发处理。

## Goals / Non-Goals

**Goals:**
- 构建统一框架，整合 RAG、Function Calling 和多智能体架构
- 迁移两个项目的核心代码到统一框架
- 支持六个专业模型的并发处理
- 统一 LLM 和 Embedding 服务配置
- 合并 HTTP API 接口
- 保持与原有代码的兼容性

**Non-Goals:**
- 不修改现有已归档的 OpenSpec specs
- 不重构已稳定运行的业务逻辑
- 不引入新的数据库引擎（保持 MySQL）
- 不改变现有数据存储格式

## Decisions

### 1. 架构风格：模块化单体

**选择理由：**
- 项目规模适中，模块化单体便于开发和部署
- 避免微服务带来的运维复杂性
- 模块间通信效率高，适合多智能体并发场景

**架构层次：**
```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (Flask)                      │
│  /api/chat, /api/models/run, /api/auth, /api/documents      │
├─────────────────────────────────────────────────────────────┤
│                    Framework Core                           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │ LLM Service │ │ Embedding   │ │ Multi-Agent         │   │
│  │             │ │ Service     │ │ Orchestrator        │   │
│  └──────┬──────┘ └──────┬──────┘ └──────────┬──────────┘   │
│         │               │                    │              │
│         └──────┬────────┴────────────────────┘              │
│                ▼                                            │
│  ┌─────────────────────────────────────────────┐            │
│  │           Function Calling System            │            │
│  │  LangChain Tools + Custom Interfaces        │            │
│  └─────────────────────────────────────────────┘            │
│                ▲                                            │
│  ┌────────────┼────────────┐ ┌────────────────┐            │
│  │ RAG Chain  │            │ │ Vector Store   │            │
│  │            │            │ │ (Chroma)       │            │
│  └────────────┴────────────┘ └────────────────┘            │
├─────────────────────────────────────────────────────────────┤
│                    Domain Modules                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐ │
│  │ 酸化评估 │ │ 石灰计算 │ │ 其他4个  │ │ 数据加载模块   │ │
│  │          │ │          │ │ 专业模型 │ │                │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Data Layer                               │
│  MySQL (用户/对话/消息/文档)  │  Chroma (向量库)            │
└─────────────────────────────────────────────────────────────┘
```

### 2. 多智能体并发设计

**选择理由：**
- 六个专业模型需要独立运行，并发处理可以显著提升性能
- LangGraph 原生支持异步节点执行

**并发策略：**
- 使用 Python `asyncio` 实现模型并发调用
- LangGraph 节点使用 `@node.async` 装饰器
- 通过状态机协调各模型的执行顺序和依赖关系
- 结果汇总节点等待所有并发模型完成后进行聚合


```

Full source: openspec/changes/migrate-and-unify-framework/design.md

## openspec/changes/migrate-and-unify-framework/tasks.md

- Source: openspec/changes/migrate-and-unify-framework/tasks.md
- Lines: 1-71
- SHA256: d951d6271d174a654a2e9bd24a606232ad73eeac347788624927d2efb2d14a68

```md
## 1. 框架搭建

- [ ] 1.1 创建统一框架目录结构（framework/）
- [ ] 1.2 更新 pyproject.toml 添加依赖（Flask、SQLAlchemy、ChromaDB、LangGraph 等）
- [ ] 1.3 创建统一配置管理模块

## 2. 核心服务实现

- [ ] 2.1 实现统一 LLM 服务（framework/llm/service.py）
- [ ] 2.2 实现统一 Embedding 服务（framework/embedding/service.py）
- [ ] 2.3 实现向量存储模块（framework/vector_store/chroma_store.py）
- [ ] 2.4 实现 RAG 问答链（framework/rag/chain.py）

## 3. 函数调用系统

- [ ] 3.1 实现工具注册表（framework/function_calling/registry.py）
- [ ] 3.2 实现 LangChain Tools 集成
- [ ] 3.3 实现自定义工具接口（JSON Schema）
- [ ] 3.4 实现工具调用执行器

## 4. 多智能体编排器

- [ ] 4.1 实现多智能体状态机定义（framework/agents/state.py）
- [ ] 4.2 实现并发模型执行节点（framework/agents/nodes.py）
- [ ] 4.3 实现多智能体编排器（framework/agents/orchestrator.py）
- [ ] 4.4 扩展支持六个专业模型的并发处理

## 5. 数据库模型迁移

- [ ] 5.1 创建数据库模型（framework/models/user.py、conversation.py、message.py、document.py）
- [ ] 5.2 配置 SQLAlchemy 数据库连接
- [ ] 5.3 创建数据库初始化脚本

## 6. 认证系统迁移

- [ ] 6.1 实现 JWT 认证模块（framework/auth/jwt.py）
- [ ] 6.2 实现密码哈希和验证
- [ ] 6.3 实现认证装饰器

## 7. 文件上传管理

- [ ] 7.1 实现文件上传模块（framework/upload/file_upload.py）
- [ ] 7.2 实现文档解析模块（PDF、Word、Excel）
- [ ] 7.3 实现文档管理 API

## 8. 专业模型迁移

- [ ] 8.1 迁移酸化评估模型（framework/domain/assessment/acidification.py）
- [ ] 8.2 迁移石灰需求量计算模型（framework/domain/calculation/lime_calculator.py）
- [ ] 8.3 迁移土壤数据加载模块（framework/domain/data/soil_data_loader.py）
- [ ] 8.4 迁移其他四个专业模型

## 9. HTTP API 合并

- [ ] 9.1 创建 Flask 应用（framework/api/app.py）
- [ ] 9.2 迁移 org-backend 的聊天 API（framework/api/routes/chat.py）
- [ ] 9.3 迁移原有的诊断/概览 API（framework/api/routes/county.py）
- [ ] 9.4 迁移认证 API（framework/api/routes/auth.py）
- [ ] 9.5 迁移文档管理 API（framework/api/routes/documents.py）

## 10. 集成测试

- [ ] 10.1 测试 RAG 问答功能
- [ ] 10.2 测试多智能体并发工作流
- [ ] 10.3 测试 Function Calling 功能
- [ ] 10.4 测试用户认证功能
- [ ] 10.5 测试文档上传和管理功能

## 11. 数据迁移

- [ ] 11.1 迁移 MySQL 数据库表结构和数据
- [ ] 11.2 迁移 Chroma 向量库数据
```

## openspec/changes/migrate-and-unify-framework/specs/database-models/spec.md

- Source: openspec/changes/migrate-and-unify-framework/specs/database-models/spec.md
- Lines: 1-45
- SHA256: f186f0ca779f5d14f56773223513cfe96e7d9e44ad16b738bbddb75bd582b8dd

```md
## ADDED Requirements

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
```

## openspec/changes/migrate-and-unify-framework/specs/file-upload-management/spec.md

- Source: openspec/changes/migrate-and-unify-framework/specs/file-upload-management/spec.md
- Lines: 1-64
- SHA256: 27718a38d28e09ccd851697269feaacb870a5425535b29bdaa7cd3e0fdce0165

```md
## ADDED Requirements

### Requirement: File Upload
The system SHALL support uploading files with size limits.

#### Scenario: Upload file within size limit
- **WHEN** a file is uploaded that is within the size limit
- **THEN** the system SHALL accept and store the file

#### Scenario: Upload file exceeding size limit
- **WHEN** a file is uploaded that exceeds the size limit
- **THEN** the system SHALL reject the upload with an error

#### Scenario: Upload supported file types
- **WHEN** a supported file type is uploaded
- **THEN** the system SHALL accept the file

#### Scenario: Upload unsupported file types
- **WHEN** an unsupported file type is uploaded
- **THEN** the system SHALL reject the upload with an error

### Requirement: Document Processing
The system SHALL process uploaded documents for text extraction.

#### Scenario: Extract text from PDF
- **WHEN** a PDF file is uploaded
- **THEN** the system SHALL extract text content from the PDF

#### Scenario: Extract text from Word
- **WHEN** a Word document is uploaded
- **THEN** the system SHALL extract text content from the document

#### Scenario: Extract text from Excel
- **WHEN** an Excel file is uploaded
- **THEN** the system SHALL extract text content from the spreadsheet

### Requirement: Document Management
The system SHALL manage documents with metadata and status.

#### Scenario: List user documents
- **WHEN** a user requests their document list
- **THEN** the system SHALL return all documents owned by the user

#### Scenario: Get document details
- **WHEN** a user requests document details
- **THEN** the system SHALL return document metadata and status

#### Scenario: Delete document
- **WHEN** a user deletes a document
- **THEN** the system SHALL remove the document and its embeddings

### Requirement: Document Status Tracking
The system SHALL track document processing status.

#### Scenario: Set document status to processing
- **WHEN** a document is being processed
- **THEN** the system SHALL set status to processing

#### Scenario: Set document status to completed
- **WHEN** document processing is complete
- **THEN** the system SHALL set status to completed

#### Scenario: Set document status to failed
- **WHEN** document processing fails
- **THEN** the system SHALL set status to failed with an error message
```

## openspec/changes/migrate-and-unify-framework/specs/function-calling-system/spec.md

- Source: openspec/changes/migrate-and-unify-framework/specs/function-calling-system/spec.md
- Lines: 1-52
- SHA256: 864adaa4d963cd822f65e2d3f8845aa27e4bd2c2e9b80d84e6b94f82980c9010

```md
## ADDED Requirements

### Requirement: Function Calling System
The system SHALL provide a function calling system that supports both LangChain Tools and custom interfaces.

#### Scenario: Register LangChain Tools
- **WHEN** LangChain Tools are registered
- **THEN** they SHALL be available for LLM function calling

#### Scenario: Register custom tools
- **WHEN** custom tools with JSON Schema are registered
- **THEN** they SHALL be available for LLM function calling

#### Scenario: LLM selects and executes tools
- **WHEN** an LLM identifies the need to call a tool
- **THEN** the system SHALL execute the tool and return results

### Requirement: Tool Registry
The system SHALL maintain a registry of all available tools.

#### Scenario: List registered tools
- **WHEN** a request to list tools is made
- **THEN** the system SHALL return all registered tools with descriptions

#### Scenario: Get tool by name
- **WHEN** a tool is requested by name
- **THEN** the system SHALL return the tool definition

#### Scenario: Deregister tool
- **WHEN** a tool is deregistered
- **THEN** it SHALL no longer be available for calling

### Requirement: JSON Schema Validation
The system SHALL validate tool inputs against JSON Schema.

#### Scenario: Validate valid input
- **WHEN** a tool is called with valid input
- **THEN** the system SHALL execute the tool

#### Scenario: Validate invalid input
- **WHEN** a tool is called with invalid input
- **THEN** the system SHALL return a validation error

### Requirement: Mixed Tool Calling
The system SHALL support calling both LangChain Tools and custom tools in the same workflow.

#### Scenario: Call LangChain Tool then custom tool
- **WHEN** a workflow calls a LangChain Tool followed by a custom tool
- **THEN** both calls SHALL execute correctly

#### Scenario: Call custom tool then LangChain Tool
- **WHEN** a workflow calls a custom tool followed by a LangChain Tool
- **THEN** both calls SHALL execute correctly
```

## openspec/changes/migrate-and-unify-framework/specs/jwt-authentication/spec.md

- Source: openspec/changes/migrate-and-unify-framework/specs/jwt-authentication/spec.md
- Lines: 1-48
- SHA256: 025d10c2d4821f0f6d7ca7d8cc2c810bb2938d95af3a49eb756aad2ff6115813

```md
## ADDED Requirements

### Requirement: JWT Authentication
The system SHALL provide JWT-based authentication for API endpoints.

#### Scenario: User login
- **WHEN** a user provides valid credentials
- **THEN** the system SHALL return a JWT access token

#### Scenario: Token expiration
- **WHEN** a JWT token expires
- **THEN** the system SHALL reject requests until a new token is obtained

#### Scenario: Invalid token
- **WHEN** an invalid or tampered token is provided
- **THEN** the system SHALL reject the request with an error

### Requirement: Protected API Endpoints
The system SHALL protect API endpoints with JWT authentication.

#### Scenario: Access protected endpoint with valid token
- **WHEN** a valid JWT token is provided for a protected endpoint
- **THEN** the system SHALL grant access

#### Scenario: Access protected endpoint without token
- **WHEN** no token is provided for a protected endpoint
- **THEN** the system SHALL return a 401 error

#### Scenario: Access protected endpoint with expired token
- **WHEN** an expired token is provided for a protected endpoint
- **THEN** the system SHALL return a 401 error

### Requirement: Token Refresh
The system SHALL support token refresh functionality.

#### Scenario: Refresh access token
- **WHEN** a refresh token is provided
- **THEN** the system SHALL issue a new access token

### Requirement: Password Security
The system SHALL securely store and verify user passwords.

#### Scenario: Store hashed password
- **WHEN** a user is created
- **THEN** the system SHALL store a hash of the password, not the plain text

#### Scenario: Verify password
- **WHEN** a user attempts to login
- **THEN** the system SHALL verify the password against the stored hash
```

## openspec/changes/migrate-and-unify-framework/specs/multi-agent-orchestrator/spec.md

- Source: openspec/changes/migrate-and-unify-framework/specs/multi-agent-orchestrator/spec.md
- Lines: 1-56
- SHA256: b9519fd30ac565a3790179a1e7b1ab593dc083d3ce271e90a16e9b2fc7a0b58d

```md
## ADDED Requirements

### Requirement: Multi-Agent Orchestration
The system SHALL provide a multi-agent orchestrator that supports concurrent execution of up to six professional models.

#### Scenario: Execute multiple models concurrently
- **WHEN** a request is submitted that requires multiple models
- **THEN** the system SHALL execute the models concurrently

#### Scenario: Coordinate model execution order
- **WHEN** models have dependencies on each other
- **THEN** the system SHALL execute them in the correct order

#### Scenario: Aggregate results from concurrent models
- **WHEN** all concurrent models complete
- **THEN** the system SHALL aggregate and return combined results

### Requirement: LangGraph Integration
The system SHALL use LangGraph as the workflow orchestration engine.

#### Scenario: Build state machine workflow
- **WHEN** a workflow is defined with nodes and edges
- **THEN** LangGraph SHALL compile and execute the workflow

#### Scenario: Conditional routing
- **WHEN** a node returns a conditional output
- **THEN** the system SHALL route to the appropriate next node

#### Scenario: Async node execution
- **WHEN** nodes are marked as async
- **THEN** they SHALL execute concurrently

### Requirement: Six Professional Models Support
The system SHALL support six professional models for cultivated land assessment.

#### Scenario: Execute acidification assessment
- **WHEN** an acidification assessment request is submitted
- **THEN** the system SHALL execute the acidification model

#### Scenario: Execute lime demand calculation
- **WHEN** a lime demand calculation request is submitted
- **THEN** the system SHALL execute the lime calculator model

#### Scenario: Execute other assessment models
- **WHEN** requests for other models are submitted
- **THEN** the system SHALL route to the appropriate model

### Requirement: Error Handling in Workflow
The system SHALL handle errors during workflow execution gracefully.

#### Scenario: Single model failure
- **WHEN** one model fails during execution
- **THEN** the system SHALL continue with other models and report the error

#### Scenario: Complete workflow failure
- **WHEN** all models fail
- **THEN** the system SHALL return an error status with details
```

## openspec/changes/migrate-and-unify-framework/specs/rag-chain/spec.md

- Source: openspec/changes/migrate-and-unify-framework/specs/rag-chain/spec.md
- Lines: 1-33
- SHA256: 19b3be75be5d299936e510b26822a832c1f68a053f91f66623ae01a56f38ccb7

```md
## ADDED Requirements

### Requirement: RAG Question Answering
The system SHALL provide a RAG chain that combines retrieval and generation.

#### Scenario: Execute RAG query
- **WHEN** a user submits a question
- **THEN** the system SHALL retrieve relevant documents and generate an answer

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
```

## openspec/changes/migrate-and-unify-framework/specs/unified-embedding-service/spec.md

- Source: openspec/changes/migrate-and-unify-framework/specs/unified-embedding-service/spec.md
- Lines: 1-33
- SHA256: 768f18711d724958b1ccd1a9ad3ff6b3ce4213c5e53d21df63e5dad6fc08e0e0

```md
## ADDED Requirements

### Requirement: Unified Embedding Service Interface
The system SHALL provide a unified embedding service interface that supports multiple embedding models.

#### Scenario: Configure embedding model via environment variables
- **WHEN** the system starts with SILICONFLOW_API_KEY set
- **THEN** the embedding service SHALL initialize with the configured model

#### Scenario: Embed single query
- **WHEN** a user requests embedding for a single query
- **THEN** the system SHALL return a vector representation of the query

#### Scenario: Embed multiple documents
- **WHEN** a user requests embedding for multiple documents
- **THEN** the system SHALL return vector representations for all documents

#### Scenario: Fallback when embedding service is unavailable
- **WHEN** the configured embedding provider is unreachable
- **THEN** the system SHALL return empty vectors and use keyword matching as fallback

### Requirement: Support multiple embedding models
The system SHALL support configuring different embedding models via environment variables.

#### Scenario: Switch between bge-large-zh-v1.5 and bge-m3
- **WHEN** SILICONFLOW_EMBED_MODEL is set to different model names
- **THEN** the embedding service SHALL use the specified model

### Requirement: Vector compatibility
The system SHALL ensure vector outputs are compatible with vector store operations.

#### Scenario: Generated vectors can be stored and queried
- **WHEN** vectors are generated by the embedding service
- **THEN** they SHALL be compatible with Chroma vector store operations
```

## openspec/changes/migrate-and-unify-framework/specs/unified-llm-service/spec.md

- Source: openspec/changes/migrate-and-unify-framework/specs/unified-llm-service/spec.md
- Lines: 1-33
- SHA256: 3d66948a43c49f10f9e32f82c95a01aecd2457f3afcfc76dcf5b60365bacc3e3

```md
## ADDED Requirements

### Requirement: Unified LLM Service Interface
The system SHALL provide a unified LLM service interface that supports multiple LLM providers and models.

#### Scenario: Configure LLM provider via environment variables
- **WHEN** the system starts with SILICONFLOW_API_KEY set
- **THEN** the LLM service SHALL initialize with the configured provider

#### Scenario: Generate text with LLM
- **WHEN** a user requests text generation with a prompt
- **THEN** the system SHALL return generated text from the configured LLM

#### Scenario: Fallback when LLM is unavailable
- **WHEN** the configured LLM provider is unreachable
- **THEN** the system SHALL return a fallback response with an error message

### Requirement: Support multiple LLM models
The system SHALL support configuring different LLM models via environment variables.

#### Scenario: Switch to different chat model
- **WHEN** SILICONFLOW_CHAT_MODEL is set to a different model name
- **THEN** the LLM service SHALL use the specified model

#### Scenario: Configure model parameters
- **WHEN** temperature and max_tokens are configured
- **THEN** the LLM service SHALL use these parameters for generation

### Requirement: Conversation history support
The system SHALL support passing conversation history to the LLM.

#### Scenario: Generate response with conversation context
- **WHEN** a user provides conversation history along with a new prompt
- **THEN** the LLM service SHALL generate a response considering the context
```

## openspec/changes/migrate-and-unify-framework/specs/vector-store/spec.md

- Source: openspec/changes/migrate-and-unify-framework/specs/vector-store/spec.md
- Lines: 1-41
- SHA256: 397524436a8586b5a0118fd44d4b95ec48930fbe386d0a332db6b7f249ac705b

```md
## ADDED Requirements

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
```
