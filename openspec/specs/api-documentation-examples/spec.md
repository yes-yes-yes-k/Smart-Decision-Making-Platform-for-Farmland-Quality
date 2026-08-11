# api-documentation-examples Specification

## Purpose
TBD - created by archiving change add-model-run-apifox-examples. Update Purpose after archive.
## Requirements
### Requirement: 模型调用文档展示六个正式专业模型

系统 MUST 在 `POST /api/v1/models/run` 的文档中展示 6 个正式专业模型请求示例：`obstacle-diagnosis`、`acidification-remediation`、`organic-matter-improvement`、`stability-risk-evaluation` 和 `quality-grade-evaluation`。每个示例 MUST 给出最小输入、地块标识或运行前提以及预期可靠性状态。

#### Scenario: 在接口文档中选择正式模型示例
- **WHEN** 调用者查看模型调用接口的 JSON 请求示例
- **THEN** 文档 MUST 显示 6 个正式模型的规范 ID、中文名称和可直接调用的示例

### Requirement: 文档区分正式、辅助和实验性能力

系统 MUST 在模型 API 与聊天 API 文档中标明空间结构解析和关键指标解析为辅助能力，协同提升为实验性能力，并说明它们不属于正式专业 Agent 或聊天路由范围。

#### Scenario: 查阅辅助或实验性能力说明
- **WHEN** 调用者查阅模型目录说明
- **THEN** 文档 MUST 显示能力分类、是否可聊天路由、可靠性状态和运行限制

### Requirement: 聊天接口文档展示零至六的问题类型

系统 MUST 在 `/api/v1/chat/` 文档中说明 `question_type=0` 为 RAG，`question_type=1..6` 各自对应单一正式 Agent，并明确 type 1 稳定性风险与 type 2 质量等级、以及 type 4 酸化与 type 5 有机质的业务边界。

#### Scenario: 查阅相关业务边界问题的路由
- **WHEN** 调用者查看稳定性风险、质量等级或酸化/有机质施用问题的聊天示例
- **THEN** 文档 MUST 分别展示 type 1/model-1 与 type 2/model-2、type 4/model-4 与 type 5/model-5 的路由和返回字段差异

