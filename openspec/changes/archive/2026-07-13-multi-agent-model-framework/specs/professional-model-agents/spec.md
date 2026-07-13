## ADDED Requirements

### Requirement: StabilityRiskAgent 智能体
系统 SHALL 实现 `StabilityRiskAgent` 智能体，对应模型1「耕地质量等级稳定性与退化风险识别模型」，负责评价耕地质量等级稳定性并识别退化风险。

#### Scenario: 等级稳定性评价
- **WHEN** 用户询问"全省耕地质量整体稳定吗？"
- **THEN** 智能体 SHALL 返回稳定性总体评价，包括稳定/一般/较弱面积占比，使用模拟数据

#### Scenario: 退化风险识别
- **WHEN** 用户询问"哪些县区高等级耕地存在退化风险？"
- **THEN** 智能体 SHALL 返回高等级不稳定耕地分布、县区排序和面积统计

#### Scenario: 重点关注清单
- **WHEN** 用户询问"哪些对象需要纳入重点关注清单？"
- **THEN** 智能体 SHALL 输出需要关注的县区/乡镇/地块清单，说明风险类型和来源

### Requirement: PotentialAssessmentAgent 智能体
系统 SHALL 实现 `PotentialAssessmentAgent` 智能体，对应模型2「耕地质量提升潜力评估模型」，负责评估耕地质量提升潜力和计算障碍度值。

#### Scenario: 提升潜力评估
- **WHEN** 智能体接收到地块质量指标数据
- **THEN** 智能体 SHALL 计算 11 个评价指标的潜在障碍度值和提升潜力等级

#### Scenario: 目标 pH 计算
- **WHEN** 智能体接收到当前 pH 值和质量目标
- **THEN** 智能体 SHALL 计算目标 pH 或 pH 增加值，供模型1和模型3使用

### Requirement: ProblemIdentificationAgent 智能体
系统 SHALL 实现 `ProblemIdentificationAgent` 智能体，对应模型3「耕地质量主要问题精准识别模型」，负责识别主要/次要障碍因素和障碍组合。

#### Scenario: 障碍因素识别
- **WHEN** 用户询问"耕地在哪些方面有问题？"
- **THEN** 智能体 SHALL 返回主要障碍因素、次要障碍因素和障碍组合统计

#### Scenario: 指标障碍等级统计
- **WHEN** 智能体接收到地块指标数据
- **THEN** 智能体 SHALL 输出每个指标的障碍等级（1~10级频数统计）

### Requirement: AcidificationRemediationAgent 智能体
系统 SHALL 实现 `AcidificationRemediationAgent` 智能体，对应模型4「耕地土壤酸化改良模型」，负责判定酸化程度并计算调理剂施用量。

#### Scenario: 酸化程度判定
- **WHEN** 用户询问"全省耕地酸化程度如何？"
- **THEN** 智能体 SHALL 返回不同酸化等级的比例分布

#### Scenario: 调理剂施用量计算
- **WHEN** 用户询问"如何治理强酸性耕地土壤？施加多少调理剂？"
- **THEN** 智能体 SHALL 返回碱性材料施用量建议（如石灰施用量 kg/亩）

### Requirement: OrganicMatterAgent 智能体
系统 SHALL 实现 `OrganicMatterAgent` 智能体，对应模型5「耕地土壤有机质培肥提升模型」，负责有机质提升评估和有机肥施用量计算。

#### Scenario: 有机质含量评估
- **WHEN** 用户询问"全省耕地土壤有机质含量如何？"
- **THEN** 智能体 SHALL 返回有机质含量空间分布和低值区域识别

#### Scenario: 有机肥施用量计算
- **WHEN** 用户询问"有机肥每亩施用量多少？"
- **THEN** 智能体 SHALL 返回有机肥施用量建议和潜在有机质提升预测值

### Requirement: ComprehensiveImprovementAgent 智能体
系统 SHALL 实现 `ComprehensiveImprovementAgent` 智能体，对应模型6「耕地综合地力改良提升模型」，负责综合多个模型结果形成分区分类的综合提升建议。

#### Scenario: 综合提升建议
- **WHEN** Manager 将模型1-5的结果传递给本智能体
- **THEN** 智能体 SHALL 综合各模型结果，生成分区分类的综合提升建议

#### Scenario: 农户地块综合诊断
- **WHEN** 农户询问"我这块地质量怎么样？"
- **THEN** 智能体 SHALL 返回地块质量等级、稳定性、主要问题和改良建议的综合诊断
