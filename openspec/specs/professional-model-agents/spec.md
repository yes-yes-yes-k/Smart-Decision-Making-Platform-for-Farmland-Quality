# professional-model-agents Specification

## Purpose
TBD - created by archiving change multi-agent-model-framework. Update Purpose after archive.
## Requirements
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

### Requirement: FertilityMLAgent 智能体
系统 SHALL 实现 `FertilityMLAgent` 智能体，对应模型6「耕地肥力机器学习预测模型」，负责调用预训练的 ExtraTreesRegressor 模型对 SOC（土壤有机碳）和 Dose（施用量）进行预测，并通过 `framework/agents/manager.py` 注册为 `model-6`。该智能体不再依赖其他模型结果，作为独立的计算单元接入 farmer 角色路由。

#### Scenario: 农户 SOC 预测查询
- **WHEN** 农户询问"我的田土壤有机碳含量大概多少？"，且 `framework/agents/manager.py` 已将 `FertilityMLAgent` 注册为 `model-6`
- **THEN** 智能体 SHALL 调用 `framework/domain/other_models/model_6.py` 中的 `model_6_execution`，传入从问题中提取或默认填充的土壤特征字典，返回包含 `soc_prediction`（g/kg）、`soc_confidence`（0.91）、`model_version` 的结构化结果，并由 `answer_question` 方法包装为包含 `answer`、`evidence`、`confidence` 字段的自然语言响应

#### Scenario: 农户 Dose 施用量预测查询
- **WHEN** 农户询问"我这块地大概需要施多少有机肥？"
- **THEN** 智能体 SHALL 调用 `model_6_execution` 返回 `dose_prediction`（kg/亩）、`dose_confidence`（0.47）、`dose_warning` 字段，并在自然语言回答中明确标注"预测结果仅供参考"

#### Scenario: 综合肥力诊断查询
- **WHEN** 农户询问"我的田肥力怎么样？"
- **THEN** 智能体 SHALL 同时返回 SOC 和 Dose 两个预测值，并提供综合诊断说明（如"SOC 预测 X g/kg，建议施肥量约 Y kg/亩"），`evidence` 字段包含两个预测值的指标列表

#### Scenario: 模型降级时的回退响应
- **WHEN** `model_6_execution` 返回 `status: "fallback"`（模型文件缺失或 sklearn 未安装）
- **THEN** 智能体 SHALL 在 `answer` 中标注"基于训练集均值的估算"而非"基于 ML 模型预测"，`confidence` 字段值降低到 0.3，并在 `evidence` 中包含 `fallback_reason` 字段

#### Scenario: Agent 独立执行无依赖
- **WHEN** `AgentManager.process` 调用 farmer 角色对应的智能体集合 `["model-4", "model-5", "model-6"]`
- **THEN** `model-6`（FertilityMLAgent）的 `dependencies` SHALL 为空列表 `[]`，可在拓扑排序中与 `model-4`、`model-5` 并行执行，不等待上游 agent 结果

#### Scenario: 非肥力相关问题跳过 model-6
- **WHEN** 农户角色提出的问题不包含肥力相关关键词（如"我的田 pH 如何"），且 `AgentManager` 路由到 model-6
- **THEN** `AgentManager._should_execute_agent` SHALL 返回 False，model-6 不被执行（不触发模型加载），`details["model-6"]` 字段值为 `{status: "skipped", reason: "question_not_related"}`。肥力关键词列表包括：有机碳、SOC、施用量、施肥量、施肥、Dose、剂量、施多少肥、肥力、综合肥力、秸秆、有机肥、培肥

#### Scenario: 输入越界时返回拒绝响应
- **WHEN** `FertilityMLAgent.execute` 收到包含越界特征值的输入，`model_6_execution` 返回 `status: "rejected"`
- **THEN** Agent SHALL 在 `answer` 中明文标注越界特征和合法范围（如"输入值异常，无法预测。越界特征：pH=99.0（合法范围 3.0-11.0）"），不返回预测值，`evidence` 为空列表

