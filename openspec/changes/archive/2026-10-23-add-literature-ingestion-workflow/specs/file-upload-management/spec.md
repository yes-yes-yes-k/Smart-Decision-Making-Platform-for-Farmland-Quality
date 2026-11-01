# file-upload-management Specification (Delta)

## ADDED Requirements

### Requirement: User Literature Upload Contract

系统 SHALL 在保持现有 `POST /api/v1/docs/upload` multipart 请求结构兼容的同时，支持可选文献元数据：`document_kind`、`title`、`authors`、`doi`、`journal`、`publication_date`、`standard_number`、`issuing_authority`、`source_url`、`source_category`、`cross_categories`、`language` 和 `idempotency_key`。每个文献上传请求 MUST 提供至少一个有效 `domain_labels`；系统 SHALL NOT 提供自动分类参数或行为。

#### Scenario: Existing client omits literature metadata
- **WHEN** 旧客户端按原契约上传支持的文件并提供有效领域标签
- **THEN** 系统 SHALL 接受请求
- **AND** SHALL 使用 `document_kind=other`
- **AND** SHALL 保持异步 202 行为
- **AND** 文档 SHALL 进入 `awaiting_admin_review`

#### Scenario: User uploads an academic paper with metadata
- **WHEN** 用户上传 PDF 并提供合法 DOI、作者数组、期刊、日期和领域标签
- **THEN** 系统 SHALL 规范化并保存元数据
- **AND** 服务端 SHALL 自行计算文件哈希和解析质量

#### Scenario: Invalid metadata encoding
- **WHEN** `authors` 或 `cross_categories` 不是合法 JSON 字符串数组，或日期不是 ISO 8601
- **THEN** 系统 SHALL 返回 HTTP 422 和 `invalid_metadata`
- **AND** SHALL 指明无效字段但不返回服务器内部路径

### Requirement: Public Literature Publication Policy

所有管理员审核通过且处理完成的文献 MUST 发布到公共知识库。审核前提交 SHALL 仅对上传者和管理员可见。文献上传者 SHALL NOT 选择私有发布；省略 `visibility_scope` 或提交 `public` 均表示审核通过后的目标可见性为 public。

#### Scenario: Regular user omits visibility
- **WHEN** 普通用户上传文献且未提供 `visibility_scope`
- **THEN** 提交 SHALL 在审核前仅对上传者和管理员可见
- **AND** 管理员批准且索引完成后文档 SHALL 设置为 public

#### Scenario: Upload duplicates published public document
- **WHEN** 用户上传的内容与已发布公共文档的确定性去重键相同
- **THEN** 系统 SHALL 返回 `duplicate_document` 和规范公共文档 ID
- **AND** SHALL NOT 创建第二份公共规范文档

#### Scenario: Upload duplicates another pending submission
- **WHEN** 用户上传的内容与另一用户尚未审核的提交哈希相同
- **THEN** 系统 SHALL NOT 返回另一用户的提交 ID、文件名、上传者或审核状态
- **AND** SHALL 保留当前用户可追踪的独立提交审计

#### Scenario: User requests private literature
- **WHEN** 用户提交 `visibility_scope=private`
- **THEN** 系统 SHALL 返回 HTTP 422 和 `visibility_not_configurable`
- **AND** SHALL 说明审核通过的文献只能发布到公共知识库

### Requirement: File Content Validation

系统 SHALL 同时校验扩展名、magic bytes、大小、加密状态和所需处理器。普通用户上传 SHALL NOT 接受 ZIP、服务器路径或目录。

#### Scenario: Extension does not match content
- **WHEN** 文件扩展名为 PDF 但文件签名不是受支持 PDF
- **THEN** 系统 SHALL 返回 HTTP 422 和 `content_type_mismatch`
- **AND** SHALL NOT 提交解析任务

#### Scenario: User uploads ZIP
- **WHEN** 普通用户向文档上传接口提交 ZIP
- **THEN** 系统 SHALL 返回 HTTP 415 和 `unsupported_file_type`
- **AND** SHALL 指引使用受控管理员批次流程，而不是自动解压

