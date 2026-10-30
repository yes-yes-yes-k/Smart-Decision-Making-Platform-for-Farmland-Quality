# add-literature-ingestion-workflow Design

## Context

当前单文件链路为：上传文件 → 保存 UUID 文件名 → 用户范围 SHA-256 查重 → 创建 `kb_document` → 后台线程解析 → 分块 → 向量化。状态只有 pending、processing、completed、failed；失败详情仅打印 traceback。文档及 chunk 元数据不足以保存 DOI、标准号、来源、权威状态、转换产物和解析质量。

首次目标资料具有以下约束：

- 英文论文主库的 TXT/RIS 与 422 个 PDF 可一一对应，清单 SHA-256 已验证一致。
- 标准库有 477 个 PDF，扫描件比例明显高于英文论文。
- 补充资料缺少统一书目清单，必须从文件名、指南和首页生成候选元数据。
- ZIP 内含 121 个 PDF 和 86 个 CAJ；旧 ZIP 中文文件名可能需要 CP936/GBK 解码。
- 当前 HTML 索引的本地 PDF 链接因重复目录层级全部失效，不能作为权威定位源。
- 来源采用九类专题，而系统目前只有三个一级领域；来源分类与系统领域必须分开保存。

## Goals / Non-Goals

### Goals

- 为千份级文献提供可预检、可恢复、可审计的批量入库。
- 让未来用户上传论文获得明确的校验、异步进度、失败原因和重试体验。
- 使单文件和批次入库复用同一校验、解析、去重、索引与权限逻辑。
- 保存书目、标准、来源、转换、OCR 和权限溯源。
- 通过管理员审核将所有获批文献安全发布到公共知识库，并在审核前保护提交内容。
- 保持现有接口和 `kb_document.status` 数值语义兼容。

### Non-Goals

- 不在本 change 中导入外部目录。
- 不自动判断版权或标准有效性；文献审核通过后公开是系统既定策略。
- 不允许公共 API 接收任意服务器绝对路径。
- 不通过本 change 重构检索算法。
- 不让普通用户上传 ZIP、批量清单或指定现有服务器文件。

## Architecture

```text
用户单文件上传 ─┐
                 ├─> Intake Validation ─> Document + Ingestion Item
管理员批次清单 ─┘             │
                               v
      validate -> admin review -> convert -> parse/OCR -> clean -> chunk -> index -> finalize
                               │
                               ├─> stage/progress/error
                               └─> immutable provenance + quality metadata
```

所有入口调用统一 `DocumentIngestionService` 或等价应用服务。路由不得分别实现去重、解析和索引规则。

## Decisions

### 1. 接收与处理分离

文件接收成功只表示原始文件和任务记录已持久化，不表示已经可检索。接口返回 HTTP 202；客户端通过状态接口查看 `stage`、`progress` 和失败详情。

保留现有 `kb_document.status`：

| status | 含义 |
|---:|---|
| 0 | pending |
| 1 | completed |
| 2 | processing |
| 3 | failed |
| 4 | rejected |

新增可读处理阶段：`accepted`、`validating`、`awaiting_admin_review`、`converting`、`parsing`、`ocr`、`chunking`、`indexing`、`completed`、`failed`、`rejected`、`skipped_duplicate`。新增 `status=4` 表示管理员驳回，原有 0 至 3 的数值语义保持不变。

### 2. 用户上传接口向后兼容扩展

保留 `POST /api/v1/docs/upload` 和现有 multipart 字段。新增可选字段：

- `document_kind`: `academic_paper|standard|policy|method_guideline|other`
- `title`
- `authors`: JSON 字符串数组
- `doi`
- `journal`
- `publication_date`: ISO 8601 日期
- `standard_number`
- `issuing_authority`
- `source_url`
- `source_category`
- `cross_categories`: JSON 字符串数组
- `language`
- `idempotency_key`

兼容规则：旧请求不传新增字段时，按 `document_kind=other` 处理；现有 `category`、`treatment_type`、`visibility_scope` 和 `domain_labels` 继续接受。

用户上传文献时必须选择至少一个有效 `domain_labels`，系统不提供自动分类或候选标签生成。`visibility_scope` 不再由文献上传者决定：省略该字段或提交 `public` 均表示审核通过后的目标可见性为 public；显式提交 `private` 时返回 HTTP 422 和 `visibility_not_configurable`，避免客户端误认为文献会被私有保存。提交在审核期仅上传者和管理员可见，审核通过并完成索引后强制设置为 `public`。普通用户不得上传 ZIP，也不得提交本地路径。

