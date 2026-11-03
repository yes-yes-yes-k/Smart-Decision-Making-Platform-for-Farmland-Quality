# heavy-metal-cd-statistics Specification (Delta)

## MODIFIED Requirements

### Requirement: 基础统计口径

系统 SHALL 为 Cd 预测结果提供基础统计，固定包含数据点总数、均值、中位数、标准差、最小值、最大值、25% 分位数、75% 分位数共 8 项，数值 MUST 保留 6 位小数。标准差 MUST 为总体标准差（除以 n），25%/75% 分位数 MUST 按排序后下标 `int(count * q)` 直取，不得改为线性插值。响应 MUST 声明所用算法，使调用方能判断其与标准分位数的差异。统计 MUST 支持按数据来源过滤（自有地块 / 移植数据 / 全部），并 MUST 在响应中返回各来源的样本数。

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

#### Scenario: 按数据来源过滤

- **WHEN** 调用方指定数据来源为自有地块或移植数据
- **THEN** 系统 MUST 只统计该来源的记录
- **AND** 响应 MUST 返回 `source` 生效值与各来源样本数
- **AND** 系统 MUST NOT 把两类数据混合后不加以标注

### Requirement: 明细查询与 CSV 导出

系统 SHALL 支持按模型、区域、数据来源、分页查询结果明细，并支持导出 CSV。明细 MUST 返回地块编号、样点编号、自然对数值、还原后的 mg/kg 值、单位与单位核验状态。CSV MUST 以 UTF-8 BOM 编码，列顺序 MUST 固定，超过单次导出上限 MUST 拒绝并给出明确错误。系统 MUST NOT 在导出中省略单位核验状态，也 MUST NOT 在未指定来源时把两类数据混装而不加说明。

#### Scenario: 分页查询明细

- **WHEN** 调用方指定模型与分页参数
- **THEN** 系统 MUST 按地块与样点排序返回该页明细
- **AND** 系统 MUST 返回每个条目的还原值与 `unit_status`

#### Scenario: 按来源查询明细

- **WHEN** 调用方指定数据来源
- **THEN** 系统 MUST 只返回该来源的明细记录

#### Scenario: 导出 CSV

- **WHEN** 调用方请求 CSV 导出
- **THEN** 系统 MUST 返回 UTF-8 BOM 编码的 CSV 附件
- **AND** 列顺序 MUST 为地块编号、样点编号、自然对数值、还原值、单位、单位核验状态

#### Scenario: 导出超过上限

- **WHEN** 请求导出的行数超过单次上限
- **THEN** 系统 MUST 拒绝该请求并返回明确错误
- **AND** 系统 MUST NOT 返回被静默截断的文件