#### Scenario: Encrypted PDF cannot be parsed
- **WHEN** PDF 需要密码且请求未提供受支持的安全解密流程
- **THEN** 系统 SHALL 返回 HTTP 422 和 `encrypted_document`
- **AND** SHALL NOT 创建可检索 chunk

### Requirement: CAJ Upload Readiness

系统 SHALL 支持用户上传 CAJ，但在接收处理前确认 CAJ 转换器可用。原始 CAJ SHALL 保留，转换 PDF SHALL 作为可追溯派生文件处理。

#### Scenario: CAJ converter is available
- **WHEN** 用户上传合法 CAJ 且转换器健康检查通过
- **THEN** 系统 SHALL 接受文件并返回 HTTP 202
- **AND** 处理阶段 SHALL 在转换时显示 `converting`

#### Scenario: CAJ converter is unavailable
- **WHEN** 用户上传 CAJ 但转换器缺失或健康检查失败
- **THEN** 系统 SHALL 返回 HTTP 503 和 `processor_unavailable`
- **AND** SHALL 提供可重试提示
- **AND** SHALL NOT 让文档永久停留 pending

### Requirement: Configurable Derived PDF Retention

系统 SHALL 通过布尔配置 `LITERATURE_RETAIN_DERIVED_PDF` 控制 CAJ 转换所得受管派生 PDF 是否长期保留，默认值 MUST 为 `false`。无论配置为何，系统 MUST 保留原始 CAJ、转换器版本、转换时间和派生 PDF 哈希，并将生效配置写入 ingestion `config_snapshot`。

#### Scenario: Derived PDF retention disabled
- **WHEN** `LITERATURE_RETAIN_DERIVED_PDF=false` 且 CAJ 已成功提取内容和记录派生哈希
- **THEN** 系统 SHALL 删除受管临时派生 PDF
- **AND** SHALL 保留原始 CAJ 和转换溯源

#### Scenario: Derived PDF retention enabled
- **WHEN** `LITERATURE_RETAIN_DERIVED_PDF=true` 且 CAJ 转换成功
- **THEN** 系统 SHALL 将派生 PDF 保存到受管存储
- **AND** 派生 PDF SHALL 继承原文档的审核与公共发布策略

### Requirement: Structured Asynchronous Upload Response

成功接收文档后，接口 SHALL 返回 HTTP 202，包含文档摘要、入库 state、stage、progress、review_status 和 `status_url`。接收成功不得被描述为已完成索引或已经公开。

#### Scenario: Upload accepted for processing
- **WHEN** 文件和请求元数据通过接收校验
- **THEN** 响应 SHALL 包含 `document.status=0`
- **AND** `ingestion.stage=accepted`
- **AND** `ingestion.progress=0`
- **AND** `ingestion.review_status=pending`
- **AND** 可访问的 `status_url`

### Requirement: Ingestion Status Endpoint

系统 SHALL 提供 `GET /api/v1/docs/<id>/ingestion`，仅允许上传者或管理员查询提交处理详情。响应 SHALL 包含 state、stage、progress、review_status、attempt、时间戳、质量摘要以及失败时的稳定错误码、脱敏信息和 retryable。

#### Scenario: Owner polls processing document
- **WHEN** 所有者查询正在 OCR 的文档
- **THEN** 系统 SHALL 返回 `state=processing`、`stage=ocr` 和 0 至 100 的 progress

#### Scenario: Unauthorized user polls document
- **WHEN** 非所有者且非管理员查询文档入库状态
- **THEN** 系统 SHALL 返回 404 或不泄露存在性的授权错误

#### Scenario: Failed ingestion status
- **WHEN** 文档解析失败
- **THEN** 状态 SHALL 包含稳定 `failure_code`、用户可读 `failure_message` 和 `retryable`
- **AND** SHALL NOT 返回 traceback、命令行、凭据或绝对路径

### Requirement: Controlled Ingestion Retry

系统 SHALL 提供 `POST /api/v1/docs/<id>/retry`。只有所有者或管理员可重试 failed 且 retryable 的文档。每次重试 SHALL 创建新 attempt 并保留历史。

