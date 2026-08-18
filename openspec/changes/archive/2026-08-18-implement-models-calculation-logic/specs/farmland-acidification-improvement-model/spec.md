## ADDED Requirements

### Requirement: 实现产酸平衡模型计算

系统 SHALL 根据 land_type（旱地/水田）和 fertilizer_type（尿素/复合肥）选择对应的产酸平衡函数，计算石灰施用量（YTK）和有机肥施用量（MBNT）。输入参数为 SJD（pH）、Hex（交换性氢）、Alex（交换性铝）。

#### Scenario: 旱地复合肥计算
- **WHEN** land_type=upland 且 fertilizer_type=compound 且 soil_indicators 有 soil_ph、exchangeable_hydrogen、exchangeable_aluminum
- **THEN** 返回 YTK（石灰施用量）和 MBNT（有机肥施用量），持久化到 acidification_remediation_result 表

#### Scenario: 水田尿素计算
- **WHEN** land_type=paddy 且 fertilizer_type=urea
- **THEN** 使用 paddy_urea 函数计算，YTK 系数为 0.6

### Requirement: 替代外部 .exe 模型依赖

系统 SHALL 使用纯 Python 实现产酸平衡计算，不再依赖外部 .exe 模型。当 soil_indicators 缺少 exchangeable_hydrogen 或 exchangeable_aluminum 时降级。

#### Scenario: 外部模型不可用时正常计算
- **WHEN** 外部 .exe 模型不存在但 DB 有完整的酸化指标
- **THEN** 系统使用 Python 实现计算，status=ok，不返回 model_unavailable

#### Scenario: 交换性铝缺失降级
- **WHEN** soil_indicators 缺少 exchangeable_aluminum
- **THEN** 返回 status=degraded、reason=missing_input
