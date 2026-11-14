## MODIFIED Requirements

### Requirement: 写回与触发重算

系统 SHALL 把计算出的籽粒/秸秆移除写回 **v2 输入表** `cd_flux_input_v2` 的 `grain_removal` / `straw_removal` 两列，MUST NOT 改动其它分量；写回 MUST 按 `select_inputs` 返回的 `id` 精确定位，并在同一条语句中把 `input_revision` 递增 1（与 v2 的 `ON CONFLICT ... DO UPDATE SET ..., input_revision = input_revision + 1` 语义一致）。写回后 MUST 触发 `cd_flux_v2.calculate` 重算，并 MUST 分别报告 `updated_inputs` 与 `recalculated` 状态。系统 MUST 支持 `write_back=false`（只算不写）。

v2 唯一键为 `(source, parcel_id, sample_id, accounting_year)`，而作物 Cd 结果表没有年度字段，无法自动推导，因此 `write_back=true` 时调用方 **MUST 显式提供 `accounting_year`**，缺失 MUST 返回机器可读的 `year_required` 错误，MUST NOT 猜测年度或写回全部年度。`contract_version='legacy_v1'` 的行 MUST NOT 参与计算或写回，跳过数量 MUST 在响应中披露。同一 `(parcel_id, sample_id)` 在所选范围内命中多个来源时 MUST 判为歧义并拒绝写回，MUST NOT 批量命中。

#### Scenario: 写回并重算

- **WHEN** 调用方请求计算，`write_back=true` 且提供了 `accounting_year`
- **THEN** 对应输入行的 `grain_removal` / `straw_removal` MUST 被更新
- **AND** 该行 `input_revision` MUST 递增 1，其它列 MUST 保持原值

#### Scenario: 缺少年度

- **WHEN** 调用方 `write_back=true` 但未提供 `accounting_year`
- **THEN** 系统 MUST 返回 `year_required` 错误
- **AND** MUST NOT 修改任何输入行

#### Scenario: 同地块多年度

- **WHEN** 同一 `(parcel_id, sample_id)` 在输入表中存在多个 `accounting_year`
- **THEN** 系统 MUST 只写回指定年度的那一行
- **AND** 其它年度的行 MUST 保持不变

### Requirement: 四类移除项统计与空间结果

系统 SHALL 提供 grain/straw/leaching/runoff 四类字段的统计、点位 GeoJSON 与导出。`leaching/runoff` MUST 直接读取 v2 输入表的 `groundwater_leaching` / `surface_runoff` 两列，MUST NOT 重新计算。统计 MUST 复用阶段 2 口径，区域过滤 MUST 复用阶段 3 归属依据；`year` 为可选的数据维度筛选，只在 `leaching/runoff` 这类来自输入表的字段上生效，作物派生的 grain/straw 无年度维度。

#### Scenario: 地下渗漏统计

- **WHEN** 调用方请求 `field=leaching` 统计
- **THEN** 系统 MUST 直接使用 v2 输入表 `groundwater_leaching` 的值
- **AND** 系统 MUST NOT 执行物理计算
