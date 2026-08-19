## ADDED Requirements

### Requirement: 实现障碍等级判定

系统 SHALL 对每个指标按阈值判定障碍等级（重度障碍/中度障碍/轻度障碍/无障碍）。SJD 障碍等级按 pH 区间判定（<=3 或 >10 为重度，6.5-7.5 为无障碍），YJZ 按 <=10 重度/<=20 中度/<=25 轻度/else 无障碍判定，其他指标类似。

#### Scenario: pH 极酸判定为重度障碍
- **WHEN** soil_ph <= 4.5
- **THEN** SJD 障碍等级为「酸化重度障碍」

#### Scenario: 有机质丰富判定为无障碍
- **WHEN** organic_matter > 25
- **THEN** YJZ 障碍等级为「无障碍」

### Requirement: 实现障碍度计算

系统 SHALL 按 `obstacle_degree = (1-membership)*weight / sum((1-membership)*weight)` 计算每个指标的障碍度，障碍度之和为 1。

#### Scenario: 正常计算
- **WHEN** 全部 12 个指标有有效的隶属度和权重
- **THEN** 12 个障碍度值之和为 1.0，每个在 [0, 1] 范围内

### Requirement: 实现障碍诊断（主要/次要因子识别）

系统 SHALL 按障碍度降序排列，障碍度 >= 0.20 的因子为主要障碍因素，障碍度 >= 0.10 但 < 0.20 的为次要障碍因素。主要因子数=1 且无次要因子时为「单一障碍」，主要因子数>1 为「多障碍」，无主要因子为「无明显障碍」。

#### Scenario: 多障碍诊断
- **WHEN** 两个以上指标障碍度 >= 0.20
- **THEN** 障碍类型为「多障碍」，主要障碍因素列表包含这些指标的中文名和障碍度

#### Scenario: 无明显障碍
- **WHEN** 所有指标障碍度 < 0.20
- **THEN** 障碍类型为「无明显障碍」

### Requirement: area_code 映射到农业区代码选择系数

系统 SHALL 通过 `AREA_TO_REGION` 映射表将 `ParcelInfo.area_code` 转换为一级农业区代码（primary，HN/CJ）选择隶属度系数，二级农业区代码（secondary，MNY/YXG/NL/QN）选择权重。乐昌(440281)→primary=HN、secondary=NL。

#### Scenario: 已知 area_code
- **WHEN** area_code 为 "440281"
- **THEN** 使用 MODEL3_COEFFICIENTS["HN"] 的隶属度系数和 MODEL3_WEIGHTS["NL"] 的权重

#### Scenario: 未知 area_code
- **WHEN** area_code 不在 AREA_TO_REGION 映射表中
- **THEN** 降级到默认 primary=HN、secondary=MNY，标注 reason=unknown_area_code
