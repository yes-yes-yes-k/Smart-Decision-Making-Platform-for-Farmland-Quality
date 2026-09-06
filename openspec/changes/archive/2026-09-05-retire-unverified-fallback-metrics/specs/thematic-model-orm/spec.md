## ADDED Requirements

### Requirement: Model-5 规则降级历史记录不得作为有效定量结果

系统 MUST 通过 `organic_matter_result.execution_id` 与 `model_execution_log` 的来源、状态、模拟标记和模型版本识别 Model-5 历史记录。规则降级、模拟、来源不明或无法关联执行依据的记录 MUST 标记为不可信历史数据，并禁止用于 API、聊天、报告和后续模型输入。

#### Scenario: 读取真实 Model-5 历史结果

- **WHEN** 结果关联的执行日志满足 `simulated=false`、模型版本非空、来源为实际 ML/RF 且执行成功
- **THEN** 系统 MAY 将实际模型产生的施用量作为有效历史结果读取
- **AND** 系统 SHALL 保留对应模型版本与数据来源

#### Scenario: 读取规则降级或模拟记录

- **WHEN** 结果或执行日志标记 `simulated=true`、状态为降级/回退、来源为 `rule_fallback`/`fallback`/`unknown`，或结果无法关联到可验证执行日志
- **THEN** 系统 MUST NOT 将其中的 `organic_fertilizer_dosage`、`potential_increase` 或兼容定量字段作为有效结果
- **AND** 报告查询 SHALL 返回定量结果不可用，而不是“已落库”

### Requirement: Model-5 不可信历史数据可审计废弃

系统 MUST 提供默认 dry-run、显式 apply、可重复执行的迁移工具，对生产 Model-5 不可信历史记录进行盘点、备份、隔离和清理。迁移 MUST 基于执行来源识别记录，禁止仅根据数值是否符合旧公式进行删除。

#### Scenario: dry-run 盘点历史记录

- **WHEN** 运维人员对生产数据库执行迁移工具但未指定 `--apply`
- **THEN** 工具 SHALL 输出待废弃记录数量、识别原因分布、来源不明数量和备份计划
- **AND** 工具 MUST NOT 修改数据库

#### Scenario: apply 废弃历史规则数值

- **WHEN** 运维人员确认 dry-run 并使用 `--apply`
- **THEN** 工具 MUST 先生成可校验备份
- **AND** SHALL 清空活动结果表及活动执行输出中的规则施用量和提升量
- **AND** SHALL 保留执行日志的基本审计事实和迁移摘要
- **AND** 真实 ML/RF 记录 MUST 保持不变

#### Scenario: 重复执行迁移

- **WHEN** 同一迁移对已经处理的数据库再次执行
- **THEN** 工具 SHALL 成功完成且不重复破坏或误分类记录
- **AND** 审计摘要 SHALL 表明没有新的待废弃活动值
