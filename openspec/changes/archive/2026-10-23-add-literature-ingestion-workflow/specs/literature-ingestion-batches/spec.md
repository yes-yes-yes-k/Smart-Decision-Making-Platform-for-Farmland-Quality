# literature-ingestion-batches Specification

## Purpose

提供管理员清单驱动、可预检、可恢复、可审计的批量文献入库能力，并与用户单文件上传复用统一入库处理核心。

## ADDED Requirements

### Requirement: Versioned Literature Manifest

系统 SHALL 接受带 schema version 的文献批次清单。每项 SHALL 包含稳定 item key、相对源路径、文档类型、来源分类、领域映射和可用书目元数据；文件哈希必须由服务端计算并可与清单声明值核对。

#### Scenario: Valid manifest item
- **WHEN** 管理员预检一个字段完整且源文件存在的 manifest item
- **THEN** 系统 SHALL 将其标记为 ready
- **AND** SHALL 输出服务端计算的 SHA-256、识别文件类型和预计处理路径

#### Scenario: Manifest path escapes source root
- **WHEN** item 使用绝对路径、`..` 或解析后落在已批准 source root 之外
- **THEN** 预检 SHALL 拒绝该 item
- **AND** SHALL NOT 读取边界外文件

### Requirement: Read-only Dry Run

系统 SHALL 在正式执行前提供 dry-run，完成文件、元数据、重复、处理器、分类映射和预计工作量校验。dry-run SHALL NOT 写入文档表、向量库或永久派生文件。

#### Scenario: Dry-run corpus successfully
- **WHEN** 管理员对批次执行 dry-run
- **THEN** 系统 SHALL 返回 ready、duplicate、needs_review、invalid 和 processor_unavailable 数量
- **AND** SHALL 按文件类型汇总直接解析、OCR 和 CAJ 转换数量

#### Scenario: Dry-run finds unresolved domain mapping
- **WHEN** 来源分类没有显式映射到支持的一级领域
- **THEN** item SHALL 标记为 needs_review 或 invalid
- **AND** 系统 SHALL NOT 从目录名自动批准领域标签

### Requirement: Safe Archive Expansion

管理员批次处理 ZIP 时 SHALL 在隔离暂存区验证并展开档案，限制条目数量、单项大小、总解压大小、压缩比、路径、符号链接和文件类型。普通用户上传接口 SHALL NOT 接受 ZIP。

#### Scenario: Legacy Chinese filename archive
- **WHEN** ZIP 条目名不是有效 UTF-8 且可按 CP936/GBK 恢复
- **THEN** 系统 SHALL 使用确定性规则恢复名称
- **AND** SHALL 在 provenance 中保存原始条目名和规范化名称

#### Scenario: Archive traversal attempt
- **WHEN** ZIP 条目包含绝对路径、`..`、设备路径或符号链接逃逸
- **THEN** 整个档案 SHALL 被拒绝
- **AND** 系统 SHALL NOT 在暂存根之外创建文件

### Requirement: Hierarchical Deduplication

批次预检和执行 SHALL 依次使用 SHA-256、规范化 DOI、规范化标准号与发布机构识别确定重复，并使用规范化标题、年份和第一作者产生近似重复候选。

#### Scenario: Exact content duplicate
- **WHEN** item SHA-256 与管理员可见的现有文档或同批已接受 item 相同
- **THEN** item SHALL 标记为 skipped_duplicate
- **AND** SHALL 记录规范文档 ID 和重复原因

#### Scenario: Similar title is not automatically deleted
- **WHEN** 两项只有规范化标题相似但没有确定标识匹配
- **THEN** 系统 SHALL 标记为 needs_review
- **AND** SHALL NOT 自动删除或合并任一项

### Requirement: Idempotent and Resumable Batch Execution

每个批次和 item SHALL 有稳定幂等键。相同 manifest hash 和 batch key 的重复执行不得创建重复文档或 chunk。服务重启后 SHALL 能从持久化阶段恢复未完成项目。

#### Scenario: Resume interrupted batch
- **WHEN** 批次在部分 item 完成后因服务停止而中断
- **THEN** 恢复执行 SHALL 跳过 completed/skipped 项
- **AND** SHALL 从安全阶段继续 pending/failed-retryable 项

#### Scenario: Re-submit changed manifest with same batch key
- **WHEN** 相同 batch key 对应不同 manifest hash
- **THEN** 系统 SHALL 返回冲突
- **AND** SHALL 要求新 batch key 或显式新版本

### Requirement: Per-item Failure Isolation

一个 item 的校验、转换、解析、OCR 或索引失败 SHALL NOT 中止其他独立 item。系统 SHALL 保存阶段、失败码、脱敏信息和 retryable。

#### Scenario: One CAJ conversion fails
- **WHEN** 批次中一个 CAJ 转换失败而其他项目有效
- **THEN** 失败 item SHALL 进入 failed
- **AND** 其他 item SHALL 继续处理
- **AND** 批次最终状态 SHALL 表达 partial_success 或 failed，而非错误报告全部成功

### Requirement: Batch Progress and Report

系统 SHALL 提供批次总数、各状态计数、当前阶段、开始/完成时间和质量汇总。终态计数之和 SHALL 等于总 item 数。

#### Scenario: Batch completes with skipped duplicates
- **WHEN** 批次完成且包含 completed、skipped_duplicate 和 needs_review
- **THEN** 报告 SHALL 分别列出各状态数量和原因
- **AND** completed + failed + skipped + review + cancelled SHALL 等于 total

### Requirement: Controlled Batch Administration

批次创建、执行、重试和取消 SHALL 仅允许管理员或离线受信运维命令。API SHALL 引用已注册 staging artifact，不得接受任意宿主机路径。

#### Scenario: Regular user attempts batch creation
- **WHEN** 非管理员调用批次创建接口
- **THEN** 系统 SHALL 返回 403
- **AND** SHALL NOT 暴露 staging root 或批次内部路径

### Requirement: Public Publication of Approved Batch Literature

管理员执行批次前 MUST 通过 manifest 或审核结果确认每项至少一个有效领域标签。批次中成功完成索引的文献 MUST 发布到公共知识库；needs_review、failed、cancelled 或未确认标签的项目 MUST NOT 发布。

#### Scenario: Administrator executes an approved manifest
- **WHEN** 管理员执行已通过 dry-run 且领域映射已确认的批次
- **THEN** 成功完成的文档 SHALL 保存 `visibility_scope=public`
- **AND** 对应 chunk SHALL 对所有用户可检索

#### Scenario: Batch item still needs label review
- **WHEN** item 没有管理员确认的有效领域标签
- **THEN** item SHALL 保持 needs_review
- **AND** SHALL NOT 进入解析、索引或公共知识库
