# routing-exclusive-rules Specification

## Purpose
TBD - created by archiving change add-routing-exclusive-rules. Update Purpose after archive.
## Requirements
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

### Requirement: 模型边界待确认降级状态

当排他规则无法消解模型重叠（如未由专业团队确认 model-1 与 model-5 的评价维度分工）时，系统 SHALL 返回「模型边界待确认」显式降级状态，SHALL NOT 自行选择任一 Agent。路由结果 SHALL 携带 `routing_status: "boundary_pending"` 信号，并在 API 响应中体现。

#### Scenario: 无法消解的重叠问题
- **WHEN** 用户问题同时命中排他规则冲突或多模型重叠且无明确判别条件
- **THEN** 系统 SHALL 返回「模型边界待确认」降级提示
- **AND** SHALL NOT 调用任一易混淆专业 Agent

#### Scenario: 可消解的重叠问题
- **WHEN** 排他规则能明确判别重叠问题归属
- **THEN** 系统 SHALL 正常路由到对应 Agent
- **AND** SHALL NOT 触发「模型边界待确认」降级

### Requirement: 路由逻辑模块化

系统 SHALL 将问题类型判定逻辑从图节点模块中抽取为独立路由模块，对外保持 `identify_question_type` 等函数签名不变，便于版本管理和回归测试。

#### Scenario: 独立路由模块
- **WHEN** 应用加载路由逻辑
- **THEN** 路由判定函数 SHALL 位于独立路由模块中
- **AND** 图节点仅负责状态组装与分支调度

### Requirement: 易混淆对测试集

系统 SHALL 扩充路由测试集，针对 model-1/5（障碍诊断 vs 质量等级）、model-2/3（酸化 vs 有机质）两组易混淆对各提供不少于 20 条正例与反例问题。正例 SHALL 断言路由到正确 Agent/question_type；反例 SHALL 断言不误选到易混淆对。

#### Scenario: 正例路由正确
- **WHEN** 提交换淆对的正例问题
- **THEN** 系统 SHALL 路由到对应的正确 Agent/question_type

#### Scenario: 反例不误选
- **WHEN** 提交付淆对的反例问题
- **THEN** 系统 SHALL 不路由到易混淆对中的另一 Agent
- **AND** 测试断言通过