若请求未提供有效 `domain_labels`，接口返回 HTTP 422 和 `domain_label_required`，不得创建提交或触发解析。通过接收校验的文档停在 `awaiting_admin_review`；只有管理员可以确认或修正标签并批准。批准后才启动转换、解析、OCR、分块和索引；驳回后进入 `rejected` 终态且不得进入可检索集合。

### 3. API 响应和错误契约

成功接收返回 HTTP 202：

```json
{
  "status": "ok",
  "data": {
    "document": {"id": 123, "status": 0},
    "ingestion": {
      "state": "pending",
      "stage": "accepted",
      "progress": 0,
      "status_url": "/api/v1/docs/123/ingestion"
    }
  }
}
```

错误使用稳定 `error_code`：

- `unsupported_file_type` → 415
- `file_too_large` → 413
- `content_type_mismatch` → 422
- `encrypted_document` → 422
- `invalid_metadata` → 422
- `domain_label_required` → 422
- `visibility_not_configurable` → 422
- `duplicate_document` → 409
- `review_already_finalized` → 409
- `processor_unavailable` → 503
- `queue_capacity_exceeded` → 429 或 503
- `ingestion_failed` → 状态接口中的终态错误

与已发布公共文献重复时可返回已有公共 `document_id`。与另一用户尚未审核的提交重复时，不得返回该用户的文件名、提交者或私有审核信息；系统可合并底层 blob，但必须保留独立提交与审核审计。

### 4. 用户状态、重试与管理员审核

新增：

- `GET /api/v1/docs/<id>/ingestion`：所有者或管理员查看阶段、进度、质量摘要和脱敏错误。
- `POST /api/v1/docs/<id>/retry`：仅失败且 `retryable=true` 的文档可重试。
- `GET /api/v1/docs/reviews?state=pending`：管理员查看待审核文献队列。
- `POST /api/v1/docs/<id>/review`：管理员提交 `approve|reject` 决策、确认后的领域标签及可选审核意见。

重试创建新的 ingestion attempt，但复用原文档和原始文件；旧 attempt 保留审计记录。已完成文档不得通过 retry 重复写入向量库。

普通用户不能自审。批准操作必须确认至少一个有效领域标签并记录审核人和时间，然后才将任务送入处理队列。驳回必须记录可供上传者查看的原因；驳回文档不得解析、向量化或公开。审核接口须幂等：同一决策重放返回原结果，相反决策必须返回 409 并要求使用独立的重新审核流程。

### 5. 管理员批次入口采用清单驱动

首次大批资料不通过公共单文件 HTTP 循环上传。提供运维 CLI 和管理员批次服务：

```text
python scripts/import_literature_batch.py \
  --source-root <staging-root> \
  --manifest <manifest.jsonl> \
  --dry-run
```

批次清单只允许相对于已批准 `source_root` 的路径。规范化后的路径必须仍位于该根目录。公共 API 不接受任意绝对路径。

管理员 API 负责创建/查询/重试/取消批次，不直接暴露宿主机路径：

- `POST /api/v1/docs/batches`
- `GET /api/v1/docs/batches/<batch_id>`
- `POST /api/v1/docs/batches/<batch_id>/retry`
- `POST /api/v1/docs/batches/<batch_id>/cancel`

批次创建可以引用由运维预先注册的 staging token 和 manifest artifact；未经注册的路径或 artifact 必须拒绝。

### 6. 批次预检先于任何数据库/向量写入

`dry-run` SHALL 完成：

- 文件存在性、扩展名和文件签名校验；
- 清单字段、相对路径和 SHA-256 校验；
- ZIP 路径穿越、条目数、单项大小、总解压大小和压缩比校验；
- ZIP 文件名 UTF-8/CP936 解码探测；
- 临时锁文件和控制文件排除；
- DOI、标准号、标题和哈希重复报告；
- CAJ 转换器、Poppler、Tesseract 及 `chi_sim` 健康检查；
- 来源分类到领域标签映射完整性检查；
- 预计直接解析、OCR、CAJ 转换和人工审核数量。

dry-run 不得创建文档记录、向量、派生 PDF 或永久解压目录。

