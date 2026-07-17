# Comet Design Handoff

- Change: add-doc-dedup-and-cleanup
- Phase: design
- Mode: compact
- Context hash: b019314a54fa9ace672b3cf6d94e8ece170a5756d84221f991ad77c66be5c637

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/add-doc-dedup-and-cleanup/proposal.md

- Source: openspec/changes/add-doc-dedup-and-cleanup/proposal.md
- Lines: 1-29
- SHA256: 9ed6fb23458465a389040ba0c74130277ae83d0a20d3abe5d67a539ca8fd110e

```md
## Why

当前文档上传流程缺少查重机制，用户可以重复上传相同内容的文档（即使文件名不同），导致向量库中出现重复数据，浪费存储空间并影响 RAG 检索质量。同时，删除文档时只清理了数据库记录和向量库数据，但 `uploads/` 目录中的物理文件未被删除，造成磁盘空间泄漏。

## What Changes

- 上传时基于文件内容哈希（SHA-256）检测重复文档，拒绝重复入库
- `Document` 模型新增 `file_hash` 字段存储文件内容哈希
- 删除文档时同步删除 `uploads/` 目录中的物理文件
- 删除操作失败时（如物理文件已被手动删除）记录日志但不阻塞数据库清理

## Capabilities

### New Capabilities
<!-- 本次无新增 capability，仅修改现有 capability -->

### Modified Capabilities
- `file-upload-management`: 新增文档内容查重要求（上传时基于 SHA-256 哈希去重）；完善删除文档要求（删除时同步清理物理文件）

## Impact

- **代码**:
  - `framework/models/document.py` — 新增 `file_hash` 字段
  - `framework/upload/file_upload.py` — 新增文件哈希计算函数
  - `framework/api/routes/docs.py` — 上传接口增加查重逻辑，删除接口增加物理文件清理
  - `framework/config.py` — 可能新增配置项
- **数据库**: `kb_document` 表新增 `file_hash` 列（需要数据库迁移）
- **API**: 上传接口在检测到重复时返回 409 Conflict；删除接口行为不变（仍返回 200）
- **依赖**: 无新增依赖，使用 Python 标准库 `hashlib`

```

## openspec/changes/add-doc-dedup-and-cleanup/design.md

- Source: openspec/changes/add-doc-dedup-and-cleanup/design.md
- Lines: 1-54
- SHA256: 8223e591c2148c948b38bff583b58e6a9d3def1c8898939416ccfc34cb01f4de

```md
## Context

当前文档上传流程（`framework/api/routes/docs.py`）直接保存文件、解析内容、入库，无查重机制。删除流程只调用 `vector_store.delete_by_source()` 和 `db.session.delete()`，未清理 `uploads/` 目录中的物理文件。

数据库表 `kb_document` 当前字段：`doc_name`, `file_path`, `file_type`, `file_size`, `chunk_count`, `status`, `category`, `treatment_type`, `create_by`, `create_time`, `update_time`。

## Goals / Non-Goals

**Goals:**
- 上传时基于文件内容 SHA-256 哈希检测重复，同用户下重复文档拒绝入库
- 删除文档时同步清理物理文件、向量库数据、数据库记录
- 物理文件删除失败不阻塞数据库清理（容错）

**Non-Goals:**
- 不做跨用户的文档查重（每个用户独立）
- 不做内容相似度检测（只做精确哈希去重）
- 不做软删除/回收站机制
- 不迁移历史数据（历史文档 `file_hash` 为空，不参与查重）

## Decisions

### Decision 1: 使用 SHA-256 计算文件内容哈希

**选择**: 使用 Python 标准库 `hashlib.sha256` 对文件二进制内容计算哈希。

**理由**: SHA-256 碰撞率极低，性能足够（50MB 文件 < 100ms），无需新增依赖。

**备选方案**:
- MD5：更快但碰撞率较高，不推荐用于去重
- 文件名 + 文件大小：不可靠，不同文件名可能内容相同

### Decision 2: 查重范围为同用户下

**选择**: 上传时查询 `Document.query.filter_by(file_hash=hash, create_by=user_id).first()`，仅在当前用户范围内查重。

**理由**: 不同用户可能需要独立维护自己的文档副本；跨用户查重会引入权限复杂度。

### Decision 3: 物理文件删除失败时容错处理

**选择**: 删除物理文件时 try-except 包裹，失败时 `print` 日志但继续删除数据库记录。

**理由**: 物理文件可能已被手动删除或权限问题，不应阻塞数据库清理。保持数据库与向量库的一致性优先级高于物理文件清理。

### Decision 4: `file_hash` 字段可为空

**选择**: `file_hash` 字段设为 `nullable=True`，历史数据该字段为 NULL。

**理由**: 避免历史数据迁移复杂性。查重查询时 `file_hash IS NOT NULL` 自动跳过历史数据。

## Risks / Trade-offs

- **[风险] 大文件哈希计算内存占用** → 使用分块读取（8192 字节/块）流式计算，避免一次性加载整个文件到内存
- **[权衡] 查重只针对精确内容相同** → 无法检测"近似重复"文档，但实现简单可靠，满足当前需求
- **[风险] 物理文件删除失败导致磁盘泄漏** → 通过日志记录便于后续排查，不阻塞业务流程

```

