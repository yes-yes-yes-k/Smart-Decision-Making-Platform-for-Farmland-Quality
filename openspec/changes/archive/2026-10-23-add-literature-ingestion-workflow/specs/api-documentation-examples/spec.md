# api-documentation-examples Specification (Delta)

## ADDED Requirements

### Requirement: Literature Upload Examples

API 文档 SHALL 提供兼容旧 multipart 结构的最小上传示例，以及包含论文元数据和显式领域标签的完整示例。文档 MUST 说明系统不提供自动分类，且 `domain_labels` 为文献上传必填字段。

#### Scenario: Developer reads paper upload example
- **WHEN** 开发者查看 `POST /api/v1/docs/upload`
- **THEN** 文档 SHALL 展示 multipart 文件及 `document_kind=academic_paper`、title、authors、doi、journal、publication_date、domain_labels 和 idempotency_key
- **AND** SHALL 说明提交先等待管理员审核，成功完成后统一发布到公共知识库
- **AND** SHALL 展示私有发布请求的 `visibility_not_configurable` 错误

### Requirement: Asynchronous Status and Retry Examples

API 文档 SHALL 展示 202 接收响应、状态轮询、awaiting_admin_review、rejected、completed、failed 和 retry 请求/响应。

#### Scenario: Client implements progress UI
- **WHEN** 客户端按文档实现状态轮询
- **THEN** 示例 SHALL 包含 state、stage、progress、attempt、quality_summary、failure_code 和 retryable

### Requirement: Administrator Review Examples

API 文档 SHALL 展示管理员待审核列表、批准和驳回请求/响应，并说明批准时必须确认至少一个领域标签、普通用户不能自审、审核决策需要幂等键。

#### Scenario: Administrator approves a user paper
- **WHEN** 管理员查看 `POST /api/v1/docs/<id>/review` 文档
- **THEN** 示例 SHALL 包含 `decision=approve`、确认后的 domain_labels、review_note 和 idempotency_key
- **AND** SHALL 说明批准后才启动解析和索引
- **AND** SHALL 说明成功完成后 `visibility_scope=public`

### Requirement: Upload Error Examples

API 文档 SHALL 为重复、超限、不支持格式、内容签名不匹配、加密文档、无效元数据、缺少标签、私有发布请求、审核冲突、队列容量和处理器不可用提供 409、413、415、422、429/503 示例及稳定 error_code。

#### Scenario: CAJ processor unavailable example
- **WHEN** 开发者查看 CAJ 上传失败示例
- **THEN** 文档 SHALL 展示 HTTP 503、`processor_unavailable` 和可重试说明
- **AND** SHALL NOT 暴露转换器安装路径或命令行

### Requirement: Batch Administration Examples

API 与运维文档 SHALL 展示 manifest dry-run、管理员批次创建、查询、重试和取消示例，并明确普通用户不得上传 ZIP 或提交服务器路径。

#### Scenario: Administrator performs dry run
- **WHEN** 管理员查看批次入库文档
- **THEN** 文档 SHALL 展示 ready、duplicate、needs_review、invalid、processor_unavailable 和预计 OCR/CAJ 数量
- **AND** SHALL 说明 dry-run 不写数据库和向量库

