## MODIFIED Requirements

### Requirement: 五维路由特征判定

系统 SHALL 在现有问题类型路由之上叠加五维路由判定，五个维度依次为：业务任务、分析尺度、数据类型、预期输出、模型依赖。路由判定 SHALL 逐级缩小候选 Agent 集合，优先从请求上下文与问题文本提取维度特征；无法确定某一维度时 SHALL 回退到现有 `question_type` 路由作为兜底。五维特征 SHALL 真正参与排他规则判定：`apply_exclusive_rules` SHALL 读取 `context` 中的分析尺度和数据类型，并结合从问题文本提取的业务任务和预期输出标签，作为排他规则的判别条件。

#### Scenario: 地块级质量等级评价问题
- **WHEN** 用户提供 `parcel_id` 且问题为质量等级评价（如"我的田耕地质量等级是多少"）
- **THEN** 系统 SHALL 识别分析尺度为地块级、数据类型为评价结果、业务任务为质量等级评价
- **AND** 路由到 `model-5`

#### Scenario: 地块级障碍诊断问题
- **WHEN** 用户提供 `parcel_id` 且问题为障碍诊断（如"我这块地到底有啥毛病"）
- **THEN** 系统 SHALL 识别分析尺度为地块级、业务任务为障碍诊断
- **AND** 路由到 `model-1`
- **AND** SHALL NOT 路由到 `model-5`

#### Scenario: 省级障碍诊断问题
- **WHEN** 用户问题为省级障碍诊断（如"全省耕地质量存在哪些问题"）
- **THEN** 系统 SHALL 识别分析尺度为省级、业务任务为现状/障碍识别
- **AND** 路由到 `model-1`

#### Scenario: 酸化调理剂用量问题
- **WHEN** 用户问题为酸化治理与调理剂用量（如"我的田酸化了要施多少石灰"）
- **THEN** 系统 SHALL 识别数据类型为处方用量、业务任务为酸化改良
- **AND** 路由到 `model-2`
- **AND** SHALL NOT 路由到 `model-3`

#### Scenario: 有机肥施用量问题
- **WHEN** 用户问题为有机肥施用和培肥措施（如"有机肥每亩施用量多少"）
- **THEN** 系统 SHALL 识别数据类型为处方用量、业务任务为有机质培肥
- **AND** 路由到 `model-3`
- **AND** SHALL NOT 路由到 `model-2`

#### Scenario: 维度缺失回退
- **WHEN** 请求未提供 `parcel_id`、`area_code` 且问题文本无法判定分析尺度
- **THEN** 系统 SHALL 回退到现有 `question_type` 关键词/向量路由
- **AND** SHALL NOT 因维度缺失而拒绝路由

#### Scenario: 维度冲突无法消解
- **WHEN** 五维特征命中多条指向不同模型的排他规则，无法消解歧义
- **THEN** 系统 SHALL 返回「模型边界待确认」降级状态
- **AND** SHALL NOT 调用任一易混淆专业 Agent