## openspec/changes/add-doc-dedup-and-cleanup/tasks.md

- Source: openspec/changes/add-doc-dedup-and-cleanup/tasks.md
- Lines: 1-23
- SHA256: 5a85f704eaec27ae1b68a14f89c5368811f98f39d27142ff7a4bedc3d38e9c9f

```md
## 1. 数据模型与工具函数

- [ ] 1.1 在 `framework/models/document.py` 的 `Document` 模型中新增 `file_hash` 字段（String(64), nullable=True, comment='文件内容SHA-256哈希'）
- [ ] 1.2 在 `framework/upload/file_upload.py` 中新增 `compute_file_hash(file_path)` 函数，使用 `hashlib.sha256` 分块读取（8192 字节/块）计算文件哈希
- [ ] 1.3 在 `framework/upload/file_upload.py` 的 `save_uploaded_file` 函数返回值中增加文件哈希（返回三元组：new_filename, file_path, file_hash）

## 2. 上传查重逻辑

- [ ] 2.1 在 `framework/api/routes/docs.py` 的 `upload_document` 接口中，保存文件后计算哈希，查询 `Document.query.filter_by(file_hash=hash, create_by=user_id).first()` 检测重复
- [ ] 2.2 检测到重复时，删除刚保存的物理文件，返回 409 Conflict 错误，响应中包含已存在文档的 ID
- [ ] 2.3 未检测到重复时，在创建 `Document` 记录时填入 `file_hash` 字段

## 3. 删除清理逻辑

- [ ] 3.1 在 `framework/api/routes/docs.py` 的 `delete_document` 接口中，删除数据库记录前先删除物理文件
- [ ] 3.2 物理文件路径通过 `Config.UPLOAD_FOLDER + document.file_path` 拼接
- [ ] 3.3 使用 try-except 包裹物理文件删除逻辑，失败时 `print` 日志但继续删除数据库记录和向量库数据

## 4. 验证

- [ ] 4.1 上传相同内容不同文件名的文档，验证返回 409 Conflict
- [ ] 4.2 删除文档后，验证 `uploads/` 目录中对应物理文件已被删除
- [ ] 4.3 删除文档时物理文件已不存在，验证不报错且数据库记录正常删除

```

## openspec/changes/add-doc-dedup-and-cleanup/specs/file-upload-management/spec.md

- Source: openspec/changes/add-doc-dedup-and-cleanup/specs/file-upload-management/spec.md
- Lines: 1-49
- SHA256: 4d0e5312e7b88b701ec9e584a8cd02f798b83991a955d439efedac8798c7a594

```md
## ADDED Requirements

### Requirement: Document Content Deduplication
The system SHALL detect duplicate documents based on file content hash (SHA-256) and reject duplicate uploads within the same user scope.

#### Scenario: Upload duplicate document with different filename
- **WHEN** a user uploads a file whose content hash matches an existing document owned by the same user
- **THEN** the system SHALL reject the upload with a 409 Conflict error and include the existing document ID in the response

#### Scenario: Upload same content by different users
- **WHEN** a user uploads a file whose content hash matches a document owned by a different user
- **THEN** the system SHALL accept the upload and create a new document record

#### Scenario: Upload first occurrence of content
- **WHEN** a user uploads a file whose content hash does not match any existing document owned by the same user
- **THEN** the system SHALL accept the upload, compute and store the SHA-256 hash in the document record

#### Scenario: Historical document without hash
- **WHEN** a user uploads a file and existing documents have NULL file_hash values
- **THEN** the system SHALL skip NULL hash documents during deduplication check and only compare against non-NULL hashes

## MODIFIED Requirements

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
- **THEN** the system SHALL remove the database record, delete associated embeddings from the vector store, and delete the physical file from the upload directory

#### Scenario: Delete document when physical file is missing
- **WHEN** a user deletes a document and the physical file no longer exists in the upload directory
- **THEN** the system SHALL log a warning, continue to remove the database record and vector store embeddings, and return success

#### Scenario: Delete document when physical file deletion fails
- **WHEN** a user deletes a document and physical file deletion raises an error (e.g., permission denied)
- **THEN** the system SHALL log the error, continue to remove the database record and vector store embeddings, and return success

#### Scenario: Delete document when vector store deletion fails
- **WHEN** a user deletes a document and vector store deletion raises an error
- **THEN** the system SHALL log the error, continue to remove the database record and physical file, and return success

```
