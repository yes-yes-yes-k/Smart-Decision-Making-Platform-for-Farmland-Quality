# heavy-metal-cd-prediction Specification (Delta)

## MODIFIED Requirements

### Requirement: 本地 Cd 双模型参数级预测

系统 SHALL 提供本地 torch 实现的作物 Cd（crop_cd）与土壤有效态 Cd（effective_cd）预测能力（领域函数，非 HTTP API）。系统 MUST 固定每个模型的特征名称及顺序，并验证特征维数与 scaler 一致；crop_cd 的 `solution` 特征索引 MUST 为 13，effective_cd 的 `Cdsolution` 特征索引 MUST 为 20。模型资产 MUST 位于受控项目目录，且加载前校验路径、存在性与 manifest 摘要。项目运行时 MUST NOT 依赖 AcidMap 在线服务。系统 MUST 以 `mg/kg` 作为两个模型的输出单位标注，并 MUST 返回可追溯的单位依据（原系统模型定义 `EffCd = exp(LnEffCd) [单位：mg/kg]`、`CropCd = exp(LnCropCd) [单位：mg/kg]` 及建表迁移列注释）。`unit_status` MUST 保持 `unverified`，直到该单位与实测数值量级完成核对；核验前系统 MUST NOT 将该值表述为可直接对外引用的浓度。

#### Scenario: 查询模型清单

- **WHEN** 调用方请求 Cd 模型清单
- **THEN** 系统 MUST 返回两个模型各自的标识、预测对象、完整有序输入字段、特殊输入字段、输出单位标注 `mg/kg`、单位依据及 `unit_status=unverified`
- **AND** 系统 MUST 明确标记该能力为参数级预测，不等同于地块级评估

#### Scenario: 完整参数执行预测

- **WHEN** 调用方为任一模型提供所有必需且有限的数值输入
- **THEN** 系统 MUST 按该模型固定特征顺序运行本地 torch 推理并返回预测数值与 `success` 状态
- **AND** 系统 MUST 将该结果的单位标注为 `mg/kg` 并保持 `unit_status=unverified`
- **AND** 系统 MUST NOT 返回任何阈值分箱、安全等级或法规结论

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