### 7. 去重分层且作用域不同

去重键依优先级：

1. 原始内容 SHA-256；
2. 规范化 DOI；
3. 规范化标准号 + 发布机构；
4. 规范化标题 + 年份 + 第一作者的候选近似重复。

批次导入在管理员可见范围内执行全局去重。近似重复只标记 `needs_review`，不得自动删除。用户提交在审核前保持逻辑隔离；即使底层复用同一 blob，也必须保留独立提交、上传者和审核记录。批准发布后，规范文档为公共资源，所有用户读取同一公共文档；上传者身份不作为检索授权条件。

`idempotency_key` 在用户和接口范围内唯一。同一 key 与相同请求重放时返回原结果；同一 key 对应不同文件哈希时返回 409。

### 8. 文献元数据采用稳定字段加扩展 JSON

高频检索/唯一字段使用关系型列：`document_kind`、`title`、`language`、`doi_normalized`、`standard_number_normalized`、`batch_id`、`processing_stage`、`failure_code`。

可变结构放入 JSON：

- `bibliographic_metadata`: 作者、期刊、日期、出版版本；
- `provenance_metadata`: 来源 URL、原始相对路径、清单来源、来源专题、交叉专题、许可说明；
- `parse_metadata`: 转换器版本、OCR 页、页数、字符数、质量评分、派生文件哈希。

API 不得信任客户端提供的哈希、页数和解析质量；这些字段由服务端计算。

### 9. 来源分类与系统领域分离

`source_category` 和 `cross_categories` 保存资料提供方的九类目录及交叉主题，不承担访问控制语义。`domain_labels` 继续使用系统当前 taxonomy：用户上传时必须明确选择，管理员审核时确认或修正；批次导入则由管理员映射文件提供。

批次预检遇到未映射来源类别时必须失败或标记为待审核，不得根据文件夹名静默授予领域标签。

### 10. CAJ 保留原件并生成派生 PDF

CAJ 原件是主文件，转换 PDF 是可重建派生文件。转换过程：

- 接收时探测转换器；普通用户上传时不可用则立即返回 `processor_unavailable`；
- 批次 dry-run 汇总不可转换项，不进入执行；
- 转换命令使用参数数组且不经过 shell；
- 限制超时、输出大小和临时目录；
- 验证输出文件头为 PDF；
- 保存原件哈希、派生 PDF 哈希、转换器及版本；
- 解析结束清理临时产物；由布尔配置 `LITERATURE_RETAIN_DERIVED_PDF` 决定是否长期保留受管派生 PDF，默认值为 `false`。

配置为 `false` 时，成功提取并记录派生哈希后删除派生 PDF；配置为 `true` 时，将派生 PDF 保存到受管存储并继承原文档访问控制。无论配置为何，原始 CAJ、转换器版本、转换时间和派生哈希均须保留。配置值须写入 ingestion 的 `config_snapshot`，确保批次可审计和可重放。

### 11. PDF 按页路由而不是整本 OCR

每页先提取文本并计算字符量。无文本或低于阈值的页进入分页 OCR；有文本页保持原文本层。OCR 每次处理有限页数，禁止将整本大型 PDF 一次性渲染到内存。

`parse_metadata` 至少记录总页数、文本层页数、OCR 页数、空页数、提取字符数和错误页。存在无法解析页时，是否完成由质量门槛决定，而不是只看任务是否抛异常。

### 12. 标准和政策默认参考级

`authority_status` 取值：`unverified`、`reference_only`、`verified_current`、`superseded`、`draft`。

批次导入标准/政策时默认 `unverified` 或根据清单显式设定 `draft`。只有管理员审核并记录核验来源、核验人和时间后，才能设为 `verified_current`。检索结果和引用必须携带该状态，不能把未核验资料描述为现行强制依据。

### 13. 向量写入采用发布式提交

一个文档的所有 chunk 生成成功后才进入最终可检索状态。写入不完整时删除该 attempt 已写入的 chunk，并保持文档 failed。重试使用确定性 chunk ID 或先清理旧 attempt，防止重复 chunk。

文档在以下条件全部满足后才 `completed`：

- 文件和元数据校验通过；
- 管理员审核通过且至少一个领域标签已确认；
- 解析质量达到门槛；
- 实际写入 chunk 数等于预期；
- 文档和所有 chunk 的权限元数据一致。

