## MODIFIED Requirements

### Requirement: 通量统计与分布

系统 SHALL 按区域聚合四类字段（`in_cd/out_cd/net_cd/end_cd`），基础统计 MUST 复用阶段 2 口径（总体标准差、下标直取分位数、6 位小数，与原系统 `get_flux_statistics_by_town` 的 `variance/mean` 与 `sorted[int(n×p)]` 一致）。分布 MUST 为：`end_cd` 三档 `<0.3 / 0.3–0.6 / ≥0.6 mg/kg`；`net_cd` **沿用原系统定义**：负值 `v<0`、接近平衡 `-5≤v≤5`、正值 `v>0`（三档**允许重叠**）；`in/out` 相对本批均值三档（`<0.5×mean / 0.5–1.5×mean / ≥1.5×mean`）。各档占比 MUST 按 `round(count/total×100, 2)` 计算、**不补差**，`net_cd` 三档占比之和 MAY 超过 100%。区域过滤 MUST 复用阶段 3 归属依据。

#### Scenario: 净通量分布互斥

- **WHEN** 统计 `net_cd` 分布
- **THEN** 负值档 MUST 为 `v<0`、平衡档 MUST 为 `-5≤v≤5`、正值档 MUST 为 `v>0`（原系统重叠定义，场景名沿用历史命名）
- **AND** 同一记录 MAY 同时计入平衡档与正（或负）值档
- **AND** 响应 MUST 标注 `mutually_exclusive: false`
- **AND** 三档占比之和 MAY 超过 100%

#### Scenario: 当年浓度三档

- **WHEN** 统计 `end_cd` 分布
- **THEN** 系统 MUST 使用 0.3 / 0.6 mg/kg 阈值（GB 15618-2018）
- **AND** 元信息 MUST 标注阈值来源

#### Scenario: 相对分级标注

- **WHEN** 统计 `in_cd` / `out_cd` 分布
- **THEN** 结果 MUST 标注 `relative: true`
- **AND** 系统 MUST NOT 将相对分级表述为绝对等级
