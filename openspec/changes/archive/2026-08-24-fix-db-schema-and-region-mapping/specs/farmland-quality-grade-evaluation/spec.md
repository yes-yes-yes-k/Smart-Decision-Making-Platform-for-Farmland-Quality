# farmland-quality-grade-evaluation Specification (Delta)

## MODIFIED Requirements

### Requirement: area_code 映射到二级农业区代码

系统 SHALL 通过 `AREA_TO_REGION` 映射表将 `ParcelInfo.area_code` 转换为二级农业区代码（ejnyq），用于选择隶属度参数和权重。乐昌(440281)→ejnyq_idx=3（南岭丘陵山地林农区，一级区 HN）。新丰县(440233)→ejnyq_idx=3（同属华南区/南岭丘陵山地林农区）。

#### Scenario: 已知 area_code
- **WHEN** area_code 为 "440281" 或 "440233"
- **THEN** ejnyq_idx=3，使用 MODEL2_COEFFICIENTS[3] 的 a/c/ut1/ut2 和 weights

#### Scenario: 未知 area_code
- **WHEN** area_code 不在 AREA_TO_REGION 映射表中
- **THEN** 降级到默认 ejnyq_idx=0（闽南粤中），标注 reason=unknown_area_code

### Requirement: 实现加权综合指数和等级判定

系统 SHALL 按 `quality_index = sum(membership[i] * weight[i])` 计算综合指数，按等级阈值 limits 判定耕地质量等级（1-10 等）。

#### Scenario: 正常计算
- **WHEN** parcel_info 有有效的 ejnyq（二级农业区代码）和全部 12 个指标
- **THEN** 返回 quality_index 在 [0, 1] 范围内，grade 在 1-10 范围内，持久化到 quality_grade_result 表

#### Scenario: 指标缺失降级
- **WHEN** soil_indicators 缺少部分指标
- **THEN** 缺失指标的隶属度为 0，仍计算加权和并标注 degraded

#### Scenario: 新丰县地块正常计算
- **WHEN** parcel_info 有 area_code="440233"，且有有效的 ejnyq（二级农业区代码）和全部 12 个指标
- **THEN** 使用 MODEL2_COEFFICIENTS[3] 参数计算隶属度和综合指数，返回 quality_index 在 [0, 1] 范围内，grade 在 1-10 范围内
