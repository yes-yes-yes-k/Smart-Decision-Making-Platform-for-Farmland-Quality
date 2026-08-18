## ADDED Requirements

### Requirement: 实现 12 指标隶属度计算

系统 SHALL 对 7 个数值指标（SJD/YJZ/YXL/SXJ/TRRZ/YXTCHD/GCHD）使用隶属度函数 `1/(1+a*(u-c)^2)` 计算隶属度，对 5 个概念指标（ZDGC/PSNL/GGNL/DXBW/ZDGX）使用查找表映射隶属度。隶属度参数 a/c/ut1/ut2 按二级农业区配置。

#### Scenario: 数值指标峰型隶属度
- **WHEN** SJD 值在 [ut1, ut2] 范围内
- **THEN** 返回隶属度 = 1/(1+a*(u-c)^2)，结果在 [0, 1] 范围内

#### Scenario: 数值指标戒上型隶属度
- **WHEN** TRRZ 值 >= ut1
- **THEN** 当 u < c 时返回 1/(1+a*(u-c)^2)，当 u >= c 时返回 1.0

#### Scenario: 概念指标映射
- **WHEN** ZDGC 值为有效的质地代码（1-12）
- **THEN** 返回对应的概念隶属度查找值

### Requirement: 实现加权综合指数和等级判定

系统 SHALL 按 `quality_index = sum(membership[i] * weight[i])` 计算综合指数，按等级阈值 limits 判定耕地质量等级（1-10 等）。

#### Scenario: 正常计算
- **WHEN** parcel_info 有有效的 ejnyq（二级农业区代码）和全部 12 个指标
- **THEN** 返回 quality_index 在 [0, 1] 范围内，grade 在 1-10 范围内，持久化到 quality_grade_result 表

#### Scenario: 指标缺失降级
- **WHEN** soil_indicators 缺少部分指标
- **THEN** 缺失指标的隶属度为 0，仍计算加权和并标注 degraded

### Requirement: area_code 映射到二级农业区代码

系统 SHALL 通过 `AREA_TO_REGION` 映射表将 `ParcelInfo.area_code` 转换为二级农业区代码（ejnyq），用于选择隶属度参数和权重。乐昌(440281)→ejnyq_idx=3（南岭丘陵山地林农区，一级区 HN）。

#### Scenario: 已知 area_code
- **WHEN** area_code 为 "440281"
- **THEN** ejnyq_idx=3，使用 MODEL2_COEFFICIENTS[3] 的 a/c/ut1/ut2 和 weights

#### Scenario: 未知 area_code
- **WHEN** area_code 不在 AREA_TO_REGION 映射表中
- **THEN** 降级到默认 ejnyq_idx=0（闽南粤中），标注 reason=unknown_area_code
