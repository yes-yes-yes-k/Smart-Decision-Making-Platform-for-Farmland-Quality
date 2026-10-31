# heavy-metal-cd-spatial-analysis Specification

## Purpose
TBD - created by archiving change add-heavy-metal-cd-spatial-analysis. Update Purpose after archive.
## Requirements
### Requirement: 地块与区域的唯一归属

系统 SHALL 使用既有区域目录与地块-区域面积表判定地块所属乡镇，且每个地块 MUST 只归属一个区域（取面积最大的那个）。系统 MUST NOT 通过点面包含判断决定归属，也 MUST NOT 让同一地块的结果在多个区域的统计中重复计入。系统 MUST 在响应中披露跨多个区域的地块数量，使归属规则的影响可见。

#### Scenario: 地块跨多个乡镇

- **WHEN** 某地块在面积表中与两个以上 township 相交
- **THEN** 系统 MUST 只把它归入面积最大的那个 township
- **AND** 系统 MUST NOT 在其它相交 township 的统计中计入该地块结果

#### Scenario: 披露跨区地块

- **WHEN** 调用方请求乡镇统计
- **THEN** 系统 MUST 返回跨乡镇地块数量
- **AND** 该数量 MUST 与面积表中确实跨多个 township 的地块数一致

### Requirement: 乡镇级统计

系统 SHALL 按乡镇聚合 Cd 预测结果，并复用与全域统计一致的口径（总体标准差、下标直取分位数、数值保留 6 位小数）。作物 Cd MUST 同时返回三档分布；有效态 Cd MUST NOT 返回任何分箱。系统 MUST 支持过滤样本数过少的乡镇，且 MUST 只统计有结果的乡镇。

#### Scenario: 查询作物 Cd 乡镇统计

- **WHEN** 调用方请求作物 Cd 的乡镇统计
- **THEN** 系统 MUST 返回每个有数据乡镇的样本数、8 项基础统计与三档分布
- **AND** 统计口径 MUST 与全域统计一致

#### Scenario: 查询有效态 Cd 乡镇统计

- **WHEN** 调用方请求有效态 Cd 的乡镇统计
- **THEN** 系统 MUST 返回 8 项基础统计
- **AND** 系统 MUST NOT 返回任何分布分箱

#### Scenario: 过滤小样本乡镇

- **WHEN** 调用方指定最小样本数
- **THEN** 系统 MUST 只返回样本数达到阈值的乡镇
- **AND** 被过滤掉的乡镇 MUST NOT 出现在结果列表中

### Requirement: 单区域统计

系统 SHALL 支持按区域类型与区域标识查询单个区域的 Cd 统计。区域类型 MUST 限定为区域目录中存在的类型；非法类型 MUST 被拒绝而不是返回空统计。

#### Scenario: 查询指定乡镇

- **WHEN** 调用方指定 township 与乡镇标识
- **THEN** 系统 MUST 返回该乡镇的统计与样本数

#### Scenario: 非法区域类型

- **WHEN** 调用方传入区域目录中不存在的类型
- **THEN** 系统 MUST 拒绝该请求并返回明确错误
- **AND** 系统 MUST NOT 返回空统计或全量统计

### Requirement: 点位 GeoJSON 输出

系统 SHALL 输出 Cd 结果的点位 GeoJSON，坐标为地块质心，并 MUST 在响应中声明坐标来源。Feature 属性 MUST 只包含地块编号、样点编号、还原值、自然对数值、单位与单位核验状态；系统 MUST NOT 在点位上给出等级判定或颜色建议。系统 MUST 支持按地图范围过滤与条数上限，并 MUST 返回被省略的条数。

#### Scenario: 请求点位数据

- **WHEN** 调用方请求某模型的点位 GeoJSON
- **THEN** 系统 MUST 返回 FeatureCollection
- **AND** 每个 Feature 的坐标 MUST 来自地块质心
- **AND** 响应 MUST 声明 `coordinate_source` 为地块质心

#### Scenario: 条数超过上限

- **WHEN** 命中点数超过请求上限
- **THEN** 系统 MUST 截断到上限
- **AND** 系统 MUST 在响应中返回被省略的条数

#### Scenario: 按地图范围过滤

- **WHEN** 调用方提供边界框
- **THEN** 系统 MUST 只返回落在该范围内的点位

