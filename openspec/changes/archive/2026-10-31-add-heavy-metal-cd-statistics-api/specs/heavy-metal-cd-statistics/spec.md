# heavy-metal-cd-statistics Specification (Delta)

## ADDED Requirements

### Requirement: 基础统计口径

系统 SHALL 为 Cd 预测结果提供基础统计，固定包含数据点总数、均值、中位数、标准差、最小值、最大值、25% 分位数、75% 分位数共 8 项，数值 MUST 保留 6 位小数。标准差 MUST 为总体标准差（除以 n），25%/75% 分位数 MUST 按排序后下标 `int(count * q)` 直取，不得改为线性插值。响应 MUST 声明所用算法，使调用方能判断其与标准分位数的差异。

#### Scenario: 统计全部作物 Cd 结果

- **WHEN** 调用方请求作物 Cd 统计且结果表有数据
- **THEN** 系统 MUST 返回 8 项基础统计及数据点总数
- **AND** 系统 MUST 在响应中声明标准差为总体标准差、分位数为下标直取

#### Scenario: 结果表为空

- **WHEN** 所请求范围内没有任何预测结果
- **THEN** 系统 MUST 返回成功响应并标记 `has_data=false`
- **AND** 基础统计字段 MUST 为空值而不是 0
- **AND** 系统 MUST NOT 用 404 表示"暂无数据"

#### Scenario: 传入区域过滤

- **WHEN** 调用方指定 `area_code`
- **THEN** 系统 MUST 只统计该区域内地块的结果（通过地块主表的区域字段过滤）
- **AND** 系统 MUST NOT 返回未经过滤的全量统计

### Requirement: 作物 Cd 分布分箱

系统 SHALL 为作物 Cd 提供三档分布统计：`0.0 ~ 0.2`（安全区间）、`0.2 ~ 0.3`（预警区间）、`≥ 0.3`（超标区间），并给出各档数量与百分比（保留 2 位小数）。负值 MUST 计入超标区间，同时 MUST 单独返回无效值计数。响应 MUST 明确该分箱仅为分布描述，不构成安全或超标判定。有效态 Cd MUST NOT 提供任何分箱。

#### Scenario: 作物 Cd 三档统计

- **WHEN** 调用方请求作物 Cd 统计
- **THEN** 系统 MUST 返回三档的数量与占比
- **AND** 系统 MUST 返回 `statistics_scope` 标明这是作物 Cd 分布统计
- **AND** 系统 MUST 返回不含安全判定含义的说明

#### Scenario: 存在负值预测

- **WHEN** 结果中存在负值
- **THEN** 系统 MUST 将其计入超标区间
- **AND** 系统 MUST 在 `invalid_count` 中单独计数

#### Scenario: 请求有效态分箱

- **WHEN** 调用方请求有效态 Cd 的分布分箱
- **THEN** 系统 MUST 不提供该分箱
- **AND** 系统 MUST 只返回 8 项基础统计

### Requirement: 双模型综合统计

系统 SHALL 提供综合统计，包含两模型各自的数据可用标志、数据点数量对比与均值对比。任一侧无数据时 MUST 仍返回另一侧统计，并 MUST 明确标记缺失侧。

#### Scenario: 两侧都有数据

- **WHEN** 作物 Cd 与有效态 Cd 都有结果
- **THEN** 系统 MUST 返回两侧统计与对比项
- **AND** 系统 MUST 标记数据完整

#### Scenario: 只有一侧有数据

- **WHEN** 只有一种模型有结果
- **THEN** 系统 MUST 返回该侧统计
- **AND** 系统 MUST 标记另一侧数据缺失

### Requirement: 明细查询与 CSV 导出

系统 SHALL 支持按模型、区域、分页查询结果明细，并支持导出 CSV。明细 MUST 返回地块编号、样点编号、自然对数值、还原后的 mg/kg 值、单位与单位核验状态。CSV MUST 以 UTF-8 BOM 编码，列顺序 MUST 固定，超过单次导出上限 MUST 拒绝并给出明确错误。系统 MUST NOT 在导出中省略单位核验状态。

#### Scenario: 分页查询明细

- **WHEN** 调用方指定模型与分页参数
- **THEN** 系统 MUST 按地块与样点排序返回该页明细
- **AND** 系统 MUST 返回每个条目的还原值与 `unit_status`

#### Scenario: 导出 CSV

- **WHEN** 调用方请求 CSV 导出
- **THEN** 系统 MUST 返回 UTF-8 BOM 编码的 CSV 附件
- **AND** 列顺序 MUST 为地块编号、样点编号、自然对数值、还原值、单位、单位核验状态

#### Scenario: 导出超过上限

- **WHEN** 请求导出的行数超过单次上限
- **THEN** 系统 MUST 拒绝该请求并返回明确错误
- **AND** 系统 MUST NOT 返回被静默截断的文件

### Requirement: 模型契约查询与接口认证

系统 SHALL 提供模型清单与输入契约查询，返回两个模型的标识、完整有序输入字段、特殊输入字段、单位、单位依据与核验状态。所有 Cd 统计与查询接口 MUST 要求认证。

#### Scenario: 查询模型契约

- **WHEN** 已认证调用方请求模型清单
- **THEN** 系统 MUST 返回两个模型的有序输入字段与单位依据
- **AND** 系统 MUST 保留单位核验状态为 `unverified`

#### Scenario: 未认证访问

- **WHEN** 未携带有效凭据访问任一 Cd 统计或查询接口
- **THEN** 系统 MUST 拒绝该请求
- **AND** 系统 MUST NOT 返回任何统计或明细数据
