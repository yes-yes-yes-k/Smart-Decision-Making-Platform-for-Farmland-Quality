# cd-flux-accounting Specification

## Purpose
Cd 通量核算：完整输入行导入（CSV）、输入/输出/净通量与当年浓度计算与持久化、区域统计与四类分布、点位与地图、CSV 导出。

## Requirements

### Requirement: 输入行导入

系统 SHALL 支持把完整通量输入行导入输入表，字段 MUST 包含 `parcel_id`、`sample_id`、`initial_cd`、`DQCJ_Cd`、`GGS_Cd`、`NCP_Cd`、`DX_Cd`、`DB_Cd`、`ZL_Cd`、`JG_Cd`，`bd020_90` MAY 提供。系统 MUST 校验必需列与数值合法性， MUST 对已存在 `(parcel_id, sample_id)` 的记录覆盖更新，并 MUST 返回插入/更新/跳过计数。

#### Scenario: 导入完整输入行

- **WHEN** 调用方上传包含全部必需列的 CSV
- **THEN** 系统 MUST 写入输入表并返回 inserted/updated 计数
- **AND** 同一键重复导入 MUST 覆盖而不是累加

#### Scenario: 缺少必需列

- **WHEN** 上传的 CSV 缺少任一必需列
- **THEN** 系统 MUST 拒绝导入并返回机器可读的缺列错误
- **AND** 系统 MUST NOT 写入部分行

### Requirement: 通量计算

系统 SHALL 由输入表计算输出表：`In_Cd = DQCJ+GGS+NCP`、`Out_Cd = DX+DB+ZL+JG`、`Net_Cd = In−Out`、`End_Cd = (Initial_Cd+Net_Cd)/(2000×bd020_90)`。`bd020_90` 缺失 MUST 回退 1.0，`Initial_Cd` 缺失 MUST 回退 0，`soil_mass` 非正 MUST 输出 0；系统 MUST 在响应中披露回退计数。重算 MUST 按 `(parcel_id, sample_id)` 覆盖写， MUST NOT 重复累积。

#### Scenario: 正常计算

- **WHEN** 输入行四项输出分量与三项输入分量齐全
- **THEN** 系统 MUST 生成 In/Out/Net/End 四列
- **AND** `End_Cd` MUST 以 mg/kg 口径按 2000×bd020_90 换算

#### Scenario: 容重缺失

- **WHEN** 输入行的 `bd020_90` 为空
- **THEN** 系统 MUST 按 1.0 计算
- **AND** 响应 MUST 返回 `bd020_90` 回退计数

#### Scenario: 重复计算幂等

- **WHEN** 对同一批输入连续执行两次计算
- **THEN** 输出表行数 MUST 保持一致（唯一键覆盖）
- **AND** 系统 MUST NOT 产生重复记录

### Requirement: 通量统计与分布

系统 SHALL 按区域聚合四类字段（`in_cd/out_cd/net_cd/end_cd`），基础统计 MUST 复用阶段 2 口径（总体标准差、下标直取分位数、6 位小数）。分布 MUST 为：`end_cd` 三档 `<0.3 / 0.3–0.6 / ≥0.6 mg/kg`；`net_cd` 互斥三档 `<−5 / −5~5 / >5 g/ha/a`；`in/out` 相对本批均值三档（`<0.5×mean / 0.5–1.5×mean / ≥1.5×mean`）。分档 MUST 互斥，占比之和 MUST ≤ 100%。区域过滤 MUST 复用阶段 3 归属依据。

#### Scenario: 净通量分布互斥

- **WHEN** 统计 `net_cd` 分布
- **THEN** 每条记录 MUST 只落入一个档位
- **AND** 三档占比之和 MUST ≤ 100%

#### Scenario: 当年浓度三档

- **WHEN** 统计 `end_cd` 分布
- **THEN** 系统 MUST 使用 0.3 / 0.6 mg/kg 阈值（GB 15618-2018）
- **AND** 元信息 MUST 标注阈值来源

#### Scenario: 相对分级标注

- **WHEN** 统计 `in_cd` / `out_cd` 分布
- **THEN** 结果 MUST 标注 `relative: true`
- **AND** 系统 MUST NOT 将相对分级表述为绝对等级

### Requirement: 空间结果

系统 SHALL 提供 flux 点位 GeoJSON 与分级地图/直方图；坐标 MUST 取地块质心，地图 MUST 按字段使用对应分级（`net_cd` 三档互斥、`end_cd` GB15618 三档、`in/out` 分位数 6 级）。渲染 MUST 复用阶段 4 的栅格化与产物目录规范，产物 MUST 记录字段、区域、单位与分级模式。

#### Scenario: 点位 GeoJSON

- **WHEN** 调用方请求 flux 点位
- **THEN** 系统 MUST 返回含 `value` 与单位属性的 FeatureCollection
- **AND** 坐标来源 MUST 标注为地块质心

#### Scenario: 通量地图

- **WHEN** 调用方请求 `net_cd` 地图
- **THEN** 系统 MUST 使用负/平衡/正三档互斥分级
- **AND** 产物元信息 MUST 记录分级边界与字段单位 `g/ha/a`

### Requirement: 明细与导出

系统 SHALL 提供分页明细与 CSV 导出；导出 MUST 受最大行数限制（10 万行），超限 MUST 返回可读错误而不是静默截断。

#### Scenario: 导出 CSV

- **WHEN** 调用方请求导出
- **THEN** 系统 MUST 返回包含四类字段与键列的 CSV
- **AND** 行数超过上限时 MUST 报错

### Requirement: 空数据语义

系统 SHALL 在输入表或输出表为空时返回 200 + `has_data=false`， MUST NOT 用 404 区分"没数据"与"出错"；计算在无输入时 MUST 返回 `has_data=false` 而不是抛 500。

#### Scenario: 无输入数据

- **WHEN** 输入表为空时调用计算
- **THEN** 系统 MUST 返回 200 + `has_data=false`
- **AND** 系统 MUST NOT 写入输出表
