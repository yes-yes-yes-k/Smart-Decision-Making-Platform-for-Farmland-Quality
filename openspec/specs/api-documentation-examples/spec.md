# api-documentation-examples Specification

## Purpose
TBD - created by archiving change add-model-run-apifox-examples. Update Purpose after archive.
## Requirements
### Requirement: 模型调用接口提供六个可切换的请求示例

系统 MUST 在 `POST /api/v1/models/run` 的 `application/json` 请求体中提供 6 个具名示例，分别对应 `spatial-structure-analysis`、`soil-indicator-analysis`、`obstacle-factor-identification`、`acidification-governance`、`organic-matter-improvement` 和 `multi-factor-collaborative-improvement`。

#### Scenario: 在接口文档中选择模型示例

- **WHEN** 调用者查看模型调用接口的 JSON 请求示例
- **THEN** 文档 MUST 显示 6 个有明确中文名称的示例，且每个示例的 `model_id` 与一个已注册专题模型一一对应

### Requirement: 请求示例符合实际路由契约

系统 MUST 只在模型调用请求示例中使用路由支持的顶层字段：`model_id`、`area_code`、`longitude`、`latitude`、`indicators` 与 `context`。`model_id` 必须为必填字段。

#### Scenario: 使用任一示例发起调用

- **WHEN** 调用者使用任一具名示例发送请求
- **THEN** 请求体 MUST 包含有效的 `model_id`，且不包含路由不会透传的顶层字段

### Requirement: 文档展示模型调用的完整响应结构

系统 MUST 提供一个协同提升模型的成功示例，展示外层 `status` 与 `data` 包装结构，以及结果中的模型信息、发现项、推荐图层、溯源、可靠性、回退、依赖模型和分区建议。系统还 MUST 提供缺少 `model_id` 时的 `400` 错误示例。

#### Scenario: 查阅协同提升模型的成功响应

- **WHEN** 调用者查看 `200` 响应示例
- **THEN** 示例 MUST 展示 `data.model.model_id` 为 `multi-factor-collaborative-improvement`，并包含 `dependent_models` 与 `zoning_recommendations`

#### Scenario: 查阅缺少模型标识的错误响应

- **WHEN** 调用者查看 `400` 响应示例
- **THEN** 示例 MUST 返回 `MISSING_MODEL_ID` 错误码和清晰的中文错误信息

