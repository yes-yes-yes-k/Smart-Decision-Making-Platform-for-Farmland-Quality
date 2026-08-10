## MODIFIED Requirements

### Requirement: 排他规则配置

系统 SHALL 提供独立、可版本化、可单测的排他规则配置，以数据驱动方式声明易混淆模型对及其判别条件。排他规则 SHALL 覆盖：现状评价→model-1；酸化调理剂→model-2；有机质培肥→model-3；稳定性风险→model-4；质量等级评价→model-5。

#### Scenario: 现状评价优先 model-1
- **WHEN** 用户问题为现状/障碍识别（如"我这块地到底有啥毛病"）
- **THEN** 系统 SHALL 依据排他规则路由到 `model-1`
- **AND** SHALL NOT 路由到 `model-5`

#### Scenario: 酸化调理剂路由 model-2
- **WHEN** 用户问题为酸化治理与调理剂用量
- **THEN** 系统 SHALL 依据排他规则路由到 `model-2`
- **AND** SHALL NOT 路由到 `model-3`

#### Scenario: 有机质培肥路由 model-3
- **WHEN** 用户问题为有机肥施用和培肥措施
- **THEN** 系统 SHALL 依据排他规则路由到 `model-3`
- **AND** SHALL NOT 路由到 `model-2`

### Requirement: 易混淆对测试集

系统 SHALL 扩充路由测试集，针对 model-1/5（障碍诊断 vs 质量等级）、model-2/3（酸化 vs 有机质）两组易混淆对各提供不少于 20 条正例与反例问题。正例 SHALL 断言路由到正确 Agent/question_type；反例 SHALL 断言不误选到易混淆对。

#### Scenario: 正例路由正确
- **WHEN** 提交换淆对的正例问题
- **THEN** 系统 SHALL 路由到对应的正确 Agent/question_type

#### Scenario: 反例不误选
- **WHEN** 提交付淆对的反例问题
- **THEN** 系统 SHALL 不路由到易混淆对中的另一 Agent
- **AND** 测试断言通过
