## ADDED Requirements

### Requirement: 旧酸化 SQLite 结果表停止作为活动数据源

系统 MUST 废弃旧 SQLite `acidification_results` 表及其 `expected_effect` 内容。新数据库禁止创建该表，运行时代码禁止向该表写入、从该表读取或把其中任何字段转换为当前酸化模型结果。`evaluation_results` 和 `diagnosis_results` 等仍被正式流程使用的表不受此废弃影响。

#### Scenario: 初始化新的诊断 SQLite

- **WHEN** `DiagnosisStorage` 初始化新的 SQLite 数据库
- **THEN** 系统 MUST NOT 创建 `acidification_results` 表
- **AND** 其他仍在使用的评价和障碍诊断表 SHALL 正常创建

#### Scenario: 兼容调用旧保存或读取方法

- **WHEN** 旧调用方调用 `save_acidification()` 或 `get_acidification()`
- **THEN** 系统 SHALL 返回或抛出明确的 deprecated/unavailable 结果
- **AND** 系统 MUST NOT 访问旧 `acidification_results` 表
- **AND** 系统 MUST NOT 返回 `expected_effect`

#### Scenario: 当前酸化按需计算

- **WHEN** 当前酸化入口基于地块或显式指标执行计算
- **THEN** 系统 SHALL 使用正式 Python 过程模型和可验证输入生成结果
- **AND** 系统 MUST NOT 回退读取旧 SQLite 酸化结果表

### Requirement: 生产旧酸化结果可备份废弃

系统 MUST 提供生产迁移能力，对明确配置的旧 SQLite 数据库进行 dry-run 盘点，在可校验备份完成后归档并删除 `acidification_results` 表。历史 `expected_effect` 只能存在于受限迁移备份中，不得继续作为应用数据源。

#### Scenario: dry-run 发现旧结果表

- **WHEN** 运维人员对指定 SQLite 执行迁移 dry-run，且数据库包含 `acidification_results`
- **THEN** 工具 SHALL 报告表结构、记录数量、非空 `expected_effect` 数量和计划备份位置
- **AND** 工具 MUST NOT 修改数据库

#### Scenario: apply 归档并删除旧结果表

- **WHEN** 运维人员显式使用 `--apply` 且备份创建与 SHA-256 校验成功
- **THEN** 工具 SHALL 在受控事务中从活动 SQLite 删除 `acidification_results` 表
- **AND** SHALL 生成包含数据库标识、处理数量、备份校验值、时间和结果状态的 JSON 审计摘要
- **AND** 其他业务表和记录 MUST 保持不变

#### Scenario: 备份或 Schema 校验失败

- **WHEN** 备份失败、SQLite Schema 不符合预期或目标路径不在显式配置范围内
- **THEN** 迁移 MUST 中止且不得删除任何表或记录
- **AND** 工具 SHALL 返回机器可读错误和人工处理建议

#### Scenario: 迁移后运行验证

- **WHEN** 生产迁移完成
- **THEN** 活动数据库 MUST 不再包含 `acidification_results` 表
- **AND** 当前酸化计算与障碍诊断流程 SHALL 继续通过验证
- **AND** API、报告和内部查询 MUST 不再出现 `expected_effect`
