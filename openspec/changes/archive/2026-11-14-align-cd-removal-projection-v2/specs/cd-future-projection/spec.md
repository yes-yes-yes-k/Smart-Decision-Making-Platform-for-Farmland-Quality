## MODIFIED Requirements

### Requirement: 未来 Cd 浓度预测

系统 SHALL 按 `Future_Cd = (Initial_Cd + Net_Cd × years) / (2000 × bulk_density_g_cm3)` 计算未来 N 年 Cd 浓度（mg/kg），`years` MUST 在 1–100 范围内。该式**严格照抄原系统**：分母固定常数 `2000` 乘容重，MUST NOT 读取 `soil_depth_m`，MUST NOT 用 `soil_depth_m × bulk_density × 1e7` 的 v2 土重推导替代（两者仅在 0.2m 耕层时等价，差异 MUST 记录在 `docs/cd-legacy-known-issues.md`）。

净通量 MUST 取自 v2 输出表 `cd_flux_output_v2` 中**与输入行当前 `input_revision` 匹配**的输出记录（含已写回的移除项），系统 MUST NOT 在本能力内重算通量。取数 MUST 跳过 `contract_version='legacy_v1'` 的输入行。`bulk_density_g_cm3` 缺失 MUST 回退 1.0，`Initial_Cd` 缺失 MUST 回退 0，`soil_mass` 非正 MUST 输出 0，回退计数 MUST 写入响应。结果 MUST 标注为线性情景推算，不得表述为实测预测。

#### Scenario: 标准外推

- **WHEN** Initial_Cd=2000、Net_Cd=5.6、bulk_density_g_cm3=1.0、years=10
- **THEN** Future_Cd MUST 为 (2000+56)/2000 = 1.028 mg/kg

#### Scenario: 不依赖耕层深度

- **WHEN** 同一初始量、净通量与容重，但 `soil_depth_m` 分别为 0.2 与 0.3
- **THEN** 两次外推结果 MUST 完全相同（公式不含 `soil_depth_m`）

## MODIFIED Requirements（区域与来源过滤）

### Requirement: 区域与来源过滤

系统 SHALL 支持按区域（区域类型 + 标识）、数据来源与核算年度过滤。与原系统一致，**区域参数 MUST 仅记录在响应中（`area_filter: not_applied`），MUST NOT 参与数据查询**；数据来源过滤 MUST 生效。`accounting_year` 为 v2 的数据维度筛选，MUST 可选：给出时只取该年度的输入行，未给出时 MUST 不限年度（保持与原系统「全量一套结果」的可比性），响应 MUST 记录实际生效的年度。

#### Scenario: 指定核算年度

- **WHEN** 同一地块样点在 `cd_flux_input_v2` 中同时存在 2023 与 2024 两行，且请求 `accounting_year=2024`
- **THEN** 查询 MUST 只返回 2024 那一行
- **AND** 未给出 `accounting_year` 时 MUST 返回两行（不限年度）
