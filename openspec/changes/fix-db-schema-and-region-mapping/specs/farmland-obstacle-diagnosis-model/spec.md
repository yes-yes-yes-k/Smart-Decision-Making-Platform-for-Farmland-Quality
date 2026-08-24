# farmland-obstacle-diagnosis-model Specification (Delta)

## MODIFIED Requirements

### Requirement: area_code 映射到农业区代码选择系数

系统 SHALL 通过 `AREA_TO_REGION` 映射表将 `ParcelInfo.area_code` 转换为一级农业区代码（primary，HN/CJ）选择隶属度系数，二级农业区代码（secondary，MNY/YXG/NL/QN）选择权重。乐昌(440281)和新丰县(440233)→primary=HN、secondary=NL。

#### Scenario: 已知 area_code
- **WHEN** area_code 为 "440281" 或 "440233"
- **THEN** 使用 MODEL3_COEFFICIENTS["HN"] 的隶属度系数和 MODEL3_WEIGHTS["NL"] 的权重

#### Scenario: 未知 area_code
- **WHEN** area_code 不在 AREA_TO_REGION 映射表中
- **THEN** 降级到默认 primary=HN、secondary=MNY，标注 reason=unknown_area_code

### Requirement: 模型3 在线障碍诊断查询

系统 SHALL 提供在线查询接口，按地块 ID 从批量评价和障碍诊断结果中查询障碍诊断信息，对接 `run_thematic_model()` 的统一调用契约。查询结果 SHALL 包含标准字段命名的评价和诊断数据。

#### Scenario: 查询指定地块的障碍诊断结果
- **WHEN** 调用方以地块 ID 发起在线查询，且批量评价和障碍诊断结果已就绪
- **THEN** 系统 SHALL 返回该地块的 `ZALX`（障碍类型）、`ZYZAYS`（主要障碍因素）、`CYZAYS`（次要障碍因素）、`GDZLDJ`（质量等级）和各指标障碍度排序

#### Scenario: 诊断数据未就绪
- **WHEN** 调用方发起在线查询，但批量评价和障碍诊断尚未完成或结果文件缺失
- **THEN** 系统 SHALL 返回 `status: "not_ready"` 和"数据未就绪，请先执行批量评价"的提示

#### Scenario: 酸化改良模块字段对齐
- **WHEN** 酸化改良模块（evaluate_acidification / query_acidification）从 evaluation_results 读取地块数据执行酸化分区与改良方案生成
- **THEN** 系统 SHALL 使用标准字段名读取数据：pH 值取自 `SJD` 列、有机质取自 `YJZ` 列、区域代码取自 `region_code` 列；不得引用旧字段名（`PH`、`YJ`、`JY`），并 SHALL 按地块实际 `region_code` 选择酸化分级配置（不得因字段缺失恒回退到默认区）

#### Scenario: 新丰县地块酸化改良
- **WHEN** 酸化改良模块从 evaluation_results 读取 area_code="440233" 的地块数据
- **THEN** 系统 SHALL 按华南区(HN)的酸化分级配置选择参数，不得因字段缺失恒回退到默认区
