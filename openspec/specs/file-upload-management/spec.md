# file-upload-management Specification

## Purpose
TBD - created by archiving change migrate-and-unify-framework. Update Purpose after archive.

## Requirements

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

The system SHALL process uploaded documents for text extraction and chunk them into overlapping segments for indexing.

#### Scenario: Extract text from PDF
- **WHEN** a PDF file is uploaded
- **THEN** the system SHALL extract text content from the PDF

#### Scenario: Extract text from Word
- **WHEN** a Word document is uploaded
- **THEN** the system SHALL extract text content from the document

#### Scenario: Extract text from Excel
- **WHEN** an Excel file is uploaded
- **THEN** the system SHALL extract text content from the spreadsheet

#### Scenario: Chunk text with configurable size and overlap
- **WHEN** 文档文本被解析后进入分块
- **THEN** 系统 SHALL 按配置的 CHUNK_SIZE 切分文本
- **AND** 相邻块之间 SHALL 保留 CHUNK_OVERLAP 大小的重叠内容

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

### Requirement: Text Cleaning

系统 SHALL 在文档解析后对文本做清洗：合并多余空白、去除页眉页脚重复内容、去除不可见控制字符与 Unicode NFKC 规范化，再进入分块与向量化。

#### Scenario: Clean parsed text
- **WHEN** 文档文本被解析后
- **THEN** 系统 SHALL 合并多余空白与换行（3+ 个连续空白压成 2 个）
- **AND** 系统 SHALL 去除跨页重复 ≥ 3 次的页眉页脚行
- **AND** 系统 SHALL 去除不可见控制字符（保留 \t \n \r）
- **AND** 系统 SHALL 应用 Unicode NFKC 规范化（全角→半角等）
- **AND** 系统 SHALL 在清洗后再进入分块与向量化

### Requirement: Asynchronous Document Processing

系统 SHALL 支持异步处理文档，将分块与向量化放入后台执行，上传接口不因大文件处理而阻塞。

#### Scenario: Large document processed asynchronously
- **WHEN** 上传较大文档
- **THEN** 系统 SHALL 立即返回 HTTP 202 并转入后台处理
- **AND** 处理状态通过 `kb_document.status` 字段跟踪，遵循状态机：pending(0) → processing(2) → completed(1) 或 failed(3)

#### Scenario: Document status lifecycle
- **WHEN** 文档上传成功并提交后台处理
- **THEN** 系统 SHALL 将 `status` 置为 `0` (pending) 后立即返回
- **AND** 系统 SHALL 在 worker 开始处理时置 `status=2` (processing)
- **AND** 系统 SHALL 在分块与向量化成功后置 `status=1` (completed) 并更新 `chunk_count`
- **AND** 系统 SHALL 在任一环节抛出异常时置 `status=3` (failed) 并打印 traceback

#### Scenario: Worker failure promotes status to failed
- **WHEN** 后台 worker 在解析、切分或写向量库时抛出异常
- **THEN** 系统 SHALL 捕获异常并打印完整 traceback
- **AND** 系统 SHALL 将文档 `status` 推进到 `3` (failed)
- **AND** 系统 SHALL 不让文档永久停留 `2` (processing)

### Requirement: Status Enum Definition

系统 SHALL 在 `Document` 模型上定义入库生命周期状态常量：

| 常量 | 值 | 含义 |
|---|---|---|
| `STATUS_PENDING` | 0 | 待处理（新上传，worker 未启动） |
| `STATUS_COMPLETED` | 1 | 已完成（保留现有语义；现有数据 `status=1` 表"完成"，无需迁移） |
| `STATUS_PROCESSING` | 2 | 处理中（worker 已开始解析/切分/向量化） |
| `STATUS_FAILED` | 3 | 失败（worker 抛异常） |

#### Scenario: Existing data semantics preserved
- **WHEN** 重定义 status 枚举后
- **THEN** 现有 `status=1` 数据 SHALL 继续表示"已完成"
- **AND** 系统 SHALL NOT 进行数据迁移
- **AND** 现有依赖 `status=1` 的测试 stub SHALL 保持语义一致

### Requirement: Image-type PDF Detection

系统 SHALL 在 PDF 解析入口先做图片型/扫描件检测，命中阈值则全本 OCR，作为主路径而非兜底。

#### Scenario: Detect image-type PDF and trigger OCR as primary path
- **WHEN** 解析 PDF 文档
- **THEN** 系统 SHALL 采样前 5 页（或全部，若不足 5 页）计算平均字符数
- **AND** 平均字符数 < `Config.PDF_OCR_THRESHOLD`（默认 50）时 SHALL 触发全本 OCR 主路径
- **AND** 平均字符数 ≥ 阈值时 SHALL 走文本层提取路径

#### Scenario: Per-page OCR fallback for mixed-type PDF
- **WHEN** 文本层提取路径中某页 `extract_text()` 返回空
- **THEN** 系统 SHALL 对该单页触发 OCR 兜底
- **AND** 系统 SHALL 将 OCR 结果与文本层结果按页顺序拼接

### Requirement: Table Structure Preservation

系统 SHALL 在 PDF 解析中保留表格结构，输出为 Markdown 表格语法，使后续分块与引用可识别表格内容。

#### Scenario: Extract tables as Markdown
- **WHEN** 解析含表格的 PDF 页面
- **THEN** 系统 SHALL 调用 `pdfplumber.extract_tables()` 提取表格
- **AND** 系统 SHALL 将每个表格转为 Markdown 表格语法（含表头分隔行）
- **AND** 系统 SHALL 将表格 Markdown 拼接到该页文本末尾（用空行分隔）

### Requirement: Page-aware Parsing

系统 SHALL 在 PDF 解析时支持按页返回 `List[(page_num, text)]` 结构，使后续切分可保留页码元数据。

#### Scenario: PDF parsed with page metadata
- **WHEN** 调用 `parse_document(file_path, file_type, page_aware=True)` 解析 PDF
- **THEN** 系统 SHALL 返回 `List[Tuple[int, str]]`，每项为 `(page_num, page_text)`
- **AND** `page_num` SHALL 从 1 开始
- **AND** 非 PDF 格式（txt/docx/xlsx）SHALL 忽略 `page_aware` 参数并继续返回 `str`