## Data Model

### `kb_ingestion_batch`

- `id`, `batch_key`, `name`, `source_type`
- `state`, `dry_run`, `requested_by`
- `manifest_hash`, `source_artifact_id`
- `total_count`, `completed_count`, `failed_count`, `skipped_count`, `review_count`
- `config_snapshot`, `summary`, `created_at`, `started_at`, `finished_at`

### `kb_ingestion_item`

- `id`, `batch_id`, `document_id`, `attempt_no`
- `source_relative_path`, `source_hash`, `idempotency_key`
- `state`, `stage`, `progress`
- `review_status`, `submitted_domain_labels`, `approved_domain_labels`
- `reviewed_by`, `reviewed_at`, `review_note`, `config_snapshot`
- `failure_code`, `failure_message`, `retryable`
- `quality_summary`, `started_at`, `finished_at`

单文件用户上传也创建一个 ingestion item，可不创建显式 batch，或归入系统生成的单项 batch；实现选择必须保证状态接口使用同一数据源。

`review_status` 取值为 `pending|approved|rejected`。用户提交保存 `submitted_domain_labels`；管理员批准时保存最终 `approved_domain_labels`，不得覆盖原始提交值。

### `kb_document` 扩展

- `document_kind`, `title`, `language`
- `doi_normalized`, `standard_number_normalized`
- `authority_status`
- `bibliographic_metadata`, `provenance_metadata`, `parse_metadata`
- `processing_stage`, `failure_code`, `failure_message`
- `review_status`, `reviewed_by`, `reviewed_at`, `review_note`
- `batch_id`

## Security and Privacy

- 上传者和管理员可查看待审核提交；其他用户不得访问待审核原件、元数据或审核信息。
- 已审核并完成索引的文献统一公开读取；上传者只能管理自己的提交记录，不能因上传行为单方面撤下公共规范文档。
- 重复检测可返回已存在的公共文档，但不得泄露其他用户的待审核提交。
- ZIP 展开必须拒绝绝对路径、`..`、设备名、符号链接和超限项。
- 文件类型校验以扩展名和 magic bytes 双重判断。
- 来源 URL 只作为元数据保存，不在入库过程中自动请求。
- 文件名、转换器输出和错误信息在返回客户端前必须脱敏，不能暴露服务器路径。
- 未完成、待审核或被驳回文档不得进入任何用户可检索 collection。

## Migration and Rollout

1. 新增数据库字段和批次/任务表；旧文档字段允许为空。
2. 抽取统一 ingestion service，保持旧上传测试通过。
3. 上线状态查询、管理员审核队列、审核接口、错误持久化和 retry。
4. 上线分页 OCR、CAJ 健康检查和派生文件溯源。
5. 实现 manifest 生成器与 dry-run；以 10 篇英文论文试运行。
6. 依次试运行英文论文、扫描标准、补充资料、ZIP PDF、CAJ，每类设置独立质量门槛。
7. 通过验收后再执行首次正式批次。

回滚时停止新任务，保留原始文件与批次审计；删除未发布的 attempt chunks。已完成文档按现有删除语义处理，不直接回滚数据库迁移。

## Risks / Trade-offs

- 批次表和阶段状态增加复杂度，但换取断点续跑、可审计和稳定用户体验。
- 全局业务去重可能产生误判，因此标题近似只做人工候选，自动跳过仅限确定键。
- OCR 提升扫描件召回，但耗时显著增加；通过逐页路由、限流和质量门槛控制。
- CAJ 转换依赖外部工具；通过接收前健康检查和原件保留降低不可控性。
- 全部获批文献统一公开会扩大误发布影响；通过强制管理员审核、审核日志和发布前权限断言降低风险。
- 未扩展一级 taxonomy 可降低本次变更范围，但九类来源必须作为独立元数据保留，后续可单独扩展标签体系。

## Resolved Decisions

- 不提供自动分类。用户上传时必须选择标签，且只有管理员可以确认或修正标签并批准入库。
- 所有审核通过并完成索引的文献均进入公共知识库；用户上传的文献同样适用。审核前提交不是公共知识。
- CAJ 派生 PDF 是否长期保留由 `LITERATURE_RETAIN_DERIVED_PDF` 配置控制，默认 `false`；原始 CAJ 和转换溯源始终保留。

