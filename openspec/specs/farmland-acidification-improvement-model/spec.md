# farmland-acidification-improvement-model Specification

## Purpose
TBD - created by archiving change add-stability-risk-and-grade-evaluation. Update Purpose after archive.
## Requirements
### Requirement: 模型3 酸化因子提取
系统 SHALL 从地块指标数据中提取酸化相关因子（pH 值、酸化方向），为后续酸化程度判定和改良方案生成提供基础数据。

#### Scenario: 提取酸化因子
- **WHEN** 系统处理地块数据（CSV 或在线查询），且包含 pH 字段
- **THEN** 系统 SHALL 提取 pH 值，并根据阈值（<6.5 为酸化，>7.5 为碱化）判定酸化方向

### Requirement: 模型3 酸化程度分区
系统 SHALL 根据酸化因子和障碍诊断结果，对地块进行酸化程度分区（无明显酸化、轻度酸化、中度酸化、重度酸化）。

#### Scenario: 酸化程度判定
- **WHEN** 系统完成酸化因子提取和障碍诊断，且 pH 隶属度和障碍度数据已就绪
- **THEN** 系统 SHALL 根据 pH 隶属度和障碍度阈值，将地块划分为无明显酸化、轻度酸化、中度酸化或重度酸化

#### Scenario: 酸化分区统计
- **WHEN** 调用方请求某区域的酸化分区统计
- **THEN** 系统 SHALL 返回该区域各酸化程度分区的地块数量或面积占比

### Requirement: 模型3 改良方案生成
系统 SHALL 基于酸化程度分区结果，生成针对性的改良方案，包括调理剂施用量建议和改良措施匹配。

#### Scenario: 生成改良方案
- **WHEN** 用户请求某地块的酸化改良方案，且该地块被判定为中度或重度酸化
- **THEN** 系统 SHALL 根据酸化程度和土壤特性，生成调理剂施用量建议（如石灰施用量 kg/亩）和改良措施（如施肥方式、轮作制度调整）

#### Scenario: 轻度或无酸化
- **WHEN** 用户请求某地块的酸化改良方案，但该地块为轻度酸化或无明显酸化
- **THEN** 系统 SHALL 返回"无需特殊改良"的提示，建议常规监测和维护

### Requirement: 模型3 酸化改良在线查询
系统 SHALL 提供在线查询接口，按地块 ID 查询酸化程度分区和改良方案，对接 `run_thematic_model()` 的统一调用契约。

#### Scenario: 查询指定地块的酸化改良方案
- **WHEN** 调用方以地块 ID 发起在线查询，且批量评价和障碍诊断结果已就绪
- **THEN** 系统 SHALL 返回该地块的酸化程度、酸化方向、调理剂施用量建议和改良措施

#### Scenario: 数据未就绪
- **WHEN** 调用方发起在线查询，但批量评价和障碍诊断尚未完成
- **THEN** 系统 SHALL 返回 `status: "not_ready"` 和"数据未就绪，请先执行批量评价"的提示

### Requirement: 模型3 改良方案输出格式
系统 SHALL 以标准化格式输出改良方案，包含酸化程度、调理剂施用量、改良措施和预期效果。

#### Scenario: 标准化改良方案输出
- **WHEN** 系统生成改良方案
- **THEN** 输出 SHALL 包含：酸化程度（轻/中/重度）、调理剂类型、施用量（kg/亩）、改良措施描述、预期效果（pH 提升幅度、有机质提升预期）

