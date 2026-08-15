## 新增需求

### 需求: model-5 真实 RF 请求示例

模型调用文档必须展示 `organic-matter-improvement`（公开 `model-5`）的真实请求示例，包含 `area_code`、`land_type`、规范字段或外部源字段、最小输入和响应中的模型版本/置信度/降级状态。

#### 场景: 调用者选择 model-5
- **当** 调用者查看 `POST /api/v1/models/run` 文档
- **那么** 文档展示的 model-5 示例可以直接触发 `OrganicMatterAgent`，并说明韶关旱地/水田的输入差异

## 修改需求

### Requirement: 模型调用文档展示六个正式专业模型

系统 MUST 在 `POST /api/v1/models/run` 文档中展示 6 个正式专业模型请求示例。model-5 示例 MUST 使用规范公开 ID `organic-matter-improvement`，说明其底层为有机质培肥 ML、韶关区域使用 SG RF，并给出 `model_version`、`dose_confidence`、`simulated` 和降级前提；model-6 示例 MUST 明确为占位能力，不得描述为肥力 RF。

#### Scenario: model-5 文档示例可执行
- **WHEN** 调用者按文档提交 model-5 请求
- **THEN** 请求包含最小区域/土地类型/特征输入，并能得到真实或明确标注的降级结果

#### Scenario: model-6 文档边界清晰
- **WHEN** 调用者查看 model-6 示例
- **THEN** 文档明确说明其为占位能力，并与 model-5 的 RF 预测区分

### Requirement: 聊天接口文档展示零至六的问题类型

系统 MUST 在 `/api/v1/chat/` 文档中说明 question_type=0 为 RAG，1 至 6 各自对应单一正式 Agent；其中 type 5 必须说明有机质培肥请求调用真实/降级的 model-5，type 6 必须说明仍为 model-6 占位符。

#### Scenario: 查阅 type 5/type 6 边界
- **WHEN** 调用者查看有机质培肥或占位模型的聊天示例
- **THEN** 文档分别展示 type 5/model-5 的 RF 输入和返回字段，以及 type 6/model-6 的占位行为
