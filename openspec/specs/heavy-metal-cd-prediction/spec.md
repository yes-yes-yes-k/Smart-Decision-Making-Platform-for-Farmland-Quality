# heavy-metal-cd-prediction Specification

## Purpose
TBD - created by archiving change add-heavy-metal-cd-prediction. Update Purpose after archive.
## Requirements
### Requirement: 本地 Cd 双模型参数级预测
系统 SHALL 提供本地 torch 实现的作物 Cd（crop_cd）与土壤有效态 Cd（effective_cd）预测能力（领域函数，非 HTTP API）。系统 MUST 固定每个模型的特征名称及顺序，并验证特征维数与 scaler 一致；crop_cd 的 `solution` 特征索引 MUST 为 13，effective_cd 的 `Cdsolution` 特征索引 MUST 为 20。模型资产 MUST 位于受控项目目录，且加载前校验路径、存在性与 manifest 摘要。项目运行时 MUST NOT 依赖 AcidMap 在线服务。

#### Scenario: 查询模型清单
- **WHEN** 调用方请求 Cd 模型清单
- **THEN** 系统 MUST 返回两个模型各自的标识、预测对象、完整有序输入字段、特殊输入字段及单位核验状态
- **AND** 系统 MUST 明确标记该能力为参数级预测，不等同于地块级评估

#### Scenario: 完整参数执行预测
- **WHEN** 调用方为任一模型提供所有必需且有限的数值输入
- **THEN** 系统 MUST 按该模型固定特征顺序运行本地 torch 推理并返回预测数值与 `success` 状态
- **AND** 系统 MUST 将结果单位状态标记为 `unverified`
- **AND** 系统 MUST NOT 返回基于未核实阈值的安全等级或法规结论

#### Scenario: 缺少特殊络合输入时按参考值降级
- **WHEN** crop_cd 请求缺少 `solution`，或 effective_cd 请求缺少 `Cdsolution`
- **THEN** 系统 MUST 使用训练集中位数参考值作为显式假设，返回 `degraded` 状态与稳定问题码
- **AND** 系统 MUST 在 `assumed_fields` 中回显参考值依据（数值、n、P25-P75、数据源）
- **AND** 系统 MUST NOT 将降级结果表述为实测输入

#### Scenario: 缺少其他必需输入或输入非法
- **WHEN** 任一必需字段缺失、不可转换为数值或为非有限数值
- **THEN** 系统 MUST 返回明确的缺失或拒绝状态及问题码
- **AND** 系统 MUST NOT 静默填入训练统计值、区域均值或零值
- **AND** 系统 MUST NOT 在拒绝路径调用模型推理

#### Scenario: 模型资产损坏或不匹配
- **WHEN** 资产缺失、摘要不符、维数不匹配或模型特征契约不一致
- **THEN** 系统 MUST 失败关闭并返回可诊断错误
- **AND** 系统 MUST NOT 以其他模型资产或默认权重替代

### Requirement: Cd 地块部分预填与来源边界
系统 MAY 为已确认语义、单位及来源的现有地块字段提供部分预填。系统 MUST 对每个已映射字段返回来源信息，并将无法映射或缺失的模型输入列入 `missing_fields`。部分预填 MUST NOT 被表述为完整地块级 Cd 评估；除已拍板的 solution/Cdsolution 参考值外，系统 MUST NOT 使用区域均值、训练集统计量或零值补齐缺失输入，也 MUST NOT 因预填字段存在而自动执行预测。

#### Scenario: 查询地块预填
- **WHEN** 调用方请求某地块的 Cd 输入预填
- **THEN** 系统 MUST 只返回已确认映射字段及逐字段 provenance
- **AND** 系统 MUST 将无映射或无值的输入列入 `missing_fields`
- **AND** 系统 MUST 明确指出预填不构成地块级评估，且未执行预测

#### Scenario: 地块不存在或数据源不可用
- **WHEN** 指定地块不存在或地块数据读取失败
- **THEN** 系统 MUST 返回明确的未找到或服务不可用错误
- **AND** 系统 MUST NOT 返回训练集统计值伪装成该地块输入

