## MODIFIED Requirements

### Requirement: 实现 Random Forest 模型加载和预测

系统 SHALL 加载预训练的 Random Forest 模型文件（旱地和水田各一个 `.joblib`），从 DB 读取土壤指标（pH/SOMbe/AK/AP/TN 等），预测 Dose（推荐施肥量）。只有实际模型成功执行时才 SHALL 返回非空 Dose；模型文件、依赖、输入或模型执行不可用时，系统 MUST NOT 使用固定阈值或等级表生成替代施用量。

#### Scenario: RF 模型可用时预测

- **WHEN** 模型文件存在、运行依赖可用且 soil_indicators 包含模型所需输入特征
- **THEN** 系统 SHALL 返回 `status=ok`、`simulated=false`、非空预测 Dose、实际模型版本和来源
- **AND** 系统 SHALL 只把该真实模型结果持久化为可用于报告的定量结果

#### Scenario: RF 模型不可用时定量结果不可用

- **WHEN** scikit-learn 未安装、模型文件不存在、模型加载失败或 RF 预测异常
- **THEN** 系统 SHALL 返回 `status=degraded` 或 `status=unavailable`
- **AND** `dose`、`dose_prediction`、`manure_dosage` 和 `potential_increase` MUST 为 `null` 或不出现在非兼容响应中
- **AND** 系统 MUST NOT 调用固定阈值规则生成替代施用量
- **AND** 结果 SHALL 标记 `simulated=true` 并提供稳定的不可用原因

### Requirement: Model-5 规则降级禁止无依据定量建议

Model-5 在只能使用规则或模板内容时 MUST 只返回有实际输入依据的定性信息，MUST NOT 根据固定等级表、默认土壤指标或固定线性比例生成施用量、预期提升量或县域平均值。

#### Scenario: 有真实有机质输入但没有预测模型

- **WHEN** 调用方提供可验证的有机质实测值，但没有可用的 Dose/SOC 模型结果
- **THEN** 系统 MAY 返回基于该实测值的定性等级
- **AND** 所有施用量、提升量和预测字段 MUST 为 `null`
- **AND** 响应 SHALL 说明定性等级不等于施肥处方或提升预测

#### Scenario: 没有真实有机质输入

- **WHEN** 调用方没有提供可验证有机质值且数据库也未命中
- **THEN** 系统 MUST NOT 使用默认 `organic_matter`、默认等级或默认施肥量构造结果
- **AND** 系统 SHALL 返回缺少输入或能力不可用的机器可读状态

#### Scenario: 禁止固定提升公式

- **WHEN** Model-5 进入任何规则降级分支
- **THEN** 系统 MUST NOT 使用 `manure_dosage / 1000 * 1.5` 或等价固定比例计算 `potential_increase`
- **AND** 兼容字段 `potential_increase` MUST 为 `null`
