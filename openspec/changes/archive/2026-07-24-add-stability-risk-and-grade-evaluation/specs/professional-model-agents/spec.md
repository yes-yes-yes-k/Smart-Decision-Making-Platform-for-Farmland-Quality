## MODIFIED Requirements

### Requirement: StabilityRiskAgent 智能体
系统 SHALL 实现 `StabilityRiskAgent` 智能体，对应模型1「耕地质量等级稳定性与退化风险识别模型」，通过调用模型1 的在线查询接口（`get_parcel_result`）获取预计算结果，返回基于真实九模块分析的稳定性评价和退化风险识别，不再使用模拟数据。

#### Scenario: 等级稳定性评价
- **WHEN** 用户询问"全省耕地质量整体稳定吗？"，且模型1 预计算结果已就绪
- **THEN** 智能体 SHALL 调用模型1 在线查询接口获取历史变化趋势模块（module=5）结果，返回基于真实数据的稳定性评价，包括持续改善/基本稳定/波动退化/持续退化的分类统计

#### Scenario: 退化风险识别
- **WHEN** 用户询问"哪些县区高等级耕地存在退化风险？"，且模型1 预计算结果已就绪
- **THEN** 智能体 SHALL 调用模型1 在线查询接口获取掉级风险（module=6）和关键因子退化风险（module=7）模块结果，返回真实的退化风险分布和关键退化因子

#### Scenario: 重点关注清单
- **WHEN** 用户询问"哪些对象需要纳入重点关注清单？"，且模型1 预计算结果已就绪
- **THEN** 智能体 SHALL 调用模型1 在线查询接口获取持续低质风险（module=9）模块结果，输出需要关注的地块清单、低质年份数和风险类型

#### Scenario: 预计算数据未就绪
- **WHEN** 用户询问稳定性或退化风险相关问题，但模型1 离线预计算结果未就绪
- **THEN** 智能体 SHALL 返回"模型1 数据未就绪，请先执行离线预计算"的提示，`confidence` 字段降低，不返回模拟数据冒充真实结果

## ADDED Requirements

### Requirement: FarmlandGradeObstacleAgent 智能体
系统 SHALL 实现 `FarmlandGradeObstacleAgent` 智能体，对应耕地质量等级和障碍度评价模型（Fortran exe），通过 subprocess 调用 `Farmland_quality_evaluation.exe` 获取地块评价结果，返回基于 GB/T 33469-2016 标准的真实质量等级和障碍度诊断。

#### Scenario: 质量等级查询
- **WHEN** 用户询问某地块的耕地质量等级，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 通过 subprocess 调用 exe，返回质量等级（1-10等）、综合指数和 12 项指标的隶属度

#### Scenario: 障碍度诊断
- **WHEN** 用户询问某地块的主要障碍因素，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 通过 subprocess 调用 exe，返回障碍度因子排序表（从大到小），识别主要限制因子

#### Scenario: exe 调用失败
- **WHEN** exe 调用失败（超时、数据库缺失、exe 未部署、地块代码无效）
- **THEN** 智能体 SHALL 返回明确的错误信息（如"评价服务超时"、"数据库文件缺失"、"未找到地块代码"），`confidence` 字段降低，不返回模拟数据

### Requirement: ObstacleDiagnosisAgent 智能体
系统 SHALL 实现 `ObstacleDiagnosisAgent` 智能体，对应模型3「耕地质量主要问题精准识别模型」，通过调用模型3 的在线查询接口获取障碍诊断结果，返回真实的障碍类型、主要/次要障碍因素和障碍组合类型。

#### Scenario: 障碍诊断查询
- **WHEN** 用户询问某地块的障碍诊断结果，且模型3 批量评价和诊断结果已就绪
- **THEN** 智能体 SHALL 调用模型3 在线查询接口，返回障碍类型（单一障碍/多障碍）、主要障碍因素、次要障碍因素和障碍度排序

#### Scenario: 障碍组合类型识别
- **WHEN** 用户询问某地块的障碍组合类型，且该地块存在多个中度以上障碍因素
- **THEN** 智能体 SHALL 返回障碍组合类型描述（如"酸化+有机质不足"、"养分失衡+耕层条件偏弱"）

#### Scenario: 诊断数据未就绪
- **WHEN** 用户询问障碍诊断相关问题，但模型3 批量评价和诊断结果未就绪
- **THEN** 智能体 SHALL 返回"模型3 数据未就绪，请先执行批量评价"的提示，不返回模拟数据

### Requirement: AcidificationImprovementAgent 智能体
系统 SHALL 实现 `AcidificationImprovementAgent` 智能体，对应模型3「耕地土壤酸化改良模型」，通过调用模型3 的在线查询接口获取酸化程度分区和改良方案，返回真实的酸化程度、调理剂施用量建议和改良措施。

#### Scenario: 酸化程度查询
- **WHEN** 用户询问某地块的酸化程度，且模型3 批量评价和诊断结果已就绪
- **THEN** 智能体 SHALL 返回酸化程度（无明显酸化/轻度/中度/重度）、酸化方向（酸化/碱化）和 pH 值

#### Scenario: 改良方案查询
- **WHEN** 用户询问某地块的酸化改良方案，且该地块被判定为中度或重度酸化
- **THEN** 智能体 SHALL 返回调理剂施用量建议（如石灰施用量 kg/亩）和改良措施（如施肥方式、轮作制度调整）

#### Scenario: 轻度或无酸化
- **WHEN** 用户询问某地块的酸化改良方案，但该地块为轻度酸化或无明显酸化
- **THEN** 智能体 SHALL 返回"无需特殊改良"的提示，建议常规监测和维护

### Requirement: 模型3 与模型1 整合诊断
系统 SHALL 在 agent 层实现模型3（障碍诊断）与模型1（退化风险）的整合，当用户请求综合诊断时，同时调用两个模型并整合结果。

#### Scenario: 综合诊断查询
- **WHEN** 用户询问某地块的综合诊断结果（同时涉及稳定性和障碍诊断），且两个模型的数据均已就绪
- **THEN** 系统 SHALL 同时调用 StabilityRiskAgent 和 ObstacleDiagnosisAgent，整合退化风险和障碍诊断结果，返回综合诊断报告
