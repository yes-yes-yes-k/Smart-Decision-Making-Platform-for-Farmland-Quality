# routing-exclusive-rules Specification

## Purpose
TBD - created by archiving change add-routing-exclusive-rules. Update Purpose after archive.
## Requirements
### Requirement: 五维路由特征判定

系统 SHALL 在现有问题类型路由之上叠加五维路由判定，五个维度依次为：业务任务、分析尺度、数据类型、预期输出、模型依赖。路由判定 SHALL 逐级缩小候选 Agent 集合，优先从请求上下文与问题文本提取维度特征；无法确定某一维度时 SHALL 回退到现有 `question_type` 路由作为兜底。

#### Scenario: 地块级质量等级评价问题
- **WHEN** 用户提供 `parcel_id` 且问题为质量等级评价（如"我的田耕地质量等级是多少"）
- **THEN** 系统 SHALL 识别分析尺度为地块级、数据类型为评价结果、业务任务为质量等级评价
- **AND** 路由到 `model-7`

#### Scenario: 省级障碍诊断问题
- **WHEN** 用户问题为省级障碍诊断（如"全省耕地质量存在哪些问题"）
- **THEN** 系统 SHALL 识别分析尺度为省级、业务任务为现状/障碍识别
- **AND** 路由到 `model-3`

#### Scenario: 维度缺失回退
- **WHEN** 请求未提供 `parcel_id`、`area_code` 且问题文本无法判定分析尺度
- **THEN** 系统 SHALL 回退到现有 `question_type` 关键词/向量路由
- **AND** SHALL NOT 因维度缺失而拒绝路由

### Requirement: 排他规则配置

系统 SHALL 提供独立、可版本化、可单测的排他规则配置，以数据驱动方式声明易混淆模型对及其判别条件。排他规则 SHALL 覆盖：现状评价→model-3；潜力→model-2；有机质投入量→model-6；酸化调理剂→model-4；稳定性风险→model-1；质量等级评价→model-7。

#### Scenario: 现状评价优先 model-3
- **WHEN** 用户问题为现状/障碍识别（如"我这块地到底有啥毛病"）
- **THEN** 系统 SHALL 依据排他规则路由到 `model-3`
- **AND** SHALL NOT 路由到 `model-7`

#### Scenario: 有机质投入量路由 model-6
- **WHEN** 用户问题为有机质投入量/施肥量预测
- **THEN** 系统 SHALL 依据排他规则路由到 `model-6`
- **AND** SHALL NOT 路由到 `model-4` 或 `model-5`

#### Scenario: 酸化调理剂路由 model-4
- **WHEN** 用户问题为酸化治理与调理剂用量
- **THEN** 系统 SHALL 依据排他规则路由到 `model-4`
- **AND** SHALL NOT 路由到 `model-6`

### Requirement: 模型边界待确认降级状态

当排他规则无法消解模型重叠（如未由专业团队确认 model-3 与 model-7 的评价维度分工）时，系统 SHALL 返回「模型边界待确认」显式降级状态，SHALL NOT 自行选择任一 Agent。路由结果 SHALL 携带 `routing_status: "boundary_pending"` 信号，并在 API 响应中体现。

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

系统 SHALL 扩充路由测试集，针对 model-3/7、model-2/7、model-4/6 三组易混淆对各提供不少于 20 条正例与反例问题。正例 SHALL 断言路由到正确 Agent/question_type；反例 SHALL 断言不误选到易混淆对。

#### Scenario: 正例路由正确
- **WHEN** 提交易混淆对的正例问题
- **THEN** 系统 SHALL 路由到对应的正确 Agent/question_type

#### Scenario: 反例不误选
- **WHEN** 提交易混淆对的反例问题
- **THEN** 系统 SHALL 不路由到易混淆对中的另一 Agent
- **AND** 测试断言通过

