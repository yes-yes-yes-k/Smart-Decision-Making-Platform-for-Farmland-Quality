# cd-removal-calculation Specification

## Purpose
Cd 移除项计算：籽粒移除与秸秆移除通量计算（f11 亩产量系数）、写回输入表并触发通量重算，四类移除项的统计/点位/导出/地图。

## Requirements

### Requirement: 籽粒移除计算

系统 SHALL 由作物 Cd 结果与亩产量参数计算籽粒移除通量：`grain = exp(ln_crop_cd) × f11 × 0.5 × 15 / 1000`，单位为 g/ha/a。系数 `0.5`（斤→kg）、`15`（亩→ha）、`1000`（mg→g）MUST 在实现与文档中保持原系统口径，不得擅自改动。`f11`（亩产量，斤/亩）MUST 可由请求指定，默认 800，响应 MUST 记录实际使用值。

#### Scenario: 标准计算

- **WHEN** 作物 Cd 浓度 0.1 mg/kg、f11=800
- **THEN** 籽粒移除 MUST 为 0.6 g/ha/a
- **AND** 响应 MUST 记录 `f11=800`

#### Scenario: 指定 f11

- **WHEN** 调用方传入 f11=1000
- **THEN** 计算结果 MUST 与 f11=800 成 1.25 倍比例
- **AND** 响应 MUST 记录实际使用值

### Requirement: 秸秆移除计算

系统 SHALL 计算秸秆移除通量：`straw = [exp(ln)/(exp(ln)×0.76−0.0034)] × f11 × 0.5 × 15 / 1000`（g/ha/a）。分母 `exp(ln)×0.76−0.0034` 非正时系统 MUST **按原系统静默跳过**该样点（仅写日志），MUST NOT 因此中断计算。响应 MAY 返回 `skipped_invalid_denominator` 计数用于可观测性，该字段 MUST NOT 改变计算数值或筛选范围。移除计算 MUST 按全量执行，区域参数 MUST 仅记录（`area_filter: not_applied`），与原系统 `calculate_*_removal_by_area` 的 `area` 仅用于出图边界一致。

#### Scenario: 分母非正

- **WHEN** 某样点的 `exp(ln)×0.76−0.0034 ≤ 0`
- **THEN** 系统 MUST 跳过该样点且继续计算其余样点
- **AND** 跳过 MUST 只写日志，不得中断整批计算

#### Scenario: 正常计算

- **WHEN** 分母为正
- **THEN** 系统 MUST 按公式输出秸秆移除通量
- **AND** 单位 MUST 为 g/ha/a

### Requirement: 写回与触发重算

系统 SHALL 把计算出的籽粒/秸秆移除写回输入表对应列（`ZL_Cd` / `JG_Cd`），只更新这两列，MUST NOT 改动其它分量；写回后 MUST 触发阶段 5 的通量重算，并 MUST 分别报告 `updated_inputs` 与 `recalculated` 状态。系统 MUST 支持 `write_back=false`（只算不写）。

#### Scenario: 写回并重算

- **WHEN** 调用方请求计算且 `write_back=true`
- **THEN** 输入表的 ZL/JG MUST 被更新
- **AND** 输出表 MUST 被重算
- **AND** 响应 MUST 分别报告写回与重算结果

#### Scenario: 只算不写

- **WHEN** 调用方 `write_back=false`
- **THEN** 输入表 MUST NOT 被修改
- **AND** 系统 MUST 仍返回计算结果

#### Scenario: 重算失败

- **WHEN** 写回成功但重算失败
- **THEN** 响应 MUST 标记 `recalculated=false` 并给出错误
- **AND** MUST NOT 报告整体成功

### Requirement: 四类移除项统计与空间结果

系统 SHALL 提供 grain/straw/leaching/runoff 四类字段的统计、点位 GeoJSON 与导出。`leaching/runoff` MUST 直接读取输入表的 `DX_Cd/DB_Cd`，MUST NOT 重新计算。统计 MUST 复用阶段 2 口径，区域过滤 MUST 复用阶段 3 归属依据。

#### Scenario: 地下渗漏统计

- **WHEN** 调用方请求 `field=leaching` 统计
- **THEN** 系统 MUST 直接使用输入表 `DX_Cd` 的值
- **AND** 系统 MUST NOT 执行物理计算

#### Scenario: 点位与导出

- **WHEN** 调用方请求点位或 CSV 导出
- **THEN** 系统 MUST 返回含键列、字段值与单位的记录
- **AND** 导出 MUST 受 10 万行上限约束

### Requirement: 空数据与错误语义

系统 SHALL 在作物 Cd 结果为空时返回 `has_data=false`/`no_data`，MUST NOT 触发写回或重算；非法字段/区域/参数 MUST 返回机器可读 400 错误。

#### Scenario: 无作物 Cd 结果

- **WHEN** 作物 Cd 结果表为空时请求移除计算
- **THEN** 系统 MUST 不写回、不重算
- **AND** 返回 MUST 表明无数据
