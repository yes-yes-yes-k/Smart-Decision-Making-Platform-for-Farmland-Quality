## REMOVED Requirements

### Requirement: 模型调用接口提供六个可切换的请求示例
正式专业模型示例改为 7 项，不再以原六个 Demo 专题模型为准。

### Requirement: 请求示例符合实际路由契约
模型 API 新增地块标识输入并引用正式能力目录，原字段范围不再完整。

### Requirement: 文档展示模型调用的完整响应结构
成功响应示例改为正式专业 Agent 的结构化分析结果，不再以协同提升 Demo 为唯一示例。

## ADDED Requirements

### Requirement: 模型调用文档展示七个正式专业模型

系统 MUST 在 `POST /api/v1/models/run` 的文档中展示 7 个正式专业模型请求示例：`stability-risk-evaluation`、`improvement-potential-assessment`、`obstacle-diagnosis`、`acidification-remediation`、`organic-matter-improvement`、`fertility-soc-dose-prediction` 和 `quality-grade-evaluation`。每个示例 MUST 给出最小输入、地块标识或运行前提以及预期可靠性状态。

#### Scenario: 在接口文档中选择正式模型示例
- **WHEN** 调用者查看模型调用接口的 JSON 请求示例
- **THEN** 文档 MUST 显示 7 个正式模型的规范 ID、中文名称和可直接调用的示例

### Requirement: 文档区分正式、辅助和实验性能力

系统 MUST 在模型 API 与聊天 API 文档中标明空间结构解析和关键指标解析为辅助能力，协同提升为实验性能力，并说明它们不属于正式专业 Agent 或聊天路由范围。

#### Scenario: 查阅辅助或实验性能力说明
- **WHEN** 调用者查阅模型目录说明
- **THEN** 文档 MUST 显示能力分类、是否可聊天路由、可靠性状态和运行限制

### Requirement: 聊天接口文档展示零至七的问题类型

系统 MUST 在 `/api/v1/chat/` 文档中说明 `question_type=0` 为 RAG，`question_type=1..7` 各自对应单一正式 Agent，并明确 type 4 肥力预测与 type 7 有机质培肥的业务边界。

#### Scenario: 查阅有机质相关问题路由
- **WHEN** 调用者查看 SOC 预测或有机肥施用问题的聊天示例
- **THEN** 文档 MUST 分别展示 type 4/model-6 与 type 7/model-5 的路由和返回字段差异
