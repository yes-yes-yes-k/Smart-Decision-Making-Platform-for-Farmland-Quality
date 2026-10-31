# heavy-metal-cd-database-backend Specification (Delta)

## ADDED Requirements

### Requirement: 数据库输入适配

系统 SHALL 支持从当前系统数据库（`parcel_info`、`third_survey_topsoils` 等）读取地块数据并转换为 Cd 双模型所需的特征集合。系统 MUST 只启用语义与单位均已确认的字段映射，未确认或无法映射的字段 MUST 进入 `missing_fields`。系统 MUST NOT 用零值、区域均值或训练集统计量补齐普通特征（`solution`/`cdsolution` 按既有降级口径除外，且必须强制 `degraded`）。系统 MUST NOT 读取本机 `soilgd` 数据库，也 MUST NOT 依赖 AcidMap 在线服务。

#### Scenario: 地块输入完整

- **WHEN** 指定地块的所有必需特征都能从已确认映射中获得
- **THEN** 系统 SHALL 返回 `ready` 状态与完整特征字典
- **AND** 系统 SHALL 为每个已填充特征返回来源标记

#### Scenario: 地块存在无法映射的特征

- **WHEN** 某地块有特征无法映射或库存值为空
- **THEN** 系统 SHALL 将该特征列入 `missing_fields` 并返回 `need_input`
- **AND** 系统 MUST NOT 填零、填区域均值或填训练集统计量
- **AND** 系统 MUST NOT 在该地块上执行预测

#### Scenario: 交换态与全量语义不得混用

- **WHEN** 库存字段是交换性钙、交换性镁、交换性钾或交换性钠
- **THEN** 系统 MUST NOT 将其映射为 `total_calcium`、`total_magnesium`、`total_potassium`
- **AND** 这些特征 MUST 保持 `missing_fields` 状态

### Requirement: Cd 预测结果地块级覆盖持久化

系统 SHALL 支持对一批地块执行 Cd 双模型预测，并将结果写入当前系统数据库。写入 MUST 按地块覆盖：同一 `parcel_id` 的既有结果行 MUST 在写入前被替换，不得累积重复行。写入 MUST 在单一事务内完成，失败 MUST 整体回滚。预检阶段若有任一地块缺少必需输入，系统 MUST 拒绝整批写入，并返回逐地块的拒绝原因。

#### Scenario: 重跑同一批次

- **WHEN** 对同一批地块连续执行两次预测
- **THEN** 结果表行数 MUST 保持不变
- **AND** `ln_*` 列 MUST 为第二次执行的值

#### Scenario: 一个地块多个样点

- **WHEN** 某 `parcel_id` 关联多个 `sample_id` 且参与预测
- **THEN** 该地块原有的全部样点结果行 MUST 被本次结果替换
- **AND** 表内 MUST NOT 残留该地块的旧样点行

#### Scenario: 批次中存在输入缺失的地块

- **WHEN** 批次内至少一个地块的必需特征缺失
- **THEN** 系统 MUST 拒绝整批写入并返回 `rejected` 明细（`parcel_id` 与 `missing_fields`）
- **AND** 结果表 MUST NOT 发生任何写入

#### Scenario: 写入过程失败

- **WHEN** 批量写入过程中发生数据库异常
- **THEN** 系统 MUST 回滚整个事务
- **AND** 结果表 MUST NOT 留下部分地块的新结果

### Requirement: 结果读取与单位还原

系统 SHALL 提供结果读取能力，返回自然对数值还原后的浓度值与原始对数值。输出单位 MUST 为 `mg/kg`，`unit_status` MUST 为 `verified`，并 MUST 返回单位依据说明。系统 MUST NOT 提供有效态 Cd 的阈值分箱、安全等级或法规结论。

#### Scenario: 读取地块预测结果

- **WHEN** 调用方请求某地块的 Cd 预测结果
- **THEN** 系统 SHALL 返回 `mg/kg` 还原值与该值的自然对数
- **AND** 系统 SHALL 返回 `unit_status=verified` 与单位依据

#### Scenario: 请求超标判定

- **WHEN** 调用方请求有效态 Cd 的超标等级或分档统计
- **THEN** 系统 MUST 明确返回该能力不在本阶段范围内
- **AND** 系统 MUST NOT 输出任何阈值判定结果

### Requirement: 结果表结构

结果表 MUST 只存储自然对数值，列结构中 MUST NOT 包含模型版本、执行标识、计算时间或批次字段。结果表 MUST 对 `(parcel_id, sample_id)` 设置唯一约束，防止重复累积。列注释 MUST 标明物理单位。

#### Scenario: 表结构核查

- **WHEN** 检查 `cd_crop_prediction_result` 与 `cd_effective_prediction_result` 的列定义
- **THEN** 两表 MUST 只包含 `id`、`parcel_id`、`sample_id` 与对应的 `ln_*` 列
- **AND** 两表 MUST 存在 `(parcel_id, sample_id)` 唯一约束
- **AND** `ln_*` 列注释 MUST 包含 `[ln(mg/kg)]`
