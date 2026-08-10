## MODIFIED Requirements

### Requirement: 专题能力按正式、辅助与实验性分类发布

系统 MUST 发布统一能力目录。正式专业模型 SHALL 由 5 个专业 Agent 一一提供；`spatial-structure-analysis` SHALL 标记为辅助空间能力，`soil-indicator-analysis` SHALL 标记为辅助指标能力，`multi-factor-collaborative-improvement` SHALL 标记为实验性能力。辅助和实验性能力 SHALL NOT 被列为正式专业模型，也 SHALL NOT 获得聊天 `question_type` 路由。

#### Scenario: 请求默认专业模型清单
- **WHEN** 调用方请求正式专业模型清单
- **THEN** 系统 MUST 返回 5 个正式模型的公开 ID、中文名称、最小输入和运行前提
- **AND** SHALL NOT 返回空间结构、指标分析或协同提升为正式专业模型

#### Scenario: 请求全量能力清单
- **WHEN** 调用方显式请求包含非正式能力的全量清单
- **THEN** 系统 MUST 返回辅助和实验性能力
- **AND** 每项 MUST 标示分类、是否可聊天路由及可靠性状态
