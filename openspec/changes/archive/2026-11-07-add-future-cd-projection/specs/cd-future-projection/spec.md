# cd-future-projection Specification (Delta)

## ADDED Requirements

### Requirement: 未来 Cd 浓度预测

系统 SHALL 按 `Future_Cd = (Initial_Cd + Net_Cd × years) / (2000 × bd020_90)` 计算未来 N 年 Cd 浓度（mg/kg），`years` MUST 在 1–100 范围内。净通量 MUST 取自通量输出表（含已写回的移除项），系统 MUST NOT 在本能力内重算通量。`bd020_90` 缺失 MUST 回退 1.0，`Initial_Cd` 缺失 MUST 回退 0，`soil_mass` 非正 MUST 输出 0，回退计数 MUST 写入响应。结果 MUST 标注为线性情景推算，不得表述为实测预测。

#### Scenario: 标准外推

- **WHEN** Initial_Cd=2000、Net_Cd=5.6、bd020_90=1.0、years=10
- **THEN** Future_Cd MUST 为 (2000+56)/2000 = 1.028 mg/kg
- **AND** 响应 MUST 记录 years 与回退计数

#### Scenario: 年份越界

- **WHEN** years=0 或 years=101
- **THEN** 系统 MUST 拒绝并返回机器可读错误

#### Scenario: 负净通量

- **WHEN** 净通量为负且外推结果为负浓度
- **THEN** 系统 MUST 按公式如实返回负值
- **AND** MUST NOT 静默截断为 0

### Requirement: 多年份情景对比

系统 SHALL 支持一次请求多个年份（如 1/5/10/20），并按年份分组返回统计；MUST 拒绝空列表、非整数与非 1–100 范围的年份。

#### Scenario: 多情景

- **WHEN** 请求 years=[1,5,10]
- **THEN** 响应 MUST 按年份分别给出统计
- **AND** 每个年份 MUST 与单年份请求结果一致

### Requirement: 区域与来源过滤

系统 SHALL 支持按区域（区域类型 + 标识）与数据来源过滤，归属 MUST 复用阶段 3 依据；MUST NOT 出现原系统"区域参数只进日志、实际查全量"的行为。

#### Scenario: 指定乡镇

- **WHEN** 请求 `region_type=township&region_id=T1`
- **THEN** 预测 MUST 只使用归属 T1 的地块
- **AND** 统计样本数 MUST 与阶段 3 该乡镇的样本数一致

### Requirement: 统计口径

系统 SHALL 复用阶段 2 的统计口径（总体标准差、下标直取分位数、6 位小数）与 GB 15618-2018 三档分布（<0.3 / 0.3–0.6 / ≥0.6 mg/kg），并 MUST 在响应中标注口径来源；MUST NOT 使用样本标准差（n−1）或线性插值分位数。

#### Scenario: 标准差口径

- **WHEN** 请求某年份统计
- **THEN** 标准差 MUST 为总体标准差（除以 n）
- **AND** 响应 MUST 标注 `statistics_scope` 说明复用阶段 2 口径

### Requirement: 空间分布与导出

系统 SHALL 提供未来 Cd 的点位 GeoJSON、分级地图/直方图与 CSV 导出；地图 MUST 复用阶段 4 渲染引擎与 GB15618 三档分级，导出 MUST 受 10 万行上限约束。

#### Scenario: 未来空间分布

- **WHEN** 请求某年份地图
- **THEN** 系统 MUST 输出 GB15618 三档分级地图
- **AND** 产物元信息 MUST 记录 years、区域与单位 mg/kg
