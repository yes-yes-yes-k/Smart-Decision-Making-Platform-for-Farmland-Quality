## Purpose

耕地质量稳定性与退化风险评价模型，基于地块指标和空间邻域数据，计算等级边界安全度、指标支撑均衡度、关键指标临界度等稳定性指标，识别耕地质量退化风险。

## ADDED Requirements

### Requirement: 稳定性计算应基于 DB 地块指标

系统 SHALL 从 `parcel_info.soil_indicators` JSON 读取 12 个指标（SJD/YJZ/YXL/SXJ/TRRZ/GCZD/GGNL/PSNL/DXBW/ZDGX/YXTCHD/GCHD）及其隶属度（LSD）和权重（QZ），计算稳定性指标。

#### Scenario: DB 数据完整时执行真实计算
- **WHEN** parcel_info 表中存在指定 parcel_id 且 soil_indicators 包含全部 12 个指标
- **THEN** 系统返回 status=ok、data_source=db、simulated=False，并持久化到 stability_risk_result 表

#### Scenario: DB 数据缺失时降级
- **WHEN** parcel_info 表中不存在指定 parcel_id 或 soil_indicators 缺少必要字段
- **THEN** 系统返回 status=degraded、reason=missing_input，不持久化

### Requirement: 实现等级边界安全度计算（模块1）

系统 SHALL 按公式 `SAFE_ABS = clip((ZHQZ - qmax + grade * w) / w, 0, 1)` 计算等级边界安全度，其中 w = (qmax - qmin) / 10，qmin/qmax 为评价分区内 ZHQZ 的最小/最大值。

#### Scenario: 正常计算
- **WHEN** 地块有有效的 ZHQZ、GDZLDJ 和 PJFQ 字段
- **THEN** 返回 SAFE_ABS 在 [0, 1] 范围内

### Requirement: 实现指标支撑均衡度计算（模块2）

系统 SHALL 按公式 `BAL_ABS = 1 - sqrt(var / (m*(1-m)))` 计算指标支撑均衡度，其中 m 为加权隶属度均值，var 为加权方差。

#### Scenario: 正常计算
- **WHEN** 地块有全部 12 个指标的 LSD 和 QZ 值
- **THEN** 返回 BAL_ABS 和 BAL_REL（相对排名）在 [0, 1] 范围内

### Requirement: 实现关键指标临界度计算（模块3）

系统 SHALL 识别对等级边界影响最大的关键指标，返回 KEY_FAC（指标名）、KEY_ABS（临界度绝对值）、KEY_REL（相对排名）。

#### Scenario: 正常计算
- **WHEN** 地块有有效的 ZHQZ、GDZLDJ 和全部 LSD/QZ 值
- **THEN** 返回 KEY_FAC 为 12 个指标之一，KEY_ABS 在 [0, 1] 范围内

### Requirement: 实现空间邻域一致性计算（模块4）

系统 SHALL 用 PostGIS `ST_DWithin(geom, :center, :radius)` 查询邻域地块，计算邻域等级加权一致性 NEI_ABS。

#### Scenario: 有邻域地块
- **WHEN** 指定 radius 内存在其他地块且有 quality_grade
- **THEN** 返回 NEI_ABS 在 [0, 1] 范围内

#### Scenario: 无邻域地块
- **WHEN** 指定 radius 内无其他地块
- **THEN** 返回 NEI_ABS=null、reason=no_neighbors，不阻断其他模块

### Requirement: 实现历史变化趋势计算（模块5）

系统 SHALL 从 `parcel_history_snapshot` 读取 3 期（2018/2021/2024）历史数据，按历史斜率回归计算 `H_ABS = (1-delta)/2`。

#### Scenario: 三期历史数据完整
- **WHEN** parcel_history_snapshot 存在该 parcel_id 的 2018/2021/2024 三期记录
- **THEN** 返回 H_ABS 在 [0, 1] 范围内

#### Scenario: 历史数据不足降级
- **WHEN** 历史期数 < 2
- **THEN** 返回 H_ABS=null、reason=insufficient_history

### Requirement: 实现掉级风险/退化风险/集聚风险/持续低质计算（模块6-9）

系统 SHALL 基于历史数据和邻域数据计算：模块6 掉级风险（等级下降幅度概率）、模块7 关键因子退化风险（关键指标历史退化率）、模块8 退化空间集聚风险（PostGIS 邻域退化密度）、模块9 持续低质风险（连续低等级期数）。

#### Scenario: 历史与邻域数据完整
- **WHEN** parcel_history_snapshot 有 3 期数据且邻域有等级信息
- **THEN** 返回各模块风险值在 [0, 1] 范围内

#### Scenario: 数据不足部分降级
- **WHEN** 模块 6-9 中部分依赖数据缺失
- **THEN** 缺失模块返回 null 并标注 reason，其他模块正常计算

### Requirement: 历史数据导入到 parcel_history_snapshot 表

系统 SHALL 新增 `parcel_history_snapshot` 表（parcel_id FK、survey_year、soil_indicators JSON、quality_grade、composite_index），从原始 Shapefile（2018/2021/2024）导入历史数据。

#### Scenario: 导入成功
- **WHEN** 运行导入脚本且 Shapefile 存在
- **THEN** parcel_history_snapshot 表按 parcel_id+survey_year 唯一约束写入记录

#### Scenario: parcel_id 不匹配
- **WHEN** Shapefile 中地块编号与 DB parcel_id 不一致
- **THEN** 通过映射表关联，无法关联的记录跳过并记录警告
