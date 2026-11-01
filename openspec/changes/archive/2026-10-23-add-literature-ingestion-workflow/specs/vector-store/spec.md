# vector-store Specification (Delta)

## ADDED Requirements

### Requirement: Literature Chunk Metadata

每个文献 chunk SHALL 继承稳定、可过滤且不含敏感服务器信息的文档元数据：document_id、document_kind、title、language、规范化 DOI、规范化标准号、authority_status、source_category、owner_id、visibility_scope、管理员确认的领域标签、chunk_index 和 page。所有已发布文献 chunk 的 `visibility_scope` MUST 为 `public`。

#### Scenario: Academic paper chunks preserve citation metadata
- **WHEN** 学术论文完成分块并写入向量库
- **THEN** 每个 chunk SHALL 携带相同 DOI、标题和文档类型
- **AND** page 和 chunk_index SHALL 对应该 chunk 的实际来源位置

#### Scenario: Standard chunks preserve authority status
- **WHEN** 未核验标准写入向量库
- **THEN** 每个 chunk SHALL 携带 `authority_status=unverified`
- **AND** 检索层 SHALL 能过滤或展示该状态

#### Scenario: Approved user paper is publicly searchable
- **WHEN** 用户上传论文已由管理员批准且完成索引
- **THEN** 所有 chunk SHALL 携带 `visibility_scope=public`
- **AND** 检索授权 SHALL NOT 依赖上传者身份

### Requirement: Atomic Document Publication

文档经管理员批准、全部预期 chunk 成功写入且公共权限元数据一致后才可标记 completed 和进入检索。部分写入失败时 SHALL 清理该 attempt 的 chunk。

#### Scenario: Partial vector write
- **WHEN** 预计写入 20 个 chunk 但实际只成功 15 个
- **THEN** 文档 SHALL NOT 标记 completed
- **AND** 系统 SHALL 清理该 attempt 已写入的 15 个 chunk
- **AND** item SHALL 进入 failed 或 retryable

### Requirement: Idempotent Reindexing

重试或重新入库 SHALL 使用确定性 chunk 身份或先删除旧 attempt，使同一逻辑文档不会产生重复 chunk。

#### Scenario: Retry after indexing timeout
- **WHEN** 首次索引响应超时且重试发生
- **THEN** 最终 collection SHALL 只包含一组规范 chunk
- **AND** BM25 与向量索引 SHALL 保持一致

### Requirement: Source Category Does Not Grant Access

系统 MUST 将 `source_category` 和 `cross_categories` 仅用于来源组织和过滤，且 MUST NOT 用其替代批准领域标签或 visibility 权限。

#### Scenario: Source folder has unmapped category
- **WHEN** 文档只有来源类别而没有批准一级领域
- **THEN** 系统 SHALL NOT 将其发布到可检索集合
- **AND** SHALL NOT 根据来源目录名称生成访问授权
