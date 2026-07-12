## ADDED Requirements

### Requirement: 系统提供 6 个可调用的模拟专题模型目录

系统 MUST 提供一份面向未来大模型或 Agent 的模拟专题模型目录，并至少包含以下 6 个固定模型标识：`spatial-structure-analysis`、`soil-indicator-analysis`、`obstacle-factor-identification`、`acidification-governance`、`organic-matter-improvement`、`multi-factor-collaborative-improvement`。每个模型 MUST 返回稳定的中文名称、用途说明、最小输入说明和推荐图层映射。

#### Scenario: 请求模型清单

- **WHEN** 调用方请求当前仓库可用的专题模型目录
- **THEN** 系统 MUST 返回全部 6 个模拟专题模型的 `model_id`、中文名称、用途说明、最小输入说明和推荐图层

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
