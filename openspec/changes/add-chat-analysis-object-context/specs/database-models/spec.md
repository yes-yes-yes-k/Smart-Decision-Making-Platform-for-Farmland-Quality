# database-models Specification (Delta)

## ADDED Requirements

### Requirement: 会话当前分析对象持久化

`Conversation` SHALL 保存 `analysis_object` JSON、`context_version` 和 `analysis_object_updated_at`。`analysis_object` 可空；`context_version` SHALL 默认为 0，并在对象设置、切换或清空成功时递增。

#### Scenario: 新会话默认无分析对象

- **WHEN** 系统创建新会话
- **THEN** `analysis_object` SHALL 为 null
- **AND** `context_version` SHALL 为 0

#### Scenario: 成功切换对象后持久化

- **WHEN** `AnalysisContextService` 成功验证并切换对象
- **THEN** Conversation SHALL 原子写入规范对象、更新时间并递增上下文版本

### Requirement: 消息分析上下文快照

`Message` SHALL 提供 `analysis_context_snapshot` JSON 字段，保存消息生成时的计算模式、规范对象和上下文版本。历史消息序列化 SHALL 返回该快照，不得使用会话当前对象替换历史快照。

#### Scenario: 切换对象后查看旧消息

- **WHEN** 一条消息在地块 P001 上生成，随后会话切换到地块 P002
- **THEN** 旧消息的 `analysis_context_snapshot` SHALL 继续指向 P001

#### Scenario: 对象不足提示保存快照

- **WHEN** 系统生成 `needs_analysis_object` 助手提示
- **THEN** 用户消息和助手提示 SHALL 保存当时的空对象或不足尺度对象快照