#### Scenario: Retry transient OCR failure
- **WHEN** 所有者重试标记为 retryable 的 OCR 失败文档
- **THEN** 系统 SHALL 创建新 attempt
- **AND** 文档 SHALL 回到 pending
- **AND** 旧 attempt 错误 SHALL 保留用于审计

#### Scenario: Retry completed document
- **WHEN** 用户尝试重试 completed 文档
- **THEN** 系统 SHALL 返回 409
- **AND** SHALL NOT 重复创建 chunk

### Requirement: Upload Idempotency

系统 SHALL 支持用户范围的 `idempotency_key`。相同 key 与相同文件哈希重放 SHALL 返回原 document/ingestion 结果；相同 key 与不同哈希 SHALL 返回冲突。

#### Scenario: Client retries timed-out upload response
- **WHEN** 客户端使用相同 idempotency key 和相同文件重试
- **THEN** 系统 SHALL 返回原文档和当前处理状态
- **AND** SHALL NOT 创建第二份文档或任务

### Requirement: Domain Label Review Gate

系统 MUST 要求用户上传时显式选择至少一个有效一级领域标签，并 MUST 在管理员审核前阻止转换、解析、OCR、分块和索引。只有管理员可以确认或修正提交标签并批准入库；系统 SHALL NOT 自动分类或生成候选标签。

#### Scenario: User omits labels
- **WHEN** 用户未提交有效领域标签
- **THEN** 系统 SHALL 返回 HTTP 422 和 `domain_label_required`
- **AND** SHALL NOT 创建提交或处理任务

#### Scenario: Valid labels await administrator review
- **WHEN** 用户提交至少一个有效领域标签且文件通过接收校验
- **THEN** 文档 SHALL 进入 `awaiting_admin_review`
- **AND** SHALL NOT 被转换、解析、向量化或公开

#### Scenario: Administrator approves labels and ingestion
- **WHEN** 管理员确认或修正至少一个有效领域标签并批准文档
- **THEN** 系统 SHALL 记录批准标签、审核人和审核时间
- **AND** SHALL 将文档提交到转换或解析队列
- **AND** 成功完成后 SHALL 以 public 发布

#### Scenario: Administrator rejects submission
- **WHEN** 管理员驳回文档并提供审核原因
- **THEN** 文档 SHALL 进入 `status=4` 和 `stage=rejected`
- **AND** SHALL NOT 创建任何可检索 chunk

### Requirement: Administrator Literature Review API

系统 SHALL 提供仅管理员可用的待审核列表和审核决策接口。`GET /api/v1/docs/reviews?state=pending` SHALL 返回待审核提交；`POST /api/v1/docs/<id>/review` SHALL 接受 `decision=approve|reject`、批准标签及可选审核意见，并持久化审核审计。

#### Scenario: Regular user attempts approval
- **WHEN** 非管理员调用文献审核接口
- **THEN** 系统 SHALL 返回 HTTP 403
- **AND** SHALL NOT 更改审核状态或启动处理

#### Scenario: Administrator replays same decision
- **WHEN** 管理员以相同幂等键重放完全相同的审核决策
- **THEN** 系统 SHALL 返回原审核结果
- **AND** SHALL NOT 重复创建处理任务

#### Scenario: Administrator submits conflicting decision
- **WHEN** 已有终态审核决策后又通过普通审核接口提交相反决策
- **THEN** 系统 SHALL 返回 HTTP 409 和 `review_already_finalized`
- **AND** SHALL NOT 静默覆盖原审核记录

### Requirement: Page-bounded OCR Processing

PDF 处理 SHALL 对每页检测文本层，仅将低文本页送入 OCR，并按页或有限页批次渲染。系统 SHALL NOT 为大型扫描 PDF 一次性在内存中生成全部页面图片。

#### Scenario: Mixed text and scanned PDF
- **WHEN** PDF 同时包含文本页和无文本扫描页
- **THEN** 系统 SHALL 保留文本页提取结果
- **AND** 仅对扫描页执行 OCR
- **AND** 按原页序返回页面文本和页码

#### Scenario: OCR produces empty pages
- **WHEN** OCR 后仍存在空页或错误页
- **THEN** 系统 SHALL 在质量摘要中记录数量
- **AND** SHALL 根据配置质量门槛决定 completed 或 failed
