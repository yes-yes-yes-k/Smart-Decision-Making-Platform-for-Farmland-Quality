# api-documentation-examples Specification

## Purpose
TBD - created by archiving change add-model-run-apifox-examples. Update Purpose after archive.

## Requirements

### Requirement: 模型调用文档展示六个正式专业模型

系统 MUST 在 `POST /api/v1/models/run` 的文档中展示 6 个正式专业模型请求示例：`obstacle-diagnosis`、`acidification-remediation`、`organic-matter-improvement`、`stability-risk-evaluation` 和 `quality-grade-evaluation`。每个示例 MUST 给出最小输入、地块标识或运行前提以及预期可靠性状态。

#### Scenario: 在接口文档中选择正式模型示例
- **WHEN** 调用者查看模型调用接口的 JSON 请求示例
- **THEN** 文档 MUST 显示 6 个正式模型的规范 ID、中文名称和可直接调用的示例

### Requirement: 文档区分正式、辅助和实验性能力

系统 MUST 在模型 API 与聊天 API 文档中标明空间结构解析和关键指标解析为辅助能力，协同提升为实验性能力，并说明它们不属于正式专业 Agent 或聊天路由范围。

#### Scenario: 查阅辅助或实验性能力说明
- **WHEN** 调用者查阅模型目录说明
- **THEN** 文档 MUST 显示能力分类、是否可聊天路由、可靠性状态和运行限制

### Requirement: 聊天接口文档展示零至六的问题类型

系统 MUST 在 `/api/v1/chat/` 文档中说明 `question_type=0` 为 RAG，`question_type=1..6` 各自对应单一正式 Agent，并明确 type 1 稳定性风险与 type 2 质量等级、以及 type 4 酸化与 type 5 有机质的业务边界。

#### Scenario: 查阅相关业务边界问题的路由
- **WHEN** 调用者查看稳定性风险、质量等级或酸化/有机质施用问题的聊天示例
- **THEN** 文档 MUST 分别展示 type 1/model-1 与 type 2/model-2、type 4/model-4 与 type 5/model-5 的路由和返回字段差异

### Requirement: model-5 真实 RF 请求示例

模型调用文档 MUST 展示 `organic-matter-improvement`（公开 model-5）的请求示例，包含 `area_code`、`land_type`、规范或外部土壤字段，并说明 `model_version`、`dose_confidence`、`simulated` 与降级状态。model-6 示例 MUST 明确为 `placeholder` 占位能力，不得描述为肥力 RF。

#### Scenario: model-5 示例可执行
- **WHEN** 调用者按文档提交 model-5 请求
- **THEN** 请求 SHALL 能触发真实 RF/ETR 结果，或返回明确标注的 fallback

### Requirement: 县域诊断安全响应与迁移文档

系统 MUST 在县域诊断 API 文档中说明模板建议、真实定量结果和错误响应的差异，并展示旧 `period`、`improve`、`effect`、`cost` 和问题 `percent` 字段从固定占位值迁移为可空字段的方式。

#### Scenario: 文档展示定量不可用响应

- **WHEN** 开发者查看县域诊断模板回退示例
- **THEN** 文档 MUST 展示 HTTP 200、`status=degraded`、`result_kind=advisory_only` 和定量字段 `null`
- **AND** MUST 展示字段级不可用原因和 `predictive=false`
- **AND** 示例 MUST NOT 包含固定治理周期、提升率、效果、成本或占比

#### Scenario: 文档展示真实定量结果要求

- **WHEN** 开发者查看非空定量字段示例
- **THEN** 文档 MUST 同时展示单位、数据来源、计算方法、计算时间、适用范围以及适用时的模型版本

#### Scenario: 文档说明旧客户端迁移

- **WHEN** 开发者查看县域诊断兼容性说明
- **THEN** 文档 MUST 指引客户端处理 `null`、`degraded` 和空重点区域列表
- **AND** MUST 指引客户端显示“暂无可靠估计”而不是回填本地默认数字

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

### Requirement: Chat Analysis Context API Documentation

OpenAPI 文档 SHALL 说明聊天接口的 `analysis_context`、`calculation_mode`、`interaction_state` 和 `provenance` 契约，并提供对象设置、继承、清空、情景试算、对象不足、版本冲突、对象无效和验证服务不可用示例。

#### Scenario: 文档展示对象设置请求

- **WHEN** 开发者查看 `POST /api/v1/chat/` 请求 schema
- **THEN** 文档 SHALL 展示 `action=set`、`expected_version` 和 `{type, id}` 对象示例

#### Scenario: 文档展示对象不足响应

- **WHEN** 开发者查看地块级问题缺少对象的响应
- **THEN** 文档 SHALL 展示 HTTP 200、`needs_analysis_object` 和 `required_object_types`
- **AND** 示例 SHALL NOT 包含任何模拟专业数值

#### Scenario: 文档标记旧字段弃用

- **WHEN** 开发者查看 `parcel_id`、`parcel_code`、`area_code`
- **THEN** 文档 SHALL 标记其为过渡期兼容字段
- **AND** SHALL 指引新客户端使用 `analysis_context.object`
