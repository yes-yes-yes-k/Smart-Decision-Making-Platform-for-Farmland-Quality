# callable-thematic-model-stubs Specification

## Purpose
定义一组可供未来大模型或 Agent 调用的模拟专题模型目录与统一调用契约，用于 Demo 阶段验证多模型协同的结构化接口边界。
## Requirements
### Requirement: 模拟专题模型支持统一结构化调用
系统 MUST 允许调用方以统一结构化入参调用任一模拟专题模型，并以统一结构化字段返回结果，而不是让调用方为不同模型适配不同的返回格式。返回结果 MUST 至少包含 `status`、`model`、`summary`、`findings`、`recommended_layers`、`recommendations`、`lineage`、`reliability` 和 `fallback`。

#### Scenario: 调用酸化治理模拟模型
- **WHEN** 调用方以 `model_id=acidification-governance` 和合法区域参数发起模型调用
- **THEN** 系统 MUST 返回该模型的结构化摘要、关键发现、推荐图层、治理建议、来源说明和可靠性标记

#### Scenario: 调用不存在的模型
- **WHEN** 调用方传入未注册的 `model_id`
- **THEN** 系统 MUST 返回机器可读的失败状态和错误码，而不是只返回笼统文本

### Requirement: 协同提升模拟模型声明其组合来源
系统 MUST 将 `multi-factor-collaborative-improvement` 定义为组合型模拟模型，并在结果中声明其综合了哪些上游专题模型或等价专题结果。该模型 MUST 返回分区分类的综合提升建议，而不是只返回一段无来源的自然语言总结。

#### Scenario: 调用协同提升模拟模型
- **WHEN** 调用方请求 `multi-factor-collaborative-improvement`
- **THEN** 系统 MUST 返回其依赖的专题模型标识或等价来源列表，以及分区分类的综合建议结果

### Requirement: 模拟专题模型结果必须可追溯且明确为 Demo
系统 MUST 为每次模拟专题模型调用结果返回来源说明和 Demo 可靠性标记，明确结果用于演示多模型调用契约，而不是生产级专题模型结论。若输入字段不足以支撑模型占位结果，系统 MUST 返回结构化回退说明。

#### Scenario: 读取模型结果的可靠性说明
- **WHEN** 调用方读取任一模拟专题模型的调用结果
- **THEN** 系统 MUST 返回 `demo_stub` 或等价的可靠性等级，并说明结果仅用于 Demo 演示

#### Scenario: 调用关键指标模型时输入不完整
- **WHEN** 调用方请求 `soil-indicator-analysis`，但缺少部分可选指标字段
- **THEN** 系统 MUST 通过模板值、默认上下文或其他 Demo 回退策略返回结构化结果，并在 `fallback` 中说明受影响字段

### Requirement: 专题能力按正式、辅助与实验性分类发布

系统 MUST 发布统一能力目录。正式专业模型 SHALL 由 6 个专业 Agent 一一提供；其中 `model-2` 同时承接 type 5 的质量等级/障碍度评价和 type 6 的提升潜力评估。`spatial-structure-analysis` SHALL 标记为辅助空间能力，`soil-indicator-analysis` SHALL 标记为辅助指标能力，`multi-factor-collaborative-improvement` SHALL 标记为实验性能力。辅助和实验性能力 SHALL NOT 被列为正式专业模型，也 SHALL NOT 获得聊天 `question_type` 路由。

#### Scenario: 请求默认专业模型清单
- **WHEN** 调用方请求正式专业模型清单
- **THEN** 系统 MUST 返回 6 个正式模型的公开 ID、中文名称、最小输入和运行前提
- **AND** SHALL NOT 返回空间结构、指标分析或协同提升为正式专业模型

#### Scenario: 请求全量能力清单
- **WHEN** 调用方显式请求包含非正式能力的全量清单
- **THEN** 系统 MUST 返回辅助和实验性能力
- **AND** 每项 MUST 标示分类、是否可聊天路由及可靠性状态

### Requirement: 正式专业模型复用 Agent 的统一结构化调用

系统 MUST 允许调用方以正式公开 `model_id` 调用对应专业 Agent 的结构化分析，返回统一字段 `status`、`capability`、`summary`、`findings`、`recommendations`、`evidence`、`lineage`、`reliability` 和 `fallback`。

#### Scenario: 调用酸化改良专业模型
- **WHEN** 调用方以 `model_id=acidification-remediation` 和满足前提的输入发起调用
- **THEN** 系统 MUST 调用 `model-4` 的结构化分析
- **AND** 返回与聊天链路同源的酸化判断、改良建议和可靠性状态

#### Scenario: 调用不具备 Agent 对应关系的辅助能力
- **WHEN** 调用方调用空间结构或关键指标辅助能力
- **THEN** 系统 MUST 返回其辅助能力分类和 Demo/数据状态
- **AND** SHALL NOT 声明已调用专业 Agent

### Requirement: 旧模型标识的处理边界明确

系统 MAY 为仍有明确业务对应关系的旧公开模型 ID 提供兼容行为，并在响应中返回规范 `model_id` 和弃用提示。已删除的 `model-7` 和 `quality-grade-evaluation` 标识 SHALL 按未知模型处理，系统 MUST NOT 将其映射到 `model-2`。

#### Scenario: 使用酸化治理旧模型标识
- **WHEN** 调用方使用可映射的旧酸化治理模型标识
- **THEN** 系统 MUST 返回 `acidification-remediation` 作为规范模型标识
- **AND** 返回可迁移提示

#### Scenario: 使用协同提升模型标识
- **WHEN** 调用方使用 `multi-factor-collaborative-improvement`
- **THEN** 系统 MUST 将其标示为实验性能力
- **AND** SHALL NOT 映射到 `model-6` 或其他正式专业 Agent
