## ADDED Requirements

### Requirement: OrganicMatterAgent 规则路径只返回安全降级结果

`OrganicMatterAgent` 的 `execute`、`analyze` 和自然语言答复 MUST 对相同输入使用一致的安全降级语义。缺少真实模型结果时，Agent 禁止暴露固定规则施用量、提升量、默认县域均值或其他无依据定量结论。

#### Scenario: 直接调用 Agent 且缺少模型特征

- **WHEN** 内部调用方直接执行 `OrganicMatterAgent`，且数据库未命中、模型特征不足或模型不可用
- **THEN** Agent SHALL 返回统一 `degraded` 或 `unavailable` 结果
- **AND** `manure_dosage`、`potential_increase`、`dose` 和 `dose_prediction` MUST 为 `null` 或在规范响应中省略
- **AND** `issues` SHALL 包含稳定代码 `MODEL5_QUANTITATIVE_UNAVAILABLE`

#### Scenario: 自然语言答复使用规则降级

- **WHEN** `answer_question` 无法获得真实模型结果
- **THEN** 答复 MAY 说明需要补充的输入和可执行的核验步骤
- **AND** 答复 MUST NOT 声称县域平均有机质、推荐每亩施用量或预期提升量
- **AND** 证据列表 MUST NOT 包含由默认值或固定规则生成的数值

#### Scenario: 聊天入口地块未命中权威数据

- **WHEN** 聊天链路已经选择地块但该地块未命中权威 Model-5 输入数据
- **THEN** Agent SHALL 保持现有专业输入守卫并拒绝执行规则处方
- **AND** 系统 MUST NOT 因兼容直接调用路径存在而绕过该守卫

#### Scenario: 真实模型结果不受影响

- **WHEN** Model-5 使用可验证输入和已部署模型成功执行
- **THEN** Agent SHALL 继续返回真实 SOC/Dose 预测、置信度、模型版本和数据来源
- **AND** 结果 SHALL 标记 `simulated=false`
