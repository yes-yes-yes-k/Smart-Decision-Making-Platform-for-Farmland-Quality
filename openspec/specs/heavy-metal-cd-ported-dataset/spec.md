# heavy-metal-cd-ported-dataset Specification

## Purpose
TBD - created by archiving change import-cd-ported-dataset. Update Purpose after archive.
## Requirements
### Requirement: 移植数据集的命名空间隔离

系统 SHALL 支持把外部 Cd 数据集（原系统土壤库）导入本系统，并 MUST 通过地块编号前缀与自有地块数据严格隔离。移植地块的编号 MUST 统一带固定前缀，自有地块编号 MUST NOT 被覆盖或修改。任一统计或明细响应 MUST 能让调用方区分数据来源。

#### Scenario: 导入移植数据

- **WHEN** 执行导入并成功写入结果
- **THEN** 所有移植记录的地块编号 MUST 带统一前缀
- **AND** 自有地块的记录 MUST 保持不变

#### Scenario: 查询时区分来源

- **WHEN** 调用方查询统计或明细
- **THEN** 系统 MUST 支持按数据来源过滤（自有 / 移植 / 全部）
- **AND** 响应 MUST 返回两侧各自的样本数

### Requirement: 移植地块的乡镇归属

系统 SHALL 为每个移植地块确定所属乡镇，并 MUST 使用区域目录中的乡镇边界做点面判断。若点位不落在任何乡镇边界内，系统 MUST 按最近乡镇归属并 MUST 记录该点到边界的距离。归属结果 MUST 独立存储，MUST NOT 写入按面积计算的地块-区域面积表。

#### Scenario: 点在乡镇边界内

- **WHEN** 移植点落在某乡镇多边形内
- **THEN** 系统 MUST 记录该乡镇与国家行政区标识
- **AND** 距离 MUST 记录为 0

#### Scenario: 点落在边界缝隙

- **WHEN** 移植点不落在任何乡镇多边形内
- **THEN** 系统 MUST 归属最近的乡镇
- **AND** 系统 MUST 记录该点到该乡镇边界的距离

#### Scenario: 不得污染面积归属表

- **WHEN** 写入移植地块的乡镇归属
- **THEN** 系统 MUST NOT 向按面积计算的地块-区域归属表写入零面积记录

### Requirement: 导入的回归验收

系统 SHALL 在导入完成后与源系统的输出做回归比对，未达标时 MUST 判定导入失败并给出差异分布。比对口径 MUST 考虑源系统有效态输出列实际存储的是浓度值而非对数值这一已核实事实。

#### Scenario: 比对通过

- **WHEN** 导入后执行回归比对且差异在容差内
- **THEN** 系统 SHALL 判定导入成功
- **AND** 系统 MUST 报告参与比对的样本数与最大差异

#### Scenario: 比对不通过

- **WHEN** 差异超出容差
- **THEN** 系统 MUST 判定导入失败并返回非零状态
- **AND** 系统 MUST 输出差异分布以便定位

