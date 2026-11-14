# cd-removal-calculation Specification

## Purpose
Cd 移除项计算：籽粒移除与秸秆移除通量计算（f11 亩产量系数）、写回 v2 输入表并触发 v2 通量重算，四类移除项的统计/点位/导出/地图。

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

系统 SHALL 把计算出的籽粒/秸秆移除写回 **v2 输入表** `cd_flux_input_v2` 的 `grain_removal` / `straw_removal` 两列，MUST NOT 改动其它分量；写回 MUST 按 `select_inputs` 返回的 `id` 精确定位，并在同一条语句中把 `input_revision` 递增 1（与 v2 的 `ON CONFLICT ... DO UPDATE SET ..., input_revision = input_revision + 1` 语义一致）。写回后 MUST 触发 `cd_flux_v2.calculate` 重算，并 MUST 分别报告 `updated_inputs` 与 `recalculated` 状态。系统 MUST 支持 `write_back=false`（只算不写）。

v2 唯一键为 `(source, parcel_id, sample_id, accounting_year)`，而作物 Cd 结果表没有年度字段，无法自动推导，因此 `write_back=true` 时调用方 **MUST 显式提供 `accounting_year`**，缺失 MUST 返回机器可读的 `year_required` 错误，MUST NOT 猜测年度或写回全部年度。`contract_version='legacy_v1'` 的行 MUST NOT 参与计算或写回，跳过数量 MUST 在响应中披露。同一 `(parcel_id, sample_id)` 在所选范围内命中多个来源时 MUST 判为歧义并拒绝写回，MUST NOT 批量命中。

#### Scenario: 写回并重算

- **WHEN** 调用方请求计算，`write_back=true` 且提供了 `accounting_year`
- **THEN** 对应输入行的 `grain_removal` / `straw_removal` MUST 被更新
- **AND** 该行 `input_revision` MUST 递增 1，其它列 MUST 保持原值
- **AND** 输出表 MUST 按新修订被重算
- **AND** 响应 MUST 分别报告写回与重算结果

#### Scenario: 缺少年度

- **WHEN** 调用方 `write_back=true` 但未提供 `accounting_year`
- **THEN** 系统 MUST 返回 `year_required` 错误
- **AND** MUST NOT 修改任何输入行

#### Scenario: 同地块多年度

- **WHEN** 同一 `(parcel_id, sample_id)` 在输入表中存在多个 `accounting_year`
- **THEN** 系统 MUST 只写回指定年度的那一行
- **AND** 其它年度的行 MUST 保持不变

#### Scenario: legacy 行与歧义

- **WHEN** 范围内存在 `contract_version='legacy_v1'` 的行，或同一地块样点命中多个来源
- **THEN** legacy 行 MUST NOT 被写回，其数量 MUST 在 `legacy_input_skipped` 中披露
- **AND** 歧义样点 MUST NOT 被写回，其数量 MUST 在 `ambiguous_input_rows` 中披露

#### Scenario: 只算不写

- **WHEN** 调用方 `write_back=false`
- **THEN** 输入表 MUST NOT 被修改
- **AND** 系统 MUST 仍返回计算结果

#### Scenario: 重算失败

- **WHEN** 写回成功但重算失败
- **THEN** 响应 MUST 标记 `recalculated=false` 并给出错误
- **AND** MUST NOT 报告整体成功

### Requirement: 四类移除项统计与空间结果

系统 SHALL 提供 grain/straw/leaching/runoff 四类字段的统计、点位 GeoJSON 与导出。`leaching/runoff` MUST 直接读取 v2 输入表的 `groundwater_leaching` / `surface_runoff` 两列，MUST NOT 重新计算。统计 MUST 复用阶段 2 口径，区域过滤 MUST 复用阶段 3 归属依据；`year` 为可选的数据维度筛选，只在 `leaching/runoff` 这类来自输入表的字段上生效，作物派生的 grain/straw 无年度维度。

#### Scenario: 地下渗漏统计

- **WHEN** 调用方请求 `field=leaching` 统计
- **THEN** 系统 MUST 直接使用 v2 输入表 `groundwater_leaching` 的值
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
